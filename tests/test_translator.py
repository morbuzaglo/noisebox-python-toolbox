"""Tests of the MATLAB -> Python translator on small snippets with known MATLAB results (no MATLAB needed).

    propy tests\\test_translator.py
"""
import math
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from m2py.codegen import ModuleGen, UnsupportedError          # noqa: E402
from m2py.mparser import parse, MParseError                    # noqa: E402
from noisebox import mrt                                       # noqa: E402

CHECKS = []


def check(name, ok, detail=""):
    CHECKS.append((name, bool(ok)))
    print("RESULT %s %s %s" % (name, "ok" if ok else "bad", detail))


def build(src, extra_public=()):
    """Translate MATLAB source (one or more functions, the first is public) and return its namespace."""
    funcs = parse(src)
    name = funcs[0]["name"]
    mg = ModuleGen(name, funcs, src.splitlines(), {name} | set(extra_public), lambda n: hasattr(mrt, "b_" + n))
    code = mg.generate("# test")
    ns = {}
    exec(compile(code, name, "exec"), ns)
    return ns


def val(x):
    return np.asarray(x, dtype=float).ravel().tolist() if not isinstance(x, str) else x


def run(name, src, call, expect, tol=1e-12):
    try:
        ns = build(src)
        got = call(ns)
        if isinstance(expect, str):
            ok = got == expect
        else:
            g, e = val(got), val(expect)
            ok = len(g) == len(e) and all((a == b) or (math.isnan(a) and math.isnan(b)) or abs(a - b) <= tol * (1 + abs(b))
                                          for a, b in zip(g, e))
        check(name, ok, "got %r, expected %r" % (got, expect) if not ok else "")
    except Exception as e:                                        # noqa: BLE001
        check(name, False, "%s: %s" % (type(e).__name__, e))


run("loop_and_power", """function r = f(n)
r = 0;
for k = 1:n
    r = r + k^2;
end
end""", lambda ns: ns["f"](4.0), 30)

run("end_growth_delete", """function [a, b, c] = f()
x = [];
for k = 1:5, x(end+1) = k*2; end
a = x(end);
x(2) = [];
b = numel(x);
y = reshape(1:6, 2, 3);
c = y(2, end);
end""", lambda ns: ns["f"](nargout=3), (10, 4, 6))

run("logical_mask_assign", """function s = f()
v = [3 -1 4 -1 5];
v(v < 0) = 0;
s = [sum(v), find(v == 0)];
end""", lambda ns: ns["f"](), [12, 2, 4])

run("row_col_orientation", """function r = f()
a = (1:3)';
b = [a, a*2];
r = [size(b, 1), size(b, 2), b(3, 2)];
end""", lambda ns: ns["f"](), [3, 2, 6])

run("struct_nested_assign", """function r = f()
s.a = 1;
s.b.c = [1 2 3];
s.b.c(2) = 20;
r = sum(s.b.c) + s.a;
end""", lambda ns: ns["f"](), 25)

run("struct_array", """function r = f()
q(2).x = 5;
r = [numel(q), isempty(q(1).x), q(2).x];
end""", lambda ns: ns["f"](), [2, 1, 5])

run("value_semantics_array", """function r = f()
a = [1 2 3];
b = a;
b(1) = 9;
r = [a(1), b(1)];
end""", lambda ns: ns["f"](), [1, 9])

run("value_semantics_struct", """function r = f()
s.x = 1;
t = s;
t.x = 2;
r = [s.x, t.x];
end""", lambda ns: ns["f"](), [1, 2])

run("param_not_modified", """function r = f()
a = [1 2 3];
g(a);
r = a(1);
end
function g(v)
v(1) = 100;
end""", lambda ns: ns["f"](), 1)

run("cell_basics", """function r = f()
c = {1, 'a', [1 2 3]};
c{end+1} = 4;
m = {1 2; 3 4};
r = [numel(c), c{3}(2), size(m, 1), m{2, 1}];
end""", lambda ns: ns["f"](), [4, 2, 2, 3])

run("cell_2d_append_row", """function r = f()
e = {'a', 1};
e(end+1, :) = {'b', 2};
r = [size(e, 1), size(e, 2), e{2, 2}];
end""", lambda ns: ns["f"](), [2, 2, 2])

run("switch_string_and_cell", """function r = f(m)
switch m
    case 'a'
        r = 1;
    case {'b', 'c'}
        r = 2;
    otherwise
        r = 3;
end
end""", lambda ns: [ns["f"]("a"), ns["f"]("c"), ns["f"]("z")], [1, 2, 3])

