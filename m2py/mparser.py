"""MATLAB lexer and parser (the subset used for numerical code).

Produces a small tuple-based AST. Anything outside the supported subset raises MParseError with
file and line, so the exporter never silently generates wrong code.
"""
import re

KEYWORDS = {"function", "end", "if", "elseif", "else", "for", "while", "switch", "case", "otherwise",
            "try", "catch", "return", "break", "continue", "global", "persistent", "parfor"}


class MParseError(Exception):
    def __init__(self, msg, line=None):
        super().__init__("line %s: %s" % (line, msg) if line else msg)
        self.line = line


class Tok:
    __slots__ = ("k", "v", "line", "sp")

    def __init__(self, k, v, line, sp=False):
        self.k, self.v, self.line, self.sp = k, v, line, sp

    def __repr__(self):
        return "Tok(%s,%r,l%d)" % (self.k, self.v, self.line)


_NUM = re.compile(r"(?:\d+\.?\d*|\.\d+)(?:[eEdD][+-]?\d+)?[ij]?")
_ID = re.compile(r"[A-Za-z_]\w*")
_OPS3 = ("...",)
_OPS2 = ("==", "~=", "!=", "<=", ">=", "&&", "||", ".*", "./", ".\\", ".^", ".'")
_OPS1 = "+-*/\\^<>=&|~!:,;()[]{}@.'"


def _value_end(t):
    """Can the token end a value (so that a following ' is a transpose / whitespace may separate elements)?"""
    if t is None:
        return False
    return t.k in ("num", "str", "id", "endidx") or (t.k == "op" and t.v in (")", "]", "}", "'", ".'"))


def lex(text):
    toks = []
    i, n, line = 0, len(text), 1
    stack = []                       # open brackets: '(' '[' '{'
    sp = False
    at_line_start = True
    while i < n:
        c = text[i]
        # ---- block comments %{ ... %} on their own lines
        if at_line_start:
            m = re.match(r"[ \t]*%\{[ \t]*\r?\n", text[i:])
            if m:
                depth = 0
                j = i
                while j < n:
                    eol = text.find("\n", j)
                    eol = n if eol < 0 else eol
                    ln = text[j:eol].strip()
                    if ln == "%{":
                        depth += 1
                    elif ln == "%}":
                        depth -= 1
                    line += 1
                    j = eol + 1
                    if depth == 0:
                        break
                i = j
                continue
        if c in " \t\r":
            i += 1
            sp = True
            continue
        if c == "\n":
            top = stack[-1] if stack else None
            if top in ("[", "{"):
                toks.append(Tok("op", ";", line, sp))
            elif not stack:
                toks.append(Tok("nl", "\n", line, sp))
            i += 1
            line += 1
            sp = True
            at_line_start = True
            continue
        at_line_start = False
        if c == "%":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if text.startswith("...", i):
            while i < n and text[i] != "\n":
                i += 1
            i += 1
            line += 1
            sp = True
            continue
        top = stack[-1] if stack else None
        prev = toks[-1] if toks else None
        in_mat = top in ("[", "{")
        # ---- element separator by whitespace inside [] / {}
        if in_mat and sp and _value_end(prev):
            nxt = text[i + 1] if i + 1 < n else ""
            starts = (c.isalnum() or c == "_" or c in "'\"([{@" or (c == "." and nxt.isdigit()) or
                      (c in "~!" and nxt != "=") or (c in "+-" and nxt not in " \t=" and nxt != ""))
            if starts and not (c in "+-" and nxt in "+-" and False):
                toks.append(Tok("op", ",", line, False))
        # ---- numbers
        if c.isdigit() or (c == "." and i + 1 < n and text[i + 1].isdigit() and not (_value_end(prev) and not sp)):
            m = _NUM.match(text, i)
            s = m.group(0)
            if "." in s and s.endswith(".") is False and False:
                pass
            # "1.*x" / "1./x" / "1.^x" / "1.'": the dot belongs to the operator
            mm = re.match(r"\d+\.(?=[*/\\^'])", text[i:])
            if mm:
                s = mm.group(0)[:-1]
            toks.append(Tok("num", s, line, sp))
            i += len(s)
            sp = False
            continue
        # ---- identifiers / keywords
        if c.isalpha() or c == "_":
            m = _ID.match(text, i)
            s = m.group(0)
            after_dot = prev is not None and prev.k == "op" and prev.v == "." and not sp
            if s in KEYWORDS and not after_dot:
                if s == "end" and stack:
                    toks.append(Tok("endidx", s, line, sp))
                else:
                    toks.append(Tok("kw", s, line, sp))
            else:
                toks.append(Tok("id", s, line, sp))
            i += len(s)
            sp = False
            continue
        # ---- strings and transpose
        if c == "'":
            transpose = _value_end(prev) and not (in_mat and sp)
            if transpose:
                toks.append(Tok("op", "'", line, sp))
                i += 1
                sp = False
                continue
            j = i + 1
            buf = []
            while True:
                if j >= n or text[j] == "\n":
                    raise MParseError("unterminated string", line)
                if text[j] == "'":
                    if j + 1 < n and text[j + 1] == "'":
                        buf.append("'")
                        j += 2
                        continue
                    break
                buf.append(text[j])
                j += 1
            toks.append(Tok("str", "".join(buf), line, sp))
            i = j + 1
            sp = False
            continue
        if c == '"':
            j = i + 1
            buf = []
            while True:
                if j >= n or text[j] == "\n":
                    raise MParseError("unterminated string", line)
                if text[j] == '"':
                    if j + 1 < n and text[j + 1] == '"':
                        buf.append('"')
                        j += 2
                        continue
                    break
                buf.append(text[j])
                j += 1
            toks.append(Tok("str", "".join(buf), line, sp))
            i = j + 1
            sp = False
            continue
        # ---- operators
        two = text[i:i + 2]
        if two in _OPS2:
            op = {"~=": "~=", "!=": "~="}.get(two, two)
            toks.append(Tok("op", op, line, sp))
            i += 2
            sp = False
            continue
        if c in _OPS1:
            if c in "([{":
                stack.append(c)
            elif c in ")]}":
                if not stack:
                    raise MParseError("unbalanced bracket", line)
                stack.pop()
            toks.append(Tok("op", c, line, sp))
            i += 1
            sp = False
            continue
        raise MParseError("unexpected character %r" % c, line)
    toks.append(Tok("nl", "\n", line))
    toks.append(Tok("eof", "", line))
    return toks


