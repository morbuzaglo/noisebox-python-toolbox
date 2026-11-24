"""AST -> Python source (one function at a time). See noisebox/mrt.py for the runtime the output relies on."""
import keyword
import re

RESERVED = set(keyword.kwlist) | {"mrt", "None", "True", "False", "self"}

# MATLAB built-ins whose result may share memory with an argument (so `y = f(x)` must copy if y is modified later)
NOT_FRESH = {"double", "single", "reshape", "real", "fliplr", "flipud", "deal", "getfield", "setfield", "rmfield",
             "struct", "char", "lower", "upper", "strtrim", "horzcat", "vertcat", "cat", "cellfun", "arrayfun",
             "feval", "ifelse", "orderfields", "logical", "values", "keys"}
# built-ins that return a scalar when all their array arguments are scalars
SCALAR_ALWAYS = {"numel", "length", "norm", "ndims", "isempty", "toc", "tic"}
SCALAR_IF_ARGS = {"floor", "ceil", "round", "abs", "sqrt", "exp", "log", "log10", "sin", "cos", "tan", "mod", "rem",
                  "hypot", "fix", "sign", "atan2", "atan", "asin", "acos", "max", "min"}
CONSTANTS = {"pi", "eps", "inf", "Inf", "nan", "NaN", "true", "false", "realmax", "realmin"}
NARGOUT_BUILTINS = {"max", "min", "size", "sort", "find", "unique", "meshgrid", "deal", "inpolygon", "cellfun",
                    "arrayfun", "feval"}


class UnsupportedError(Exception):
    pass


def pyname(n):
    if n in RESERVED or n.startswith("_"):
        return n + "_u" if n.startswith("_") else n + "_"
    return n


def _walk(node, fn):
    """Call fn on every tuple node (pre-order)."""
    if isinstance(node, tuple):
        if node and isinstance(node[0], str):
            fn(node)
        for c in node:
            _walk(c, fn)
    elif isinstance(node, list):
        for c in node:
            _walk(c, fn)


def lvalue_chain(node):
    """('call', ('field', ('id','x'), 'a'), args) -> ('x', [('.','a'), ('(', args)])"""
    items = []
    while node[0] in ("call", "cell", "field", "dynfield"):
        if node[0] == "call":
            items.append(("(", node[2]))
        elif node[0] == "cell":
            items.append(("{", node[2]))
        elif node[0] == "field":
            items.append((".", node[2]))
        else:
            items.append((".dyn", node[2]))
        node = node[1]
    if node[0] != "id":
        raise UnsupportedError("assignment target must start with a variable")
    items.reverse()
    return node[1], items