run("try_catch_identifier", """function r = f()
try
    error('a:b', 'message %d', 3);
catch ME
    r = [ME.identifier, '|', ME.message];
end
end""", lambda ns: ns["f"](), "a:b|message 3")

run("nargin_default", """function r = f(a, b)
if nargin < 2, b = 10; end
r = a + b;
end""", lambda ns: [ns["f"](1.0), ns["f"](1.0, 2.0)], [11, 3])

run("varargin_varargout", """function varargout = f(varargin)
for k = 1:nargout
    varargout{k} = varargin{k} * 2;
end
end""", lambda ns: ns["f"](1.0, 2.0, 3.0, nargout=2), [2, 4])

run("multiple_outputs_subset", """function [a, b, c] = f()
a = 1; b = 2; c = 3;
end""", lambda ns: ns["f"](nargout=2), [1, 2])

run("anonymous_captures_value", """function r = f()
k = 3;
g = @(x) x*k;
k = 5;
r = g(2);
end""", lambda ns: ns["f"](), 6)

run("matrix_algebra", """function r = f()
A = [1 2; 3 4];
B = A*A;
x = A \\ [1; 2];
r = [B(2, 2), sum(sum(A.*A)), x(1), A'(1, 2)];
end""", lambda ns: ns["f"](), [22, 30, 0, 3])

run("sort_max_unique", """function r = f()
[s, i] = sort([3 1 2], 'descend');
[m, k] = max([4 9 2 9]);
u = unique([3 1 3 2 1]);
r = [s, i, m, k, u];
end""", lambda ns: ns["f"](), [3, 2, 1, 1, 3, 2, 9, 2, 1, 2, 3])

run("rounding_and_mod", """function r = f()
r = [round(2.5), round(-2.5), mod(-1, 3), rem(-1, 3), fix(-2.7), floor(-2.7), mod(5, 0)];
end""", lambda ns: ns["f"](), [3, -3, 2, -1, -2, -3, 5])

run("sprintf_formats", """function r = f()
r = sprintf('%d-%s-%5.2f|%g', 3, 'ab', pi, 0.5);
end""", lambda ns: ns["f"](), "3-ab- 3.14|0.5")

run("division_by_zero_and_nan", """function r = f()
a = 1/0;
b = -1/0;
c = 0/0;
r = [a, b, isnan(c)];
end""", lambda ns: ns["f"](), [math.inf, -math.inf, 1])

run("while_break_continue", """function r = f()
r = 0; k = 0;
while true
    k = k + 1;
    if k > 10, break; end
    if mod(k, 2) == 0, continue; end
    r = r + k;
end
end""", lambda ns: ns["f"](), 25)

run("containers_map", """function r = f()
m = containers.Map({'a', 'b'}, {1, 2});
r = [m('b'), isKey(m, 'a'), isKey(m, 'z')];
end""", lambda ns: ns["f"](), [2, 1, 0])

run("interp1_and_cumsum_diff", """function r = f()
r = [interp1([0 1 2], [0 10 40], 1.5), cumsum([1 2 3]), diff([1 4 9])];
end""", lambda ns: ns["f"](), [25, 1, 3, 6, 3, 5])

run("logical_short_circuit_and_not", """function r = f(x)
r = [~isempty(x) && x(1) > 0, ~(1 == 2)];
end""", lambda ns: ns["f"](np.zeros((0, 0))), [0, 1])

run("colon_empty_range_loop", """function r = f()
r = 0;
for k = 5:1
    r = 99;
end
for k = 10:-3:1
    r = r + k;
end
end""", lambda ns: ns["f"](), 22)

run("compare_strings_and_isfield", """function r = f()
s = struct('a', 1);
r = [isfield(s, 'a'), isfield(s, 'b'), strcmp('x', 'x'), strcmp('x', 'y')];
end""", lambda ns: ns["f"](), [1, 0, 1, 0])

run("local_function_call", """function r = f(x)
r = helper(x) + 1;
end
function y = helper(x)
y = x * 2;
end""", lambda ns: ns["f"](4.0), 9)

# the translator must refuse what it does not know instead of guessing
try:
    build("function r = f()\nr = nonexistent_function_xyz(1);\nend")
    check("unknown_function_is_reported", False)
except UnsupportedError as e:
    check("unknown_function_is_reported", "nonexistent_function_xyz" in str(e))
try:
    parse("function r = f()\nglobal G\nr = 1;\nend")
    check("global_is_reported", False)
except MParseError as e:
    check("global_is_reported", "global" in str(e))

bad = [c for c in CHECKS if not c[1]]
print("\n%d checks, %d failed" % (len(CHECKS), len(bad)))
sys.exit(1 if bad else 0)
