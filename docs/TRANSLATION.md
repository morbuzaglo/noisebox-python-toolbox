# How the MATLAB core becomes Python

`m2py/` reads each `.m` file (lexer + parser for the numerical subset of MATLAB) and writes one Python module per
file. The output is a *literal* translation: no formula is rewritten. MATLAB semantics come from `noisebox/mrt.py`.

## Representation

| MATLAB | Python |
|---|---|
| number, logical | `float` / `bool` (a 1-by-1 array is equivalent) |
| array | 2-D `numpy.ndarray` (always two dimensions, MATLAB shapes: `1:3` is 1x3, `x(:)` is a column) |
| char array | `str` |
| struct / struct array | `Struct` (dict) / `SArr` |
| cell array | `Cell` (list in column-major order + 2-D shape) |
| `containers.Map` | `MMap` |
| function handle | Python function (variables captured by value, like MATLAB) |
| error / `catch ME` | `MatlabError` (identifier, message) / `ME.identifier`, `ME.message` |

* 1-based indexing, `end`, logical masks, growth (`x(end+1) = v`), deletion (`x(i) = []`), 2-D cell indexing.
* Value semantics: assigning or passing a struct/array never changes the original (copy-on-write for field
  assignment, copies where an array is modified in place).
* `nargin`, `nargout`, `varargin`, `varargout`, outputs that are not assigned when the caller does not ask for them.
* Division by zero gives `Inf`/`NaN`, `round` rounds half away from zero, `mod` follows the divisor, `max/min`
  ignore NaN, `sort` puts NaN last, `unique` returns sorted values.

## Known differences from MATLAB (none affects the current core; the comparison would show it if one did)

* Only up to two array dimensions (`cat(3, ...)`, `zeros(2,2,2)` stop the translation).
* Integer classes saturate only at conversion (`int32(x)`); integer arithmetic is done in double.
* Complex results of `sqrt(-1)`-like expressions are NaN for arrays (MATLAB returns complex).
* `a + b` for two logical *arrays* is a logical OR in NumPy (MATLAB gives 0/1/2): use `double(a) + double(b)`.
* `global`, `persistent`, `eval`, `evalin`, `inputname`, classes, Java/COM calls, file and audio I/O are not translated.
* Printing without a semicolon does nothing.
* Strings: `==` between strings of different length is `False` instead of an error.
* Numbers match MATLAB to rounding (relative 1e-9 in the comparison; typically 1e-13).

## Files

* `m2py/mparser.py` lexer and parser; `m2py/codegen.py` Python code generator; `m2py/export.py` driver
  (`--core`, `--out`, `--overrides`, `--accel`, `--require`; `--promote a b`; `--stamp-accel core accel`).
* `matlab/required_functions.txt` functions the tools call. If one cannot be translated the export stops.
* `noisebox/core_py/manifest.json` function list with inputs / outputs / md5, accelerated functions, notes.
* **Accelerators** (`matlab/python_accel/<name>.py`): line `# MATLAB-MD5: <md5>` = md5 of the `.m` file (line endings
  ignored) they were written for. After you have verified a new accelerator with `nb_export_python`, run
  `python m2py/export.py --stamp-accel matlab/core matlab/python_accel` to record the current md5.
* **Overrides** (`matlab/python_overrides/<name>.py`): always replace the translation of that function (e.g.
  `nb_fingerprint`, which uses Java in MATLAB).