class FunctionGen:
    def __init__(self, fn, module):
        self.fn = fn
        self.m = module                       # ModuleGen (name resolution, builtin check)
        self.lines = []
        self.ind = 1
        self.end_stack = []
        self.sw_n = 0
        self.vars = set()
        self.mutated = set()
        self.level = {}                       # root -> 2 index/brace assignment, 1 field assignment, 0 nested path
        self.defined = set()
        self.uses = set()
        self.cur_line = fn["line"]

    # ---------------------------------------------------------------- analysis
    def analyse(self):
        fn = self.fn
        self.vars |= set(p for p in fn["params"] if p != "~") | set(fn["outs"])
        self.defined |= set(p for p in fn["params"] if p != "~")

        def visit_stmt(s):
            k = s[0]
            if k == "assign":
                self.note_mut(s[1])
            elif k == "massign":
                for t in s[1]:
                    if t[0] != "tilde":
                        self.note_mut(t)
            elif k == "for":
                self.vars.add(s[1])
            elif k == "try" and s[2]:
                self.vars.add(s[2])
            for sub in self.child_blocks(s):
                for st in sub:
                    visit_stmt(st)
        for st in fn["body"]:
            visit_stmt(st)

        def uses(node):
            if node[0] == "id" and node[1] in ("nargin", "nargout", "varargin", "varargout"):
                self.uses.add(node[1])
        _walk(fn["body"], uses)
        for p in fn["params"]:
            if p == "varargin":
                self.uses.add("varargin")
        for o in fn["outs"]:
            if o == "varargout":
                self.uses.add("varargout")

    def note_mut(self, target):
        root, items = lvalue_chain(target)
        self.vars.add(root)
        if not items:
            return
        self.mutated.add(root)
        lv = 2 if items[0][0] in ("(", "{") else (1 if len(items) == 1 else 0)
        self.level[root] = max(self.level.get(root, 0), lv)

    def copy_call(self, root, val):
        lv = self.level.get(root, 0)
        if lv >= 2:
            return "mrt.copy(%s)" % val
        if lv == 1:
            return "mrt.copy1(%s)" % val
        return val

    @staticmethod
    def child_blocks(s):
        k = s[0]
        if k == "if":
            return [b for _, b in s[1]] + ([s[2]] if s[2] else [])
        if k == "for":
            return [s[3]]
        if k == "while":
            return [s[2]]
        if k == "switch":
            return [b for _, b in s[2]] + ([s[3]] if s[3] else [])
        if k == "try":
            return [s[1], s[3]]
        return []

    # ---------------------------------------------------------------- output helpers
    def emit(self, text):
        self.lines.append("    " * self.ind + text)

    def src_comment(self, line):
        if line and line != self.cur_line or line == self.fn["line"]:
            pass
        txt = self.m.source_line(line)
        if txt:
            self.emit("# m:%d  %s" % (line, txt))

    # ---------------------------------------------------------------- function
    def generate(self):
        fn = self.fn
        self.analyse()
        params = fn["params"]
        sig = []
        has_varargin = bool(params) and params[-1] == "varargin"
        fixed = params[:-1] if has_varargin else params
        for i, p in enumerate(fixed):
            sig.append(("_a%d" % i if p == "~" else pyname(p)) + "=mrt.UNSET")
        if has_varargin:
            sig.append("*varargin")
        sig.append("nargout=1")
        pyfn = self.m.pyfunc_name(fn["name"], local=fn.get("local", False))
        self.lines.append("def %s(%s):" % (pyfn, ", ".join(sig)))
        doc = self.m.docstring(fn)
        if doc:
            self.lines.append("    " + doc)
        if has_varargin:
            self.emit("varargin = mrt.Cell(varargin)")
        if "nargin" in self.uses:
            names = ["_a%d" % i if p == "~" else pyname(p) for i, p in enumerate(fixed)]
            extra = " + float(len(varargin))" if has_varargin else ""
            self.emit("nargin = mrt.nargin_of(%s)%s" % (", ".join(names), extra))
        outs = fn["outs"]
        has_varargout = bool(outs) and outs[-1] == "varargout"
        fixed_outs = outs[:-1] if has_varargout else outs
        for o in fixed_outs:
            if o not in params:
                self.emit("%s = mrt.NOVAL" % pyname(o))
        if has_varargout:
            self.emit("varargout = mrt.Cell()")
        init = [v for v in sorted(self.mutated) if v not in params and v not in outs]
        for v in init:
            self.emit("%s = mrt.NOVAL" % pyname(v))
        for p in fixed:
            if self.level.get(p, 0) >= 1:
                self.emit("%s = %s" % (pyname(p), self.copy_call(p, pyname(p))))
        self.block(fn["body"])
        if not fn["body"] or fn["body"][-1][0] != "return":
            self.emit(self.return_expr())
        if len(self.lines) and self.lines[-1].strip() == "":
            pass
        return self.lines

    def return_expr(self):
        outs = self.fn["outs"]
        if not outs:
            return "return None"
        has_varargout = outs[-1] == "varargout"
        fixed = [pyname(o) for o in (outs[:-1] if has_varargout else outs)]
        if has_varargout:
            return "return mrt.ret((%s%s*varargout,), nargout)" % (", ".join(fixed), ", " if fixed else "")
        if len(fixed) == 1:
            return "return %s" % fixed[0]
        return "return mrt.ret((%s), nargout)" % ", ".join(fixed)

    # ---------------------------------------------------------------- statements
    def block(self, stmts):
        n0 = len(self.lines)
        for s in stmts:
            self.stmt(s)
        if len(self.lines) == n0:
            self.emit("pass")

    def stmt(self, s):
        k = s[0]
        line = s[-1] if isinstance(s[-1], int) else None
        if line:
            self.src_comment(line)
        getattr(self, "s_" + k)(s)

    def s_expr(self, s):
        e = s[1]
        if e[0] == "id" and e[1] in self.vars:
            return
        self.emit(self.E(e))

    def is_fresh(self, node):
        k = node[0]
        if k in ("num", "str", "mat", "cellmat", "range", "anon", "bin", "un", "post", "fh"):
            return True
        if k == "paren":
            return self.is_fresh(node[1])
        if k == "call" and node[1][0] == "id" and node[1][1] not in self.vars:
            n = node[1][1]
            return self.m.is_builtin(n) and n not in NOT_FRESH
        if k == "id" and node[1] not in self.vars:
            return True
        return False

    def root_of(self, node):
        while node[0] in ("call", "cell", "field", "dynfield", "post", "paren"):
            node = node[1]
        return node[1] if node[0] == "id" else None

    def s_assign(self, s):
        lhs, rhs = s[1], s[2]
        root, items = lvalue_chain(lhs)
        if not items:
            val = self.E(rhs)
            alias_src = self.root_of(rhs)
            if not self.is_fresh(rhs) and (self.level.get(root, 0) >= 1 or self.level.get(alias_src, 0) >= 1):
                lv = max(self.level.get(root, 0), self.level.get(alias_src, 0))
                val = ("mrt.copy(%s)" if lv >= 2 else "mrt.copy1(%s)") % val
            self.emit("%s = %s" % (pyname(root), val))
            self.defined.add(root)
            return
        self.defined.add(root)
        self.assign_chain(root, items, rhs_node=rhs, rhs_str=None)

    def assign_chain(self, root, items, rhs_node=None, rhs_str=None):
        r = pyname(root)
        is_delete = rhs_node is not None and rhs_node[0] == "mat" and rhs_node[1] == [] and items[-1][0] == "("
        if len(items) == 1:
            kind, arg = items[0]
            if kind == "(" or kind == "{":
                subs = self.subs(r, arg, [])
                val = rhs_str if rhs_str is not None else self.rhs_val(rhs_node)
                if kind == "(" and is_delete:
                    self.emit("%s = mrt.delete(%s, (%s))" % (r, r, subs))
                elif kind == "(":
                    self.emit("%s = mrt.setindex(%s, (%s), %s)" % (r, r, subs, val))
                else:
                    self.emit("%s = mrt.setcell(%s, (%s), %s)" % (r, r, subs, val))
                return
            val = rhs_str if rhs_str is not None else self.rhs_val(rhs_node)
            name = repr(arg) if kind == "." else self.E(arg)
            self.emit("%s = mrt.setfield(%s, %s, %s)" % (r, r, name, val))
            return
        if is_delete and items[-1][0] == "(":
            raise UnsupportedError("deleting elements of a nested value (x.a(i) = []) is not supported")
        path = []
        for n_, (kind, arg) in enumerate(items):
            if kind == ".":
                path.append("('.', %r)" % arg)
            elif kind == ".dyn":
                path.append("('.', %s)" % self.E(arg))
            else:
                prefix = "(%s,)" % ", ".join(path) if path else "()"
                base = "mrt.getpath(%s, %s)" % (r, prefix)
                subs = self.subs(base, arg, [])
                path.append("(%r, (%s))" % (kind, subs) if False else "('%s', (%s))" % (kind, subs))
        val = rhs_str if rhs_str is not None else self.rhs_val(rhs_node)
        self.emit("%s = mrt.setpath(%s, (%s,), %s)" % (r, r, ", ".join(path), val))

    def rhs_val(self, node):
        v = self.E(node)
        if not self.is_fresh(node):
            src = self.root_of(node)
            if self.level.get(src, 0) >= 1:
                return self.copy_call(src, v)
        return v

    def s_massign(self, s):
        lhs, rhs = s[1], s[2]
        n = len(lhs)
        simple = all(t[0] == "tilde" or (t[0] == "id") for t in lhs)
        # [c{1:k}] = f(...)
        if n == 1 and lhs[0][0] == "cell":
            root, items = lvalue_chain(lhs[0])
            if len(items) == 1 and items[0][0] == "{":
                rng = items[0][1][0]
                cnt = self.literal_count(rng)
                call = self.E(rhs, nargout=cnt)
                r = pyname(root)
                self.emit("%s = mrt.cs_assign(%s, %s, mrt.cs_unpack(%s, %d))" % (r, r, self.E(rng), call, cnt))
                self.defined.add(root)
                return
        names = []
        for i, t in enumerate(lhs):
            names.append("_" if t[0] == "tilde" else (pyname(t[1]) if simple else "_t%d" % i))
        if rhs[0] == "call" and self.is_function_call(rhs):
            call = self.E(rhs, nargout=n)
            if n == 1:
                self.emit("%s = %s" % (names[0], call))
            else:
                self.emit("%s = %s" % (", ".join(names), call))
        elif n == 1:
            self.emit("%s = mrt.cs_unpack(%s, 1)[0]" % (names[0], self.E(rhs)))
        else:
            self.emit("%s = mrt.cs_unpack(%s, %d)" % (", ".join(names), self.E(rhs), n))
        if simple:
            for t in lhs:
                if t[0] == "id":
                    self.defined.add(t[1])
        else:
            for i, t in enumerate(lhs):
                if t[0] == "tilde":
                    continue
                root, items = lvalue_chain(t)
                if not items:
                    self.emit("%s = _t%d" % (pyname(root), i))
                else:
                    self.assign_chain(root, items, rhs_node=None, rhs_str="_t%d" % i)
                self.defined.add(root)

    def literal_count(self, rng):
        if rng[0] == "range" and rng[2] is None and rng[1][0] == "num" and rng[3][0] == "num":
            return int(rng[3][1] - rng[1][1] + 1)
        if rng[0] == "num":
            return 1
        raise UnsupportedError("[x{range}] = f(...) needs a literal range such as 1:4")

    def is_function_call(self, node):
        b = node[1]
        if b[0] == "id" and b[1] not in self.vars:
            return True
        if b[0] == "field" and b[1] == ("id", "containers"):
            return True
        return False

    def s_if(self, s):
        arms, els = s[1], s[2]
        for i, (cond, body) in enumerate(arms):
            self.emit("%s %s:" % ("if" if i == 0 else "elif", self.cond(cond)))
            self.ind += 1
            self.block(body)
            self.ind -= 1
        if els:
            self.emit("else:")
            self.ind += 1
            self.block(els)
            self.ind -= 1

    def cond(self, node):
        if node[0] == "bin" and node[1] in ("&&", "||"):
            return self.E(node)
        return "mrt.truth(%s)" % self.E(node)

    def s_while(self, s):
        self.emit("while %s:" % self.cond(s[1]))
        self.ind += 1
        self.block(s[2])
        self.ind -= 1

    def s_for(self, s):
        var, rng, body = s[1], s[2], s[3]
        self.defined.add(var)
        if rng[0] == "range":
            a, st, b = rng[1], rng[2], rng[3]
            args = [self.E(a), self.E(b)] + ([self.E(st)] if st is not None else [])
            it = "mrt.for_range(%s)" % ", ".join(args)
        else:
            it = "mrt.iter_for(%s)" % self.E(rng)
        self.emit("for %s in %s:" % (pyname(var), it))
        self.ind += 1
        self.block(body)
        self.ind -= 1

    def s_switch(self, s):
        subj, cases, default = s[1], s[2], s[3]
        self.sw_n += 1
        v = "_sw%d" % self.sw_n
        self.emit("%s = %s" % (v, self.E(subj)))
        first = True
        for val, body in cases:
            self.emit("%s mrt.sw_eq(%s, %s):" % ("if" if first else "elif", v, self.E(val)))
            first = False
            self.ind += 1
            self.block(body)
            self.ind -= 1
        if default:
            if first:
                self.emit("if True:")
            else:
                self.emit("else:")
            self.ind += 1
            self.block(default)
            self.ind -= 1

    def s_try(self, s):
        body, var, handler = s[1], s[2], s[3]
        self.emit("try:")
        self.ind += 1
        self.block(body)
        self.ind -= 1
        self.emit("except Exception as _e:")
        self.ind += 1
        if var:
            self.emit("%s = mrt.to_ME(_e)" % pyname(var))
            self.defined.add(var)
        self.block(handler)
        self.ind -= 1

    def s_return(self, s):
        self.emit(self.return_expr())

    def s_break(self, s):
        self.emit("break")

    def s_continue(self, s):
        self.emit("continue")

    # ---------------------------------------------------------------- expressions
    def subs(self, base, args, _unused):
        out = []
        n = len(args)
        for k, a in enumerate(args):
            self.end_stack.append((base, k + 1, n))
            out.append(self.E(a))
            self.end_stack.pop()
        return ", ".join(out) + ("," if len(out) == 1 else "")

    def arg_list(self, args):
        """Call-site arguments; c{:} / s.f cs-lists are spread."""
        out = []
        for a in args:
            out.append(self.E(a, spread=True))
        return ", ".join(out)

    def is_cs(self, node):
        if node[0] == "cell":
            return any(a[0] in ("colon", "range") for a in node[2])
        return False

    def is_scalar(self, node):
        k = node[0]
        if k == "num":
            return not isinstance(node[1], complex)
        if k == "paren":
            return self.is_scalar(node[1])
        if k == "un" and node[1] in ("-", "+"):
            return self.is_scalar(node[2])
        if k == "bin" and node[1] in ("+", "-", "*", "/", "^", ".*", "./", ".^"):
            return self.is_scalar(node[2]) and self.is_scalar(node[3])
        if k == "call" and node[1][0] == "id" and node[1][1] not in self.vars:
            n = node[1][1]
            if n in SCALAR_ALWAYS:
                return True
            if n in SCALAR_IF_ARGS and node[2] and all(self.is_scalar(a) for a in node[2]):
                return True
        if k == "id" and node[1] in ("pi",) and node[1] not in self.vars:
            return True
        return False

    def E(self, node, nargout=None, spread=False):
        return getattr(self, "e_" + node[0])(node, nargout=nargout, spread=spread) \
            if node[0] in ("call", "cell", "field") else getattr(self, "e_" + node[0])(node)

    def e_num(self, n):
        v = n[1]
        if isinstance(v, complex):
            return "complex(0, %r)" % v.imag
        s = repr(float(v))
        return s if v >= 0 else "(%s)" % s

    def e_str(self, n):
        return repr(n[1])

    def e_colon(self, n):
        return "mrt.COLON"

    def e_end(self, n):
        if not self.end_stack:
            raise UnsupportedError("'end' outside an index expression")
        base, k, tot = self.end_stack[-1]
        return "mrt.end_(%s, %d, %d)" % (base, k, tot)

    def e_paren(self, n):
        return "(%s)" % self.E(n[1])

    def e_id(self, n):
        name = n[1]
        if name in self.vars or name in ("nargin", "nargout", "varargin"):
            return pyname(name)
        # not a variable: zero-argument function call
        return self.call_named(name, [], None)

    def e_un(self, n):
        op, a = n[1], n[2]
        if op == "-":
            if a[0] == "num" and not isinstance(a[1], complex):
                return "(%r)" % (-float(a[1]))
            return "(-%s)" % self.E(a) if self.is_scalar(a) else "mrt.neg(%s)" % self.E(a)
        if op == "+":
            return self.E(a)
        return "mrt.not_(%s)" % self.E(a)

    def e_bin(self, n):
        op, a, b = n[1], n[2], n[3]
        A, B = self.E(a), self.E(b)
        if op in ("+", "-"):
            return "(%s %s %s)" % (A, op, B)
        if op == ".*":
            return "(%s * %s)" % (A, B)
        if op == "*":
            if self.is_scalar(a) or self.is_scalar(b):
                return "(%s * %s)" % (A, B)
            return "mrt.mtimes(%s, %s)" % (A, B)
        if op == "./":
            return "mrt.div(%s, %s)" % (A, B)
        if op == "/":
            if b[0] == "num" and b[1] != 0:
                return "(%s / %s)" % (A, B)
            if self.is_scalar(a) and self.is_scalar(b):
                return "mrt.div(%s, %s)" % (A, B)
            return "mrt.mrdivide(%s, %s)" % (A, B)
        if op == ".^":
            return "mrt.power(%s, %s)" % (A, B)
        if op == "^":
            if self.is_scalar(a) and self.is_scalar(b):
                return "mrt.power(%s, %s)" % (A, B)
            return "mrt.mpower(%s, %s)" % (A, B)
        if op == "\\":
            return "mrt.mldivide(%s, %s)" % (A, B)
        if op == ".\\":
            return "mrt.div(%s, %s)" % (B, A)
        if op == "~=":
            return "(%s != %s)" % (A, B)
        if op in ("<", "<=", ">", ">=", "=="):
            return "(%s %s %s)" % (A, op, B)
        if op == "&&":
            return "(mrt.truth(%s) and mrt.truth(%s))" % (A, B)
        if op == "||":
            return "(mrt.truth(%s) or mrt.truth(%s))" % (A, B)
        if op == "&":
            return "mrt.land(%s, %s)" % (A, B)
        if op == "|":
            return "mrt.lor(%s, %s)" % (A, B)
        raise UnsupportedError("operator %s" % op)

    def e_range(self, n):
        a, st, b = n[1], n[2], n[3]
        if st is None:
            return "mrt.colon(%s, %s)" % (self.E(a), self.E(b))
        return "mrt.colon(%s, %s, %s)" % (self.E(a), self.E(b), self.E(st))

    def e_post(self, n):
        return ("mrt.ctranspose(%s)" if n[1] == "'" else "mrt.transpose(%s)") % self.E(n[2])

    def e_mat(self, n):
        rows = n[1]
        if not rows:
            return "mrt.empty()"
        if len(rows) == 1:
            return "mrt.hcat(%s)" % ", ".join(self.mat_elem(e) for e in rows[0])
        return "mrt.mat([%s])" % ", ".join("[%s]" % ", ".join(self.mat_elem(e) for e in r) for r in rows)

    def mat_elem(self, e):
        if e[0] == "field" and not (e[1][0] == "id" and e[1][1] == "containers"):
            return "*mrt.fieldcs(%s, %r)" % (self.E(e[1]), e[2])
        return self.E(e, spread=True)

    def e_cellmat(self, n):
        rows = n[1]
        if not rows:
            return "mrt.Cell()"
        return "mrt.cellmat([%s])" % ", ".join("[%s]" % ", ".join(self.mat_elem(e) for e in r) for r in rows)

    def e_anon(self, n):
        params, body = n[1], n[2]
        pnames = [("_p%d" % i if p == "~" else pyname(p)) for i, p in enumerate(params)]
        free = set()

        def collect(node):
            if node[0] == "id" and node[1] in self.defined and node[1] not in params:
                free.add(node[1])
        _walk(body, collect)
        caps = ["%s=%s" % (pyname(v), pyname(v)) for v in sorted(free)]
        saved, saved_vars = self.end_stack, self.vars
        self.end_stack = []
        self.vars = self.vars | set(params)
        b = self.E(body)
        self.end_stack, self.vars = saved, saved_vars
        return "(lambda %s: %s)" % (", ".join(pnames + caps) if (pnames or caps) else "", b)

    def e_fh(self, n):
        name = n[1]
        return self.m.function_ref(name, self)

    def e_field(self, n, nargout=None, spread=False):
        base, name = n[1], n[2]
        if base == ("id", "containers") and name == "Map":
            return "mrt.containers_Map"
        if base[0] == "id" and base[1] in ("java", "matlab", "datetime") and base[1] not in self.vars:
            raise UnsupportedError("'%s.*' (Java / package) calls are not supported" % base[1])
        return "mrt.field(%s, %r)" % (self.E(base), name)

    def e_dynfield(self, n):
        return "mrt.field(%s, %s)" % (self.E(n[1]), self.E(n[2]))

    def e_cell(self, n, nargout=None, spread=False):
        base, args = n[1], n[2]
        B = self.E(base)
        subs = self.subs(B, args, [])
        if self.is_cs(n):
            return ("*mrt.cellcs(%s, %s)" if spread else "mrt.cellcs(%s, %s)") % (B, subs)
        return "mrt.cellget(%s, %s)" % (B, subs)

    def e_call(self, n, nargout=None, spread=False):
        base, args = n[1], n[2]
        if base[0] == "id" and base[1] not in self.vars:
            return self.call_named(base[1], args, nargout)
        if base == ("field", ("id", "containers"), "Map"):
            return "mrt.containers_Map(%s)" % self.arg_list(args)
        if base[0] == "id" and base[1] in self.vars:
            B = pyname(base[1])
        else:
            B = self.E(base)
        subs = self.subs(B, args, [])
        if len(args) == 1:
            return "mrt.ix1(%s, %s)" % (B, subs.rstrip(","))
        if len(args) == 2:
            return "mrt.ix2(%s, %s)" % (B, subs)
        return "mrt.index(%s, %s)" % (B, subs)

    def call_named(self, name, args, nargout):
        a = self.arg_list(args) if args else ""
        extra = ""
        if nargout is not None and nargout > 1:
            extra = "nargout=%d" % nargout
        kind, ref = self.m.resolve(name)
        if kind == "builtin":
            if extra and name not in NARGOUT_BUILTINS:
                raise UnsupportedError("'%s' with %d outputs is not supported" % (name, nargout))
            if name in ("nargin", "nargout"):
                return name
        sep = ", " if (a and extra) else ""
        return "%s(%s%s%s)" % (ref, a, sep, extra)