class Parser:
    def __init__(self, toks):
        self.t = toks
        self.p = 0

    # ---- token helpers
    @property
    def cur(self):
        return self.t[self.p]

    def peek(self, k=1):
        return self.t[min(self.p + k, len(self.t) - 1)]

    def is_op(self, v):
        c = self.cur
        return c.k == "op" and c.v == v

    def is_kw(self, v):
        c = self.cur
        return c.k == "kw" and c.v == v

    def eat_op(self, v):
        if not self.is_op(v):
            raise MParseError("expected %r, found %r" % (v, self.cur.v), self.cur.line)
        self.p += 1

    def skip_seps(self):
        while self.cur.k == "nl" or (self.cur.k == "op" and self.cur.v in (";", ",")):
            self.p += 1

    # ---- file
    def parse_file(self):
        funcs = []
        self.skip_seps()
        while self.cur.k != "eof":
            if not self.is_kw("function"):
                raise MParseError("only function files are supported (script statement found)", self.cur.line)
            funcs.append(self.parse_function())
            self.skip_seps()
        if not funcs:
            raise MParseError("no function found")
        return funcs

    def parse_function(self):
        line = self.cur.line
        self.p += 1                                             # function
        outs = []
        if self.is_op("["):
            self.p += 1
            while not self.is_op("]"):
                if self.is_op(","):
                    self.p += 1
                    continue
                outs.append(self.expect_id())
            self.p += 1
            self.eat_op("=")
            name = self.expect_id()
        else:
            name = self.expect_id()
            if self.is_op("="):
                self.p += 1
                outs = [name]
                name = self.expect_id()
        while self.is_op("."):                                  # package-style names are not needed
            self.p += 1
            name += "." + self.expect_id()
        params = []
        if self.is_op("("):
            self.p += 1
            while not self.is_op(")"):
                if self.is_op(","):
                    self.p += 1
                    continue
                if self.is_op("~"):
                    self.p += 1
                    params.append("~")
                else:
                    params.append(self.expect_id())
            self.p += 1
        body = self.parse_block(("end", "function"))
        if self.is_kw("end"):
            self.p += 1
        return {"name": name, "outs": outs, "params": params, "body": body, "line": line}

    def expect_id(self):
        c = self.cur
        if c.k != "id":
            raise MParseError("identifier expected, found %r" % (c.v,), c.line)
        self.p += 1
        return c.v

    # ---- statements
    def parse_block(self, stops):
        out = []
        while True:
            self.skip_seps()
            c = self.cur
            if c.k == "eof":
                if "eof" in stops or "end" in stops or "function" in stops:
                    return out
                raise MParseError("unexpected end of file", c.line)
            if c.k == "kw" and c.v in stops:
                return out
            out.append(self.parse_stmt())

    def end_stmt(self):
        c = self.cur
        if c.k == "nl" or c.k == "eof":
            return
        if c.k == "op" and c.v in (";", ","):
            return
        raise MParseError("unexpected %r at end of statement" % (c.v,), c.line)

    def parse_stmt(self):
        c = self.cur
        line = c.line
        if c.k == "kw":
            v = c.v
            if v == "if":
                return self.parse_if()
            if v in ("for", "parfor"):
                return self.parse_for()
            if v == "while":
                self.p += 1
                cond = self.parse_expr()
                body = self.parse_block(("end",))
                self.p += 1
                return ("while", cond, body, line)
            if v == "switch":
                return self.parse_switch()
            if v == "try":
                return self.parse_try()
            if v in ("return", "break", "continue"):
                self.p += 1
                return (v, line)
            if v in ("global", "persistent"):
                raise MParseError("'%s' variables are not supported" % v, line)
            raise MParseError("unexpected keyword %r" % v, line)
        # multi-assignment [a,b] = ...
        if c.k == "op" and c.v == "[" and self.is_multi_assign():
            self.p += 1
            lhs = []
            while not self.is_op("]"):
                if self.is_op(","):
                    self.p += 1
                    continue
                if self.is_op("~"):
                    self.p += 1
                    lhs.append(("tilde",))
                else:
                    lhs.append(self.parse_postfix())
            self.p += 1
            self.eat_op("=")
            rhs = self.parse_expr()
            self.end_stmt()
            return ("massign", lhs, rhs, line)
        e = self.parse_expr()
        if self.is_op("="):
            self.p += 1
            rhs = self.parse_expr()
            self.end_stmt()
            self.check_lvalue(e, line)
            return ("assign", e, rhs, line)
        self.end_stmt()
        return ("expr", e, line)

    def is_multi_assign(self):
        depth, q = 0, self.p
        while True:
            t = self.t[q]
            if t.k == "eof" or t.k == "nl":
                return False
            if t.k == "op" and t.v in ("[", "(", "{"):
                depth += 1
            elif t.k == "op" and t.v in ("]", ")", "}"):
                depth -= 1
                if depth == 0:
                    nx = self.t[q + 1]
                    return nx.k == "op" and nx.v == "="
            q += 1

    def check_lvalue(self, e, line):
        k = e[0]
        if k == "id":
            return
        if k in ("call", "cell", "field", "dynfield"):
            self.check_lvalue(e[1], line)
            return
        raise MParseError("invalid assignment target", line)

    def parse_if(self):
        line = self.cur.line
        self.p += 1
        arms = []
        cond = self.parse_expr()
        body = self.parse_block(("elseif", "else", "end"))
        arms.append((cond, body))
        els = None
        while True:
            if self.is_kw("elseif"):
                self.p += 1
                cond = self.parse_expr()
                body = self.parse_block(("elseif", "else", "end"))
                arms.append((cond, body))
            elif self.is_kw("else"):
                self.p += 1
                els = self.parse_block(("end",))
            else:
                break
        if not self.is_kw("end"):
            raise MParseError("'end' expected for if", line)
        self.p += 1
        return ("if", arms, els, line)

    def parse_for(self):
        line = self.cur.line
        self.p += 1
        paren = False
        if self.is_op("("):
            paren = True
            self.p += 1
        var = self.expect_id()
        self.eat_op("=")
        rng = self.parse_expr()
        if paren and self.is_op(")"):
            self.p += 1
        body = self.parse_block(("end",))
        self.p += 1
        return ("for", var, rng, body, line)

    def parse_switch(self):
        line = self.cur.line
        self.p += 1
        subj = self.parse_expr()
        self.skip_seps()
        cases, default = [], None
        while True:
            self.skip_seps()
            if self.is_kw("case"):
                self.p += 1
                val = self.parse_expr()
                body = self.parse_block(("case", "otherwise", "end"))
                cases.append((val, body))
            elif self.is_kw("otherwise"):
                self.p += 1
                default = self.parse_block(("case", "otherwise", "end"))
            else:
                break
        if not self.is_kw("end"):
            raise MParseError("'end' expected for switch", line)
        self.p += 1
        return ("switch", subj, cases, default, line)

    def parse_try(self):
        line = self.cur.line
        self.p += 1
        body = self.parse_block(("catch", "end"))
        var, handler = None, []
        if self.is_kw("catch"):
            self.p += 1
            if self.cur.k == "id" and self.peek().k in ("nl", "eof") or \
                    (self.cur.k == "id" and self.peek().k == "op" and self.peek().v == ";"):
                var = self.cur.v
                self.p += 1
            handler = self.parse_block(("end",))
        self.p += 1
        return ("try", body, var, handler, line)

    # ---- expressions
    def parse_expr(self):
        return self.parse_oror()

    def parse_oror(self):
        a = self.parse_andand()
        while self.is_op("||"):
            self.p += 1
            a = ("bin", "||", a, self.parse_andand())
        return a

    def parse_andand(self):
        a = self.parse_or()
        while self.is_op("&&"):
            self.p += 1
            a = ("bin", "&&", a, self.parse_or())
        return a

    def parse_or(self):
        a = self.parse_and()
        while self.is_op("|"):
            self.p += 1
            a = ("bin", "|", a, self.parse_and())
        return a

    def parse_and(self):
        a = self.parse_cmp()
        while self.is_op("&"):
            self.p += 1
            a = ("bin", "&", a, self.parse_cmp())
        return a

    def parse_cmp(self):
        a = self.parse_range()
        while self.cur.k == "op" and self.cur.v in ("<", "<=", ">", ">=", "==", "~="):
            op = self.cur.v
            self.p += 1
            a = ("bin", op, a, self.parse_range())
        return a

    def parse_range(self):
        a = self.parse_add()
        if self.is_op(":") and not self._colon_ends_arg():
            self.p += 1
            b = self.parse_add()
            if self.is_op(":") and not self._colon_ends_arg():
                self.p += 1
                c = self.parse_add()
                return ("range", a, b, c)                       # a:step:c
            return ("range", a, None, b)
        return a

    def _colon_ends_arg(self):
        nx = self.peek()
        return nx.k == "op" and nx.v in (")", ",")

    def parse_add(self):
        a = self.parse_mul()
        while self.cur.k == "op" and self.cur.v in ("+", "-"):
            op = self.cur.v
            self.p += 1
            a = ("bin", op, a, self.parse_mul())
        return a

    def parse_mul(self):
        a = self.parse_unary()
        while self.cur.k == "op" and self.cur.v in ("*", "/", ".*", "./", "\\", ".\\"):
            op = self.cur.v
            self.p += 1
            a = ("bin", op, a, self.parse_unary())
        return a

    def parse_unary(self):
        c = self.cur
        if c.k == "op" and c.v in ("-", "+", "~", "!"):
            self.p += 1
            return ("un", "~" if c.v == "!" else c.v, self.parse_unary())
        return self.parse_power()

    def parse_power(self):
        a = self.parse_postfix()
        while self.cur.k == "op" and self.cur.v in ("^", ".^"):
            op = self.cur.v
            self.p += 1
            a = ("bin", op, a, self.parse_power_operand())
        return a

    def parse_power_operand(self):
        c = self.cur
        if c.k == "op" and c.v in ("-", "+", "~", "!"):
            self.p += 1
            return ("un", "~" if c.v == "!" else c.v, self.parse_power_operand())
        return self.parse_postfix()

    def parse_args(self, close):
        args = []
        while not self.is_op(close):
            if self.is_op(","):
                self.p += 1
                continue
            if self.is_op(":") and self._colon_ends_arg_or(close):
                self.p += 1
                args.append(("colon",))
            else:
                args.append(self.parse_expr())
        self.p += 1
        return args

    def _colon_ends_arg_or(self, close):
        nx = self.peek()
        return nx.k == "op" and nx.v in (close, ",")

    def parse_postfix(self):
        a = self.parse_primary()
        while True:
            c = self.cur
            if c.k != "op":
                break
            if c.v == "(" and not (self._in_matrix_gap(c)):
                self.p += 1
                a = ("call", a, self.parse_args(")"))
            elif c.v == "{" and not (self._in_matrix_gap(c)):
                self.p += 1
                a = ("cell", a, self.parse_args("}"))
            elif c.v == "." and not c.sp:
                nx = self.peek()
                if nx.k == "id":
                    self.p += 2
                    a = ("field", a, nx.v)
                elif nx.k == "op" and nx.v == "(":
                    self.p += 2
                    e = self.parse_expr()
                    self.eat_op(")")
                    a = ("dynfield", a, e)
                else:
                    break
            elif c.v == "'":
                self.p += 1
                a = ("post", "'", a)
            elif c.v == ".'":
                self.p += 1
                a = ("post", ".'", a)
            else:
                break
        return a

    def _in_matrix_gap(self, c):
        return False                                            # the lexer already inserted commas

    def parse_primary(self):
        c = self.cur
        if c.k == "num":
            self.p += 1
            s = c.v
            if s[-1] in "ij":
                return ("num", complex(0, float(s[:-1].replace("d", "e").replace("D", "e"))))
            return ("num", float(s.replace("d", "e").replace("D", "e")))
        if c.k == "str":
            self.p += 1
            return ("str", c.v)
        if c.k == "id":
            self.p += 1
            return ("id", c.v)
        if c.k == "endidx":
            self.p += 1
            return ("end",)
        if c.k == "op":
            if c.v == "(":
                self.p += 1
                e = self.parse_expr()
                self.eat_op(")")
                return ("paren", e)
            if c.v == "[":
                self.p += 1
                return ("mat", self.parse_rows("]"))
            if c.v == "{":
                self.p += 1
                return ("cellmat", self.parse_rows("}"))
            if c.v == "@":
                self.p += 1
                if self.is_op("("):
                    self.p += 1
                    params = []
                    while not self.is_op(")"):
                        if self.is_op(","):
                            self.p += 1
                            continue
                        if self.is_op("~"):
                            self.p += 1
                            params.append("~")
                        else:
                            params.append(self.expect_id())
                    self.p += 1
                    body = self.parse_expr()
                    return ("anon", params, body)
                name = self.expect_id()
                while self.is_op(".") and self.peek().k == "id":
                    self.p += 1
                    name += "." + self.expect_id()
                return ("fh", name)
            if c.v == ":":
                self.p += 1
                return ("colon",)
        raise MParseError("unexpected %r" % (c.v,), c.line)

    def parse_rows(self, close):
        rows, row = [], []
        while True:
            if self.is_op(close):
                self.p += 1
                break
            if self.is_op(";"):
                self.p += 1
                if row:
                    rows.append(row)
                row = []
                continue
            if self.is_op(","):
                self.p += 1
                continue
            if self.cur.k in ("eof",):
                raise MParseError("unterminated matrix", self.cur.line)
            if self.cur.k == "nl":
                self.p += 1
                continue
            row.append(self.parse_expr())
        if row:
            rows.append(row)
        return rows


def parse(text):
    return Parser(lex(text)).parse_file()