class ModuleGen:
    """One .m file -> one Python module."""

    def __init__(self, name, funcs, src_lines, public, builtin_check):
        self.name = name
        self.funcs = funcs
        self.src = src_lines
        self.public = public                      # set of public function names (all files)
        self.builtin_check = builtin_check
        self.local = {f["name"] for f in funcs[1:]}
        for f in funcs[1:]:
            f["local"] = True

    def is_builtin(self, n):
        return n in CONSTANTS or self.builtin_check(n)

    def pyfunc_name(self, name, local=False):
        return "_l_" + name if local else name

    def resolve(self, name):
        if name in self.local:
            return "local", "_l_" + name
        if name in self.public:
            return "public", name
        if name in CONSTANTS and name in ("true", "false", "pi", "eps", "inf", "Inf", "nan", "NaN", "realmax", "realmin"):
            return "builtin", "mrt.b_" + name.lower().replace("inf", "inf")
        if self.builtin_check(name):
            return "builtin", "mrt.b_" + name
        if name in ("i", "j"):
            return "builtin", "mrt.b_imagunit"
        raise UnsupportedError("function '%s' is not defined in the MATLAB core and has no Python equivalent in "
                               "noisebox/mrt.py" % name)

    def function_ref(self, name, fg):
        if "." in name:
            raise UnsupportedError("function handle @%s" % name)
        return self.resolve(name)[1]

    def source_line(self, line):
        if line is None or line < 1 or line > len(self.src):
            return ""
        t = self.src[line - 1].strip()
        return t[:150]

    def docstring(self, fn):
        """Leading comment block (the MATLAB help text) as a Python docstring."""
        i = fn["line"]                                # line index of the line after `function ...`
        out = []
        while i < len(self.src):
            t = self.src[i].strip()
            if t.startswith("%"):
                out.append(re.sub(r"^%+ ?", "", t))
                i += 1
            else:
                break
        if not out:
            return ""
        text = "\n".join(out).replace("\\", "\\\\").replace('"""', "'''")
        return '"""' + text + '\n    """'

    def generate(self, header):
        out = [header, "from noisebox import mrt", "", ""]
        for f in self.funcs:
            g = FunctionGen(f, self)
            out.extend(g.generate())
            out.append("")
            out.append("")
        return "\n".join(out)
