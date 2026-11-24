"""MATLAB runtime for the code generated from matlab/core/*.m (see m2py/).

The generated modules do not contain any acoustics written by hand: every formula is a literal translation of
the .m file. This module only provides the MATLAB *semantics* the translation needs:

* every array is a 2-D numpy array (column-major thinking), scalars may be Python/NumPy scalars (a 1x1 array is
  equivalent to a scalar everywhere);
* 1-based indexing, `end`, logical masks, growth on assignment, deletion with [];
* struct (Struct / SArr), cell (Cell), containers.Map (MMap), strings (str);
* the MATLAB built-in functions the core uses, as `b_<name>`;
* MATLAB error / try-catch behaviour (MatlabError).

Behaviour that differs from MATLAB is listed in docs/TRANSLATION.md.
"""
import builtins as _bi
import math
import re
import time

import numpy as np

np.seterr(all="ignore")


# --------------------------------------------------------------------------- basic types
class MatlabError(Exception):
    def __init__(self, identifier, message):
        super().__init__(message)
        self.identifier = identifier or ""
        self.message = message


class _NoVal:
    """Value of an output / variable that was never assigned."""
    __slots__ = ()

    def __repr__(self):
        return "<unassigned>"

    def __bool__(self):
        return False


NOVAL = _NoVal()
UNSET = _NoVal()                       # argument not supplied by the caller (for nargin)


class _Colon:
    __slots__ = ()

    def __repr__(self):
        return ":"


COLON = _Colon()


class Struct(dict):
    """Scalar struct. Fields keep their creation order."""
    __slots__ = ()


class SArr:
    """Struct array (anything but 1x1)."""
    __slots__ = ("items", "fields", "shape")

    def __init__(self, items=(), fields=(), shape=None):
        self.items = list(items)
        self.fields = list(fields)
        self.shape = shape if shape is not None else ((1, len(self.items)) if self.items else (0, 0))


class Cell(list):
    """Cell array: a flat list in column-major order plus its 2-D shape (`sh`; `col` marks an N-by-1 cell)."""
    __slots__ = ("col", "sh")

    def __init__(self, it=(), col=False, shape=None):
        super().__init__(it)
        self.col = col
        self.sh = shape


def cshape(C):
    n = _bi.len(C)
    sh = C.sh
    if sh is not None and sh[0] * sh[1] == n:
        return sh
    if n == 0:
        return (0, 1) if C.col else (0, 0)
    return (n, 1) if C.col else (1, n)


def _cell_resize(C, R, K):
    """Grow a cell to R-by-K (new elements are []), keeping the position of the existing ones."""
    r, c = cshape(C)
    if (R, K) == (r, c):
        return C
    new = [np.zeros((0, 0)) for _ in range(R * K)]
    for j in range(c):
        for i in range(r):
            new[i + j * R] = C[i + j * r]
    C[:] = new
    C.sh = (R, K)
    C.col = K == 1 and R != 1
    return C


class CS(list):
    """A comma-separated list produced by c{:} or s.f on a struct array."""
    __slots__ = ()


class MMap:
    """containers.Map (a handle object: not copied)."""

    def __init__(self, keys=None, values=None, numeric=None):
        self.d = {}
        self.numeric = numeric
        if keys is not None:
            if isinstance(keys, (Cell, list)):
                ks = list(keys)
                vs = list(values) if isinstance(values, (Cell, list)) else [values] * len(ks)
            elif isinstance(keys, str):
                ks, vs = [keys], [values]
            else:
                ks = list(np.asarray(keys).ravel(order="F"))
                vs = list(values) if isinstance(values, (Cell, list)) else [values] * len(ks)
            if len(ks) != len(vs):
                raise MatlabError("MATLAB:Containers:Map:NumKeysNotEqualNumValues",
                                  "The number of keys and values must match.")
            for k, v in zip(ks, vs):
                self.d[self._key(k)] = v
            if ks:
                self.numeric = not isinstance(ks[0], str)

    @staticmethod
    def _key(k):
        return k if isinstance(k, str) else float(_sc(k))


# --------------------------------------------------------------------------- small helpers
def _sc(x):
    t = type(x)
    if t is float or t is int or t is np.float64 or t is bool or t is np.bool_:
        return x
    if isinstance(x, np.ndarray):
        if x.size != 1:
            raise MatlabError("MATLAB:nonscalar", "A scalar value is required here.")
        return x.item()
    if isinstance(x, (np.integer, np.floating)):
        return x.item()
    return x


def asarr(x):
    """Any numeric-like value -> 2-D ndarray."""
    if type(x) is np.ndarray:
        if x.ndim == 2:
            return x
        if x.ndim == 0:
            return x.reshape(1, 1)
        if x.ndim == 1:
            return x.reshape(1, -1)
        return x
    if isinstance(x, (bool, np.bool_)):
        return np.array([[bool(x)]])
    if isinstance(x, (int, float, complex, np.number)):
        return np.array([[x]])
    if isinstance(x, str):
        return np.array([[ord(c) for c in x]], dtype=float).reshape(1, len(x))
    if isinstance(x, (list, tuple)):
        if _bi.len(x) == 0:
            return np.zeros((0, 0))
        return np.asarray(x).reshape(1, -1)
    if x is NOVAL or x is UNSET:
        raise MatlabError("MATLAB:UndefinedFunction", "Unrecognized variable or unassigned output.")
    raise MatlabError("MATLAB:badtype", "Operation not supported for %s." % type(x).__name__)


def S(x):
    """1x1 array -> scalar (others unchanged)."""
    if type(x) is np.ndarray and x.size == 1:
        return x.reshape(()).item() if x.dtype != bool else bool(x.reshape(()))
    return x


def _isscalarlike(x):
    t = type(x)
    if t is float or t is int or t is bool or t is np.float64 or t is np.bool_:
        return True
    return t is np.ndarray and x.size == 1


def truth(x):
    if x is True or x is False:
        return x
    t = type(x)
    if t is float or t is int or t is np.float64 or t is np.bool_:
        return bool(x)
    if t is np.ndarray:
        return x.size > 0 and bool(x.all())
    if t is str:
        return _bi.len(x) > 0
    if x is NOVAL:
        raise MatlabError("MATLAB:UndefinedFunction", "Unrecognized variable or unassigned output.")
    return bool(x)


def copy(x):
    t = type(x)
    if t is np.ndarray:
        return x.copy()
    if t is Struct:
        return Struct((k, copy(v)) for k, v in x.items())
    if t is Cell:
        r = Cell((copy(v) for v in x), x.col)
        return r
    if t is SArr:
        return SArr([copy(i) for i in x.items], x.fields, x.shape)
    return x


def copy1(x):
    """Shallow copy of a struct (its fields stay shared)."""
    t = type(x)
    if t is Struct:
        return Struct(x)
    if t is SArr:
        return SArr(list(x.items), x.fields, x.shape)
    if t is np.ndarray:
        return x.copy()
    if t is Cell:
        return Cell(x, x.col)
    return x


def make_error(identifier, message):
    return MatlabError(identifier, message)


def to_ME(e):
    """Exception -> the MException-like struct that `catch ME` sees."""
    if isinstance(e, MatlabError):
        return Struct(identifier=e.identifier, message=e.message, stack=Struct())
    return Struct(identifier="python:" + type(e).__name__, message=str(e), stack=Struct())


def nargin_of(*a):
    n = 0
    for v in a:
        if v is UNSET:
            break
        n += 1
    return float(n)


def ret(vals, nargout):
    if nargout <= 1:
        return vals[0]
    return vals[:nargout]


# --------------------------------------------------------------------------- arithmetic
def div(a, b):
    try:
        return a / b
    except ZeroDivisionError:
        return np.divide(np.float64(_sc(a)), np.float64(_sc(b)))
    except TypeError:
        return asarr(a) / asarr(b)


def power(a, b):
    try:
        return a ** b
    except (ZeroDivisionError, OverflowError):
        return np.power(np.float64(_sc(a)), np.float64(_sc(b)))
    except TypeError:
        return asarr(a) ** asarr(b)


def neg(a):
    if type(a) is np.ndarray and a.dtype == bool:
        return -a.astype(float)
    if a is True or a is False or type(a) is np.bool_:
        return -float(a)
    return -a


def not_(a):
    t = type(a)
    if t is np.ndarray:
        return np.logical_not(a)
    return not truth(a) if t is not np.bool_ else bool(np.logical_not(a))


def land(a, b):
    if type(a) is np.ndarray or type(b) is np.ndarray:
        return np.logical_and(a, b)
    return bool(a) and bool(b)


def lor(a, b):
    if type(a) is np.ndarray or type(b) is np.ndarray:
        return np.logical_or(a, b)
    return bool(a) or bool(b)


def mtimes(a, b):
    if _isscalarlike(a) or _isscalarlike(b):
        return a * b
    A, B = asarr(a), asarr(b)
    if A.shape[1] != B.shape[0]:
        raise MatlabError("MATLAB:innerdim", "Incorrect dimensions for matrix multiplication.")
    return A @ B


def mrdivide(a, b):
    if _isscalarlike(b):
        return div(a, b)
    A, B = asarr(a), asarr(b)
    return np.linalg.lstsq(B.T, A.T, rcond=None)[0].T


def mldivide(a, b):
    if _isscalarlike(a):
        return div(b, a)
    A, B = asarr(a), asarr(b)
    if A.shape[0] == A.shape[1]:
        return np.linalg.solve(A, B)
    return np.linalg.lstsq(A, B, rcond=None)[0]


def mpower(a, b):
    if _isscalarlike(a) and _isscalarlike(b):
        return power(a, b)
    A = asarr(a)
    return np.linalg.matrix_power(A, int(_sc(b)))


def ctranspose(a):
    if type(a) is np.ndarray:
        if a.ndim == 2:
            return a.conj().T if np.iscomplexobj(a) else a.T
        return a
    if type(a) is Cell:
        return Cell(a, not a.col)
    return a


def transpose(a):
    if type(a) is np.ndarray and a.ndim == 2:
        return a.T
    return a


def colon(a, b, step=1.0):
    a, b, step = _sc(a), _sc(b), _sc(step)
    if step == 0 or (step > 0 and a > b) or (step < 0 and a < b) or a != a or b != b:
        return np.zeros((1, 0))
    n = int(math.floor((b - a) / step * (1 + 4e-16) + 1e-10)) + 1
    return (a + np.arange(n) * step).reshape(1, n)


def for_range(a, b, step=1.0):
    a, b, step = _sc(a), _sc(b), _sc(step)
    if step == 0 or (step > 0 and a > b) or (step < 0 and a < b) or a != a or b != b:
        return
    n = int(math.floor((b - a) / step * (1 + 4e-16) + 1e-10)) + 1
    for i in range(n):
        yield float(a + i * step)


def iter_for(x):
    """Values taken by a `for` loop variable: the columns of x."""
    if type(x) is np.ndarray:
        if x.ndim == 2 and x.shape[0] == 1:
            for v in x[0]:
                yield v
        elif x.size:
            for j in range(x.shape[1]):
                yield x[:, j:j + 1]
        return
    if type(x) is Cell:
        r, c = cshape(x)
        for j in range(c):
            yield Cell((x[i + j * r] for i in range(r)), r != 1, (r, 1))
        return
    if type(x) is SArr:
        for v in x.items:
            yield v
        return
    if type(x) in (list, CS):
        for v in x:
            yield v
        return
    yield x


def sw_eq(subject, case):
    if type(case) is Cell:
        return _bi.any(sw_eq(subject, c) for c in case)
    if isinstance(subject, str) or isinstance(case, str):
        return isinstance(subject, str) and isinstance(case, str) and subject == case
    try:
        return bool(truth(subject == case)) if not (type(subject) is np.ndarray and subject.size == 0) else False
    except Exception:
        return False


# --------------------------------------------------------------------------- concatenation
def _to_cat(x):
    if type(x) is np.ndarray:
        return x if x.ndim == 2 else asarr(x)
    return asarr(x)


def _flat_args(items):
    out = []
    for it in items:
        if type(it) is CS:
            out.extend(it)
        else:
            out.append(it)
    return out


_NUMT = (float, int, np.float64)


def _cat(items, axis):
    # fast path: only real numbers and 2-D float arrays (the usual case in numerical code)
    kinds = 0
    for x in items:
        t = type(x)
        if t is np.ndarray:
            if x.ndim != 2 or x.dtype != np.float64:
                kinds = -1
                break
        elif t not in _NUMT:
            kinds = -1
            break
    if kinds == 0 and items:
        if all(type(x) in _NUMT for x in items):
            return np.array([items], dtype=float) if axis == 1 else np.array([items], dtype=float).T
        parts = [x if type(x) is np.ndarray else np.array([[x]], dtype=float) for x in items]
        parts = [a for a in parts if a.shape != (0, 0)]
        if not parts:
            return np.zeros((0, 0))
        if len(parts) == 1:
            return parts[0].copy()
        try:
            return np.concatenate(parts, axis=axis)
        except ValueError:
            raise MatlabError("MATLAB:catenate:dimensionMismatch",
                              "Dimensions of arrays being concatenated are not consistent.") from None
    items = _flat_args(items)
    if not items:
        return np.zeros((0, 0))
    if _bi.any(isinstance(i, str) for i in items):
        if axis == 1:
            if _bi.all(isinstance(i, str) for i in items):
                return "".join(items)
            return "".join(i if isinstance(i, str) else "".join(chr(int(c)) for c in asarr(i).ravel()) for i in items)
        rows = [i for i in items if not (isinstance(i, str) and i == "")]
        if len({_bi.len(r) for r in rows}) > 1:
            raise MatlabError("MATLAB:catenate:dimensionMismatch", "Dimensions of arrays being concatenated are not consistent.")
        return Cell(rows, True) if False else "\n".join(rows) if False else _char_matrix(rows)
    if _bi.any(type(i) is Cell for i in items):
        parts = []
        for i in items:
            if type(i) is Cell:
                if _bi.len(i) == 0:
                    continue
                parts.append(i)
            elif isinstance(i, np.ndarray) and i.size == 0:
                continue
            else:
                parts.append(Cell([i]))
        if not parts:
            return Cell()
        if axis == 1 and _bi.all(cshape(q)[0] == 1 for q in parts):
            out = Cell()
            for q in parts:
                out.extend(q)
            return out
        if axis == 0 and _bi.all(cshape(q)[1] == 1 for q in parts):
            out = Cell()
            for q in parts:
                out.extend(q)
            out.col = True
            return out
        arrs = []
        for q in parts:
            r, c = cshape(q)
            a = np.empty((r, c), dtype=object)
            for j in range(c):
                for i in range(r):
                    a[i, j] = q[i + j * r]
            arrs.append(a)
        try:
            big = np.concatenate(arrs, axis=axis)
        except ValueError:
            raise MatlabError("MATLAB:catenate:dimensionMismatch",
                              "Dimensions of arrays being concatenated are not consistent.") from None
        R, K = big.shape
        return Cell((big[i, j] for j in range(K) for i in range(R)), K == 1 and R != 1, (R, K))
    if _bi.any(type(i) in (Struct, SArr) for i in items):
        elems, fields = [], None
        for i in items:
            if type(i) is Struct:
                elems.append(i)
            elif type(i) is SArr:
                elems.extend(i.items)
                fields = fields or i.fields
            elif isinstance(i, np.ndarray) and i.size == 0:
                continue
            else:
                raise MatlabError("MATLAB:catenate:structFieldBad", "Cannot concatenate a struct with another type.")
        if elems:
            fields = list(elems[0].keys())
            for e in elems:
                if list(e.keys()) != fields and set(e.keys()) != set(fields):
                    raise MatlabError("MATLAB:catenate:structFieldBad",
                                      "Concatenation operands are not consistent: the field names differ.")
        shape = (1, _bi.len(elems)) if axis == 1 else (_bi.len(elems), 1)
        return SArr(elems, fields or [], shape) if _bi.len(elems) != 1 else elems[0]
    arrs = []
    for i in items:
        a = _to_cat(i)
        if a.shape == (0, 0):
            continue
        arrs.append(a)
    if not arrs:
        return np.zeros((0, 0))
    if _bi.len(arrs) == 1:
        return arrs[0]
    try:
        return np.concatenate(arrs, axis=axis)
    except ValueError:
        raise MatlabError("MATLAB:catenate:dimensionMismatch",
                          "Dimensions of arrays being concatenated are not consistent.") from None


def _char_matrix(rows):
    return rows[0] if _bi.len(rows) == 1 else rows


def hcat(*items):
    return _cat(items, 1)


def vcat(*items):
    return _cat(items, 0)


def mat(rows):
    """Matrix literal from a list of rows (each a list of elements)."""
    if not rows:
        return np.zeros((0, 0))
    if _bi.len(rows) == 1:
        return _cat(rows[0], 1)
    return _cat([_cat(r, 1) for r in rows], 0)


def cellmat(rows):
    """{...} literal."""
    out = Cell()
    if not rows:
        return out
    if _bi.len(rows) == 1:
        for it in _flat_args(rows[0]):
            out.append(it)
        return out
    flat = [_flat_args(r) for r in rows]
    K = _bi.len(flat[0])
    if _bi.any(_bi.len(r) != K for r in flat):
        raise MatlabError("MATLAB:catenate:dimensionMismatch", "Dimensions of arrays being concatenated are not consistent.")
    R = _bi.len(flat)
    for j in range(K):
        for i in range(R):
            out.append(flat[i][j])
    out.col = K == 1
    out.sh = (R, K)
    return out


# --------------------------------------------------------------------------- indexing
def _bad_index(k, n, pos=None):
    if pos is None:
        return MatlabError("MATLAB:badsubscript", "Index exceeds the number of array elements (%d)." % n)
    return MatlabError("MATLAB:badsubscript", "Index in position %d exceeds array bounds (must not exceed %d)." % (pos, n))


def _ix(s, n, pos=None, allow_grow=False):
    """Subscript -> int64 array of zero-based positions."""
    if s is COLON:
        return np.arange(n)
    t = type(s)
    if t is float or t is int or t is np.float64:
        k = int(s)
        if k != s or k < 1:
            raise MatlabError("MATLAB:badsubscript", "Array indices must be positive integers or logical values.")
        if k > n and not allow_grow:
            raise _bad_index(k, n, pos)
        return np.array([k - 1])
    if t is bool or t is np.bool_:
        return np.array([0]) if s else np.zeros(0, dtype=np.int64)
    if isinstance(s, str):
        raise MatlabError("MATLAB:badsubscript", "Subscript indices must be real positive integers or logicals.")
    a = asarr(s)
    if a.dtype == bool:
        flat = a.ravel(order="F")
        if flat.size > n:
            if flat[n:].any():
                raise _bad_index(flat.size, n, pos)
            flat = flat[:n]
        return np.flatnonzero(flat)
    flat = a.ravel(order="F")
    if flat.size == 0:
        return np.zeros(0, dtype=np.int64)
    k = flat.astype(np.int64)
    if not (k == flat).all() or (k < 1).any():
        raise MatlabError("MATLAB:badsubscript", "Array indices must be positive integers or logical values.")
    if not allow_grow and k.max() > n:
        raise _bad_index(int(k.max()), n, pos)
    return k - 1


def _vec_shape(sub, count):
    """Shape of A(sub) for a linear index when the shape follows the subscript."""
    a = sub if type(sub) is np.ndarray else None
    if a is None or a.ndim != 2:
        return (1, count) if count != 1 else (1, 1)
    if a.dtype == bool:
        return (1, count) if a.shape[0] == 1 else (count, 1)
    return a.shape


def index(A, *s):
    t = type(A)
    if t is np.ndarray:
        ns = _bi.len(s)
        if ns == 1:
            i = s[0]
            ti = type(i)
            r, c = A.shape
            if ti is float or ti is np.float64 or ti is int:
                k = int(i)
                if k == i and 1 <= k <= A.size:
                    k -= 1
                    return A[0, k] if r == 1 else (A[k, 0] if c == 1 else A[k % r, k // r])
                _ix(i, A.size)
            if i is COLON:
                return A.reshape(-1, 1, order="F")
            ix = _ix(i, A.size)
            flat = A.ravel(order="F")[ix]
            if type(i) is np.ndarray and i.ndim == 2 and i.dtype != bool and i.shape[0] != 1 and i.shape[1] != 1:
                return flat.reshape(i.shape, order="F")
            is_vec_idx = not (type(i) is np.ndarray and i.ndim == 2 and i.shape[0] != 1 and i.shape[1] != 1 and i.dtype != bool)
            if r == 1 and c != 1 and is_vec_idx:
                shp = (1, flat.size)
            elif c == 1 and r != 1 and is_vec_idx:
                shp = (flat.size, 1)
            elif type(i) is np.ndarray and i.dtype == bool and i.ndim == 2 and i.shape[0] != 1 and i.shape[1] != 1:
                shp = (flat.size, 1)
            else:
                shp = _vec_shape(i, flat.size)
            return S(flat.reshape(shp))
        if ns == 2:
            i, j = s
            ti, tj = type(i), type(j)
            si = ti is float or ti is np.float64 or ti is int
            sj = tj is float or tj is np.float64 or tj is int
            if si and sj:
                a, b = int(i), int(j)
                if a == i and b == j and 1 <= a <= A.shape[0] and 1 <= b <= A.shape[1]:
                    return A[a - 1, b - 1]
            elif si and j is COLON:
                a = int(i)
                if a == i and 1 <= a <= A.shape[0]:
                    return A[a - 1, 0] if A.shape[1] == 1 else A[a - 1:a, :].copy()
            elif i is COLON and sj:
                b = int(j)
                if b == j and 1 <= b <= A.shape[1]:
                    return A[0, b - 1] if A.shape[0] == 1 else A[:, b - 1:b].copy()
            ri = _ix(i, A.shape[0], 1)
            ci = _ix(j, A.shape[1], 2)
            r_ = A[ri[:, None], ci[None, :]]
            return r_[0, 0] if r_.size == 1 else r_
        if ns == 0:
            return A
        extra = s[2:]
        if _bi.all(e is COLON or _sc(e) == 1 for e in extra):
            return index(A, s[0], s[1])
        raise MatlabError("MATLAB:badsubscript", "Arrays with more than two dimensions are not supported.")
    if callable(A):
        return A(*s)
    if t is float or t is int or t is np.float64 or t is bool or t is np.bool_:
        return index(asarr(A), *s)
    if t is str:
        if _bi.len(s) == 1:
            i = s[0]
            if i is COLON:
                return A
            ix = _ix(i, _bi.len(A))
            return "".join(A[k] for k in ix)
        raise MatlabError("MATLAB:badsubscript", "Unsupported index of a string.")
    if t is Cell:
        r, c = cshape(A)
        if _bi.len(s) == 1:
            i = s[0]
            if i is COLON:
                return Cell(A, True)
            ix = _ix(i, _bi.len(A))
            return Cell((A[k] for k in ix), A.col, None if (r == 1 or c == 1) else (_bi.len(ix), 1))
        if _bi.len(s) == 2:
            ix = _ix(s[0], r, 1)
            jx = _ix(s[1], c, 2)
            return Cell((A[int(i) + int(j) * r] for j in jx for i in ix), jx.size == 1 and ix.size != 1, (ix.size, jx.size))
    if t is Struct:
        ix = _ix(s[0], 1)
        return A if ix.size == 1 else SArr([A] * ix.size)
    if t is SArr:
        if _bi.len(s) == 1:
            i = s[0]
            if i is COLON:
                return SArr(A.items, A.fields, (_bi.len(A.items), 1))
            ix = _ix(i, _bi.len(A.items))
            if ix.size == 1:
                return A.items[ix[0]]
            return SArr([A.items[k] for k in ix], A.fields)
    if t is MMap:
        k = s[0]
        key = MMap._key(k)
        if key not in A.d:
            if isinstance(k, str):
                raise MatlabError("MATLAB:Containers:Map:NoKey", "The specified key is not present in this container.")
            raise MatlabError("MATLAB:Containers:Map:NoKey", "The specified key is not present in this container.")
        return A.d[key]
    if A is NOVAL:
        raise MatlabError("MATLAB:UndefinedFunction", "Unrecognized function or variable.")
    raise MatlabError("MATLAB:badsubscript", "Cannot index into a value of type %s." % t.__name__)


def ix1(A, i):
    """index(A, i) with the scalar case inlined."""
    if type(A) is np.ndarray:
        ti = type(i)
        if ti is float or ti is np.float64:
            k = int(i)
            if k == i and 1 <= k <= A.size:
                k -= 1
                r = A.shape[0]
                if r == 1:
                    return A[0, k]
                return A[k, 0] if A.shape[1] == 1 else A[k % r, k // r]
    return index(A, i)


def ix2(A, i, j):
    """index(A, i, j) with the scalar / row / column cases inlined."""
    if type(A) is np.ndarray:
        ti, tj = type(i), type(j)
        if ti is float or ti is np.float64:
            a = int(i)
            if a == i and 1 <= a <= A.shape[0]:
                if tj is float or tj is np.float64:
                    b = int(j)
                    if b == j and 1 <= b <= A.shape[1]:
                        return A[a - 1, b - 1]
                elif j is COLON:
                    return A[a - 1, 0] if A.shape[1] == 1 else A[a - 1:a, :].copy()
    return index(A, i, j)


def end_(A, k, n):
    t = type(A)
    if t is np.ndarray:
        if n == 1:
            return float(A.size)
        return float(A.shape[k - 1]) if k <= 2 else 1.0
    if t is str:
        return float(_bi.len(A))
    if t is Cell:
        if n == 1:
            return float(_bi.len(A))
        r, c = cshape(A)
        return float(r if k == 1 else c)
    if t is SArr:
        return float(_bi.len(A.items))
    if t is Struct:
        return 1.0
    if A is NOVAL or A is UNSET:
        return 0.0
    if isinstance(A, (int, float, np.number, bool, np.bool_)):
        return 1.0
    raise MatlabError("MATLAB:end", "'end' is not supported here.")


def cellget(C, *s):
    """c{i}: one element."""
    if type(C) is not Cell:
        if C is NOVAL:
            raise MatlabError("MATLAB:badsubscript", "Index exceeds the number of array elements (0).")
        raise MatlabError("MATLAB:cellRefFromNonCell", "'{}' indexing is only allowed for cell arrays.")
    if _bi.len(s) == 1:
        i = s[0]
        ti = type(i)
        if ti is float or ti is np.float64 or ti is int:
            k = int(i)
            if k == i and 1 <= k <= _bi.len(C):
                return C[k - 1]
        ix = _ix(i, _bi.len(C))
    else:
        r, c = cshape(C)
        ii = _ix(s[0], r, 1)
        jj = _ix(s[1], c, 2)
        ix = np.array([int(a) + int(b) * r for b in jj for a in ii])
    if ix.size != 1:
        raise MatlabError("MATLAB:index:expected_one_output", "Expected one output from a curly brace expression.")
    return C[ix[0]]


def cellcs(C, *s):
    """c{:} / c{1:3}: a comma-separated list."""
    if type(C) is not Cell:
        raise MatlabError("MATLAB:cellRefFromNonCell", "'{}' indexing is only allowed for cell arrays.")
    if _bi.len(s) == 1:
        return CS(C[k] for k in _ix(s[0], _bi.len(C)))
    r, c = cshape(C)
    return CS(C[int(a) + int(b) * r] for b in _ix(s[1], c, 2) for a in _ix(s[0], r, 1))


def field(a, name):
    t = type(a)
    if t is Struct:
        try:
            return a[name]
        except KeyError:
            raise MatlabError("MATLAB:nonExistentField", "Unrecognized field name \"%s\"." % name) from None
    if t is SArr:
        return CS(it[name] for it in a.items)
    raise MatlabError("MATLAB:nonStructAssignment", "Dot indexing is not supported for variables of type %s." % (
        "double" if isinstance(a, (np.ndarray, float, int, np.number)) else t.__name__))


def fieldcs(a, name):
    if type(a) is Struct:
        return [field(a, name)]
    return field(a, name)


def setfield(a, name, v):
    if a is NOVAL or (type(a) is np.ndarray and a.size == 0):
        a = Struct()
    if type(a) is Struct:
        a[name] = v
        return a
    if type(a) is SArr and _bi.len(a.items) == 1:
        a.items[0][name] = v
        return a.items[0]
    raise MatlabError("MATLAB:nonStructAssignment", "Invalid use of a N-D array / non-struct in a field assignment.")


def _grow_to(A, r, c, fill=0.0):
    if r <= A.shape[0] and c <= A.shape[1]:
        return A
    nr, nc = _bi.max(r, A.shape[0]), _bi.max(c, A.shape[1])
    B = np.full((nr, nc), fill, dtype=A.dtype if A.dtype != bool else bool)
    if A.dtype == bool:
        B[:] = False
    B[:A.shape[0], :A.shape[1]] = A
    return B


def _val_arr(v, dtype=None):
    a = asarr(v) if not isinstance(v, str) else asarr(v)
    return a


def setindex(A, s, v):
    """A(s...) = v. May mutate A in place; always use the returned object."""
    if A is NOVAL or A is UNSET or A is None:
        A = np.zeros((0, 0))
    t = type(A)
    if t is Cell:
        if type(v) is not Cell:
            raise MatlabError("MATLAB:cellAssignment", "Conversion to cell from %s is not possible." % type(v).__name__)
        if _bi.len(s) == 1:
            ix = _ix(s[0], _bi.len(A), 1, True)
            for n_, k in enumerate(ix):
                if k >= _bi.len(A):
                    setcell(A, (float(k + 1),), None)
                A[k] = v[n_] if _bi.len(v) > 1 else v[0]
            return A
        r, c = cshape(A)
        vr, vc = cshape(v)
        ri = np.arange(vr if r == 0 else r) if s[0] is COLON else _ix(s[0], r, 1, True)
        cj = np.arange(vc if c == 0 else c) if s[1] is COLON else _ix(s[1], c, 2, True)
        R = _bi.max(r, int(ri.max()) + 1 if ri.size else 0)
        K = _bi.max(c, int(cj.max()) + 1 if cj.size else 0)
        _cell_resize(A, R, K)
        if _bi.len(v) != 1 and _bi.len(v) != ri.size * cj.size:
            raise MatlabError("MATLAB:subsassigndimmismatch",
                              "Unable to perform assignment because the left and right sides have a different number of elements.")
        n_ = 0
        for b in cj:
            for a in ri:
                A[int(a) + int(b) * R] = v[0] if _bi.len(v) == 1 else v[n_]
                n_ += 1
        return A
    if t is SArr or t is Struct:
        return _setindex_struct(A, s, v)
    if t is not np.ndarray:
        A = asarr(A)
    if type(v) is not np.ndarray:
        if isinstance(v, (Struct, SArr, Cell, MMap)) or callable(v):
            if A.size == 0:
                if type(v) is Struct:
                    return _setindex_struct(SArr([], list(v.keys())), s, v)
                if type(v) is Cell:
                    return setindex(Cell(), s, v)
            raise MatlabError("MATLAB:UnableToConvert", "Conversion to double from %s is not possible." % type(v).__name__)
        v = asarr(v)
    if np.iscomplexobj(v) and not np.iscomplexobj(A):
        A = A.astype(complex)
    if _bi.len(s) == 1:
        i = s[0]
        ti = type(i)
        n = A.size
        if (ti is float or ti is np.float64 or ti is int) and v.size == 1:
            k = int(i)
            if k == i and 1 <= k <= n:
                k -= 1
                if A.shape[0] == 1:
                    A[0, k] = v.flat[0]
                elif A.shape[1] == 1:
                    A[k, 0] = v.flat[0]
                else:
                    A[k % A.shape[0], k // A.shape[0]] = v.flat[0]
                return A
        if i is COLON:
            if v.size == 1:
                A[...] = v.flat[0]
            elif v.size == n:
                A[...] = v.reshape(A.shape, order="F")
            else:
                raise MatlabError("MATLAB:subsassigndimmismatch", "Unable to perform assignment because the left and right sides have a different number of elements.")
            return A
        ix = _ix(i, n, None, True)
        if ix.size == 0:
            return A
        top = int(ix.max()) + 1
        if top > n:
            if A.shape[0] == 0 or A.shape == (0, 0) or A.shape[0] == 1:
                A = _grow_to(A, 1, top)
            elif A.shape[1] == 1:
                A = _grow_to(A, top, 1)
            else:
                raise MatlabError("MATLAB:subsassignnumelmismatch",
                                  "Attempt to grow array along ambiguous dimension.")
        if v.size == 1:
            A.ravel(order="F")                                   # force a view check (no-op)
            flat_assign(A, ix, v.flat[0])
        elif v.size == ix.size:
            flat_assign(A, ix, v.ravel(order="F"))
        else:
            raise MatlabError("MATLAB:subsassigndimmismatch",
                              "Unable to perform assignment because the left and right sides have a different number of elements.")
        return A
    if _bi.len(s) == 2 and s[1] is COLON and v.ndim == 2 and v.shape[0] == 1 and v.shape[1] == A.shape[1]             and (type(s[0]) is float or type(s[0]) is np.float64) and A.dtype == v.dtype:
        a = int(s[0])
        if a == s[0] and a >= 1:
            if a <= A.shape[0]:
                A[a - 1, :] = v[0]
                return A
            if a == A.shape[0] + 1:
                return np.concatenate((A, v), axis=0)
    if _bi.len(s) >= 2:
        i, j = s[0], s[1]
        ri = _ix(i, A.shape[0], 1, True) if i is not COLON else None
        cj = _ix(j, A.shape[1], 2, True) if j is not COLON else None
        # COLON on an empty dimension takes the size from the value
        if ri is None:
            nr = A.shape[0] if A.shape[0] > 0 or A.shape == (0, 0) and False else None
            if A.shape[0] == 0 and A.size == 0:
                nr = v.shape[0] if v.size != 1 or True else 1
                if cj is not None and v.size == 1:
                    nr = 1
                if cj is not None and v.size > 1 and cj.size == v.size and v.shape[0] == 1:
                    nr = 1
            ri = np.arange(nr if nr is not None else A.shape[0])
        if cj is None:
            nc = A.shape[1]
            if A.shape[1] == 0 and A.size == 0:
                nc = v.shape[1] if v.size != 1 else 1
                if ri.size and v.size > 1 and ri.size == v.size and v.shape[1] == 1:
                    nc = 1
            cj = np.arange(nc)
        nr_need = int(ri.max()) + 1 if ri.size else 0
        nc_need = int(cj.max()) + 1 if cj.size else 0
        A = _grow_to(A, nr_need, nc_need)
        if v.size == 1:
            A[np.ix_(ri, cj)] = v.flat[0]
        elif v.size == ri.size * cj.size:
            if v.shape == (ri.size, cj.size):
                A[np.ix_(ri, cj)] = v
            else:
                A[np.ix_(ri, cj)] = v.reshape((ri.size, cj.size), order="F")
        else:
            raise MatlabError("MATLAB:subsassigndimmismatch",
                              "Unable to perform assignment because the size of the left side is %d-by-%d and the size of the right side is %d-by-%d."
                              % (ri.size, cj.size, v.shape[0], v.shape[1]))
        return A
    return A


def flat_assign(A, ix, vals):
    """Assign to column-major linear positions."""
    r = A.shape[0]
    if A.flags["F_CONTIGUOUS"] or A.ndim == 2:
        rows, cols = ix % r, ix // r
        A[rows, cols] = vals


def _setindex_struct(A, s, v):
    if type(A) is Struct:
        A = SArr([A], list(A.keys()))
    k = _ix(s[0], _bi.len(A.items) + 1, None, True)
    if type(v) is not Struct:
        raise MatlabError("MATLAB:UnableToConvert", "Conversion to struct from non-struct is not possible.")
    i = int(k[0])
    while _bi.len(A.items) <= i:
        A.items.append(Struct((f, np.zeros((0, 0))) for f in A.fields))
    A.items[i] = v
    for f in v:
        if f not in A.fields:
            A.fields.append(f)
    A.shape = (1, _bi.len(A.items))
    return A


def delete(A, s):
    """A(s) = []"""
    if type(A) is Cell:
        ix = _ix(s[0], _bi.len(A))
        drop = set(int(k) for k in ix)
        keep = [x for n_, x in enumerate(A) if n_ not in drop]
        return Cell(keep, A.col)
    A = asarr(A)
    if _bi.len(s) == 1:
        ix = _ix(s[0], A.size)
        flat = np.delete(A.ravel(order="F"), ix)
        if A.shape[0] == 1 or A.size == 0:
            return flat.reshape(1, -1)
        if A.shape[1] == 1:
            return flat.reshape(-1, 1)
        return flat.reshape(1, -1)
    i, j = s[0], s[1]
    if i is COLON:
        return np.delete(A, _ix(j, A.shape[1], 2), axis=1)
    if j is COLON:
        return np.delete(A, _ix(i, A.shape[0], 1), axis=0)
    raise MatlabError("MATLAB:subsdeldimmismatch", "A null assignment can have only one non-colon index.")


def setcell(C, s, v):
    """c{s...} = v."""
    if C is NOVAL or (type(C) is np.ndarray and C.size == 0):
        C = Cell()
    if type(C) is not Cell:
        raise MatlabError("MATLAB:cellAssToNonCell", "Conversion to cell from %s is not possible." % type(C).__name__)
    if _bi.len(s) == 1:
        ix = _ix(s[0], _bi.len(C), None, True)
        k = int(ix[0])
        if k >= _bi.len(C):
            r, c = cshape(C)
            if r <= 1 and not C.col:
                _cell_resize(C, 1, k + 1)
            elif c == 1:
                _cell_resize(C, k + 1, 1)
            else:
                raise MatlabError("MATLAB:subsassignnumelmismatch", "Attempt to grow array along ambiguous dimension.")
        C[k] = v
        return C
    r, c = cshape(C)
    i = int(_ix(s[0], r, 1, True)[0])
    j = int(_ix(s[1], c, 2, True)[0])
    if i >= r or j >= c:
        _cell_resize(C, _bi.max(r, i + 1), _bi.max(c, j + 1))
        r = cshape(C)[0]
    C[i + j * r] = v
    return C


def getpath(a, path):
    for kind, arg in path:
        if kind == ".":
            a = field(a, arg) if (type(a) in (Struct, SArr)) else NOVAL
        elif kind == "(":
            a = index(a, *arg)
        else:
            a = cellget(a, *arg)
    return a


def _shallow(a):
    if type(a) is Struct:
        return Struct(a)
    if type(a) is SArr:
        return SArr(list(a.items), list(a.fields), a.shape)
    return a


def setpath(a, path, v):
    """Nested assignment x.a(i).b{j} = v with copy-on-write: nothing shared with another variable is changed."""
    kind, arg = path[0]
    rest = path[1:]
    if not rest:
        if kind == ".":
            return setfield(_shallow(a), arg, v)
        if kind == "(":
            return setindex(copy1(a), arg, v)
        return setcell(copy1(a), arg, v)
    if kind == ".":
        if a is NOVAL or (type(a) is np.ndarray and a.size == 0):
            a = Struct()
        if type(a) is SArr and _bi.len(a.items) == 1:
            a = a.items[0]
        if type(a) is not Struct:
            raise MatlabError("MATLAB:nonStructAssignment", "Invalid use of a field assignment on a non-struct.")
        a = Struct(a)
        a[arg] = setpath(a.get(arg, NOVAL), rest, v)
        return a
    if kind == "(":
        if rest[0][0] == ".":
            if a is NOVAL or (type(a) is np.ndarray and a.size == 0):
                a = SArr()
            if type(a) is Struct:
                a = SArr([a], list(a.keys()))
            if type(a) is not SArr:
                raise MatlabError("MATLAB:nonStructAssignment", "Invalid struct array assignment.")
            a = _shallow(a)
            k = int(_ix(arg[0], _bi.len(a.items) + 1, None, True)[0])
            while _bi.len(a.items) <= k:
                a.items.append(Struct((f, np.zeros((0, 0))) for f in a.fields))
            elem = setpath(a.items[k], rest, v)
            a.items[k] = elem
            for f in elem:
                if f not in a.fields:
                    a.fields.append(f)
                    for n_, other in enumerate(a.items):
                        if f not in other:
                            other = Struct(other)
                            other[f] = np.zeros((0, 0))
                            a.items[n_] = other
            a.shape = (1, _bi.len(a.items))
            return a
        sub = index(a, *arg) if a is not NOVAL else NOVAL
        return setindex(copy1(a), arg, setpath(sub, rest, v))
    sub = NOVAL
    try:
        sub = cellget(a, *arg)
    except MatlabError:
        pass
    return setcell(copy1(a), arg, setpath(sub, rest, v))


def cs_assign(targets_cell, rng, values):
    """[c{1:n}] = f(...): store each returned value."""
    if targets_cell is NOVAL:
        targets_cell = Cell()
    ix = _ix(rng, 10 ** 9, None, True)
    for k, val in zip(ix, values):
        while _bi.len(targets_cell) <= k:
            targets_cell.append(np.zeros((0, 0)))
        targets_cell[int(k)] = val
    return targets_cell


def cs_unpack(x, n):
    if type(x) in (CS, list, tuple):
        v = list(x)
    else:
        v = [x]
    if _bi.len(v) < n:
        raise MatlabError("MATLAB:unassignedOutputs", "Some elements in the list of outputs are unassigned.")
    return v[:n]


def anon_call(f, *a):
    return f(*a)


# --------------------------------------------------------------------------- constructors
def _dims(args):
    if not args:
        return (1, 1)
    a = [x for x in args if not isinstance(x, str)]
    if _bi.len(a) == 1:
        v = a[0]
        if type(v) is np.ndarray and v.size > 1:
            d = [int(x) for x in v.ravel()]
            return (_bi.max(d[0], 0), _bi.max(d[1], 0))
        n = _bi.max(int(_sc(v)), 0)
        return (n, n)
    return (_bi.max(int(_sc(a[0])), 0), _bi.max(int(_sc(a[1])), 0))


def b_zeros(*a):
    return np.zeros(_dims(a))


def b_ones(*a):
    return np.ones(_dims(a))


def b_nan(*a):
    return float("nan") if not a else np.full(_dims(a), np.nan)


def b_inf(*a):
    return float("inf") if not a else np.full(_dims(a), np.inf)


def b_true(*a):
    return True if not a else np.ones(_dims(a), dtype=bool)


def b_false(*a):
    return False if not a else np.zeros(_dims(a), dtype=bool)


def b_pi():
    return math.pi


def b_eps(x=None):
    if x is None:
        return float(np.finfo(float).eps)
    return np.spacing(np.abs(x))


def b_realmax():
    return float(np.finfo(float).max)


def b_realmin():
    return float(np.finfo(float).tiny)


def b_eye(*a):
    d = _dims(a)
    return np.eye(d[0], d[1])


def b_cell(*a):
    d = _dims(a)
    n = d[0] * d[1]
    c = Cell((np.zeros((0, 0)) for _ in range(n)))
    c.col = d[1] == 1 and d[0] != 1
    c.sh = (d[0], d[1])
    return c


def b_linspace(a, b, n=100.0):
    n = int(_sc(n))
    return np.linspace(_sc(a), _sc(b), n).reshape(1, n)


def b_repmat(A, m, n=None):
    if n is None:
        if type(m) is np.ndarray and m.size >= 2:
            m, n = m.ravel()[0], m.ravel()[1]
        else:
            n = m
    if type(A) is Cell:
        raise MatlabError("MATLAB:repmat", "repmat of a cell is not supported.")
    return np.tile(asarr(A), (_bi.max(int(_sc(m)), 0), _bi.max(int(_sc(n)), 0)))


def b_reshape(A, *dims):
    A = asarr(A)
    d = []
    for x in dims:
        d.append(None if (type(x) is np.ndarray and x.size == 0) else x)
    if _bi.len(d) == 1:
        d = [int(v) for v in asarr(dims[0]).ravel()]
    d = [None if v is None else int(_sc(v)) for v in d]
    if None in d:
        known = int(np.prod([v for v in d if v is not None]))
        d[d.index(None)] = A.size // known if known else 0
    if int(np.prod(d)) != A.size:
        raise MatlabError("MATLAB:getReshapeDims:notSameNumel", "To RESHAPE the number of elements must not change.")
    return A.reshape(tuple(d[:2]), order="F")


def b_meshgrid(x, y=None, nargout=1):
    xv = asarr(x).ravel()
    yv = xv if y is None else asarr(y).ravel()
    X, Y = np.meshgrid(xv, yv)
    return (X, Y) if nargout > 1 else X


def b_struct(*kv):
    if not kv:
        return Struct()
    if _bi.len(kv) % 2:
        raise MatlabError("MATLAB:struct:ArgNameValuePairs", "Field and value arguments must come in pairs.")
    names = [kv[i] for i in range(0, _bi.len(kv), 2)]
    vals = [kv[i] for i in range(1, _bi.len(kv), 2)]
    cells = [(n_, v) for n_, v in zip(names, vals) if type(v) is Cell and _bi.len(v) != 1]
    if cells:
        n = _bi.len(cells[0][1])
        for _, v in cells:
            if _bi.len(v) != n:
                raise MatlabError("MATLAB:struct:ArraySizeMismatch", "Array dimensions of cell values must match.")
        items = []
        for k in range(n):
            st = Struct()
            for nm, v in zip(names, vals):
                if type(v) is Cell:
                    st[nm] = v[k] if _bi.len(v) != 1 else v[0]
                else:
                    st[nm] = v
            items.append(st)
        return SArr(items, names, (1, n) if n else (0, 0))
    st = Struct()
    for nm, v in zip(names, vals):
        st[nm] = v[0] if type(v) is Cell else v
    return st


def containers_Map(*a):
    if not a:
        return MMap()
    if isinstance(a[0], str) and a[0] in ("KeyType", "UniformValues", "ValueType"):
        m = MMap()
        for k in range(0, _bi.len(a), 2):
            if a[k] == "KeyType":
                m.numeric = a[k + 1] != "char"
        return m
    return MMap(a[0], a[1] if _bi.len(a) > 1 else None)


# --------------------------------------------------------------------------- size / type queries
def b_size(A, dim=None, nargout=1):
    t = type(A)
    if t is np.ndarray:
        shp = A.shape if A.ndim == 2 else (A.shape + (1, 1))[:2]
    elif t is str:
        shp = (1 if _bi.len(A) else 0, _bi.len(A))
    elif t is Cell:
        shp = cshape(A)
    elif t is SArr:
        shp = A.shape
    elif t is Struct or isinstance(A, (int, float, bool, complex, np.number, np.bool_)) or callable(A) or t is MMap:
        shp = (1, 1)
    elif A is NOVAL:
        shp = (0, 0)
    else:
        raise MatlabError("MATLAB:size", "size of %s" % t.__name__)
    if dim is not None:
        d = int(_sc(dim))
        return float(shp[d - 1]) if d <= 2 else 1.0
    if nargout <= 1:
        return np.array([[float(shp[0]), float(shp[1])]])
    out = [float(shp[0]), float(shp[1])] + [1.0] * (nargout - 2)
    return tuple(out[:nargout])


def b_numel(A, *a):
    t = type(A)
    if t is np.ndarray:
        return float(A.size)
    if t is str or t is Cell:
        return float(_bi.len(A))
    if t is SArr:
        return float(_bi.len(A.items))
    if t is MMap:
        return float(_bi.len(A.d))
    if A is NOVAL:
        return 0.0
    return 1.0


def b_length(A):
    s = b_size(A)
    return float(s.max()) if asarr(A).size or type(A) is not np.ndarray else 0.0 if False else (
        float(np.max(s)) if np.all(s > 0) else 0.0)


def b_ndims(A):
    return 2.0


def b_isempty(A):
    t = type(A)
    if t is np.ndarray:
        return A.size == 0
    if t is str or t is Cell:
        return _bi.len(A) == 0
    if t is SArr:
        return _bi.len(A.items) == 0
    if A is NOVAL:
        return True
    if t is MMap:
        return _bi.len(A.d) == 0
    return False


def b_isscalar(A):
    return b_numel(A) == 1


def b_isvector(A):
    s = b_size(A)
    return bool(s.size == 2 and (s[0, 0] == 1 or s[0, 1] == 1) and s.max() >= 1 and (s[0, 0] * s[0, 1]) >= 1)


def b_isrow(A):
    s = b_size(A)
    return bool(s[0, 0] == 1)


def b_iscolumn(A):
    s = b_size(A)
    return bool(s[0, 1] == 1)


def b_ismatrix(A):
    return True


def b_ischar(A):
    return isinstance(A, str)


def b_iscell(A):
    return type(A) is Cell


def b_isstruct(A):
    return type(A) in (Struct, SArr)


def b_isnumeric(A):
    if type(A) is np.ndarray:
        return A.dtype != bool
    return isinstance(A, (int, float, complex, np.number)) and not isinstance(A, (bool, np.bool_))


def b_isreal(A):
    if type(A) is np.ndarray:
        return not np.iscomplexobj(A)
    return not isinstance(A, (complex, np.complexfloating)) and (isinstance(A, (int, float, np.number, bool, np.bool_)))


def b_islogical(A):
    return (type(A) is np.ndarray and A.dtype == bool) or isinstance(A, (bool, np.bool_))


def b_isfloat(A):
    return b_isnumeric(A)


def b_isa(A, cls):
    if cls in ("numeric", "float", "double"):
        return b_isnumeric(A)
    if cls == "logical":
        return b_islogical(A)
    if cls == "char":
        return isinstance(A, str)
    if cls == "struct":
        return b_isstruct(A)
    if cls == "cell":
        return type(A) is Cell
    if cls == "function_handle":
        return callable(A)
    return False


def b_is_function_handle(A):
    return callable(A)


def b_isfield(s, name):
    if type(name) is Cell:
        return np.array([[b_isfield(s, n) for n in name]], dtype=bool).reshape(1, -1)
    if type(s) is Struct:
        return isinstance(name, str) and name in s
    if type(s) is SArr:
        return isinstance(name, str) and name in s.fields
    return False


def b_fieldnames(s):
    if type(s) is Struct:
        return Cell(list(s.keys()), True)
    if type(s) is SArr:
        return Cell(list(s.fields), True)
    raise MatlabError("MATLAB:fieldnames:InvalidInput", "Invalid input argument of type 'double'. Input must be a structure or a Java or COM object.")


def b_rmfield(s, names):
    names = [names] if isinstance(names, str) else list(names)
    if type(s) is Struct:
        r = Struct(s)
        for n in names:
            if n not in r:
                raise MatlabError("MATLAB:rmfield:InvalidFieldname", "Invalid field name: '%s'." % n)
            del r[n]
        return r
    if type(s) is SArr:
        items = []
        for it in s.items:
            r = Struct(it)
            for n in names:
                r.pop(n, None)
            items.append(r)
        return SArr(items, [f for f in s.fields if f not in names], s.shape)
    raise MatlabError("MATLAB:rmfield:FirstInputNotStruct", "The first argument must be a structure.")


def b_getfield(s, name):
    return field(s, name)


def b_setfield(s, name, v):
    r = Struct(s)
    r[name] = v
    return r


def b_orderfields(s):
    return Struct(sorted(s.items()))


def b_isKey(m, k):
    if type(k) is Cell:
        return np.array([[MMap._key(x) in m.d for x in k]], dtype=bool).reshape(1, -1)
    return MMap._key(k) in m.d


def b_keys(m):
    ks = sorted(m.d.keys(), key=lambda x: (isinstance(x, str), x))
    return Cell(ks)


def b_values(m, *a):
    if a:
        return Cell(m.d[MMap._key(k)] for k in a[0])
    return Cell(m.d[k] for k in sorted(m.d.keys(), key=lambda x: (isinstance(x, str), x)))


# --------------------------------------------------------------------------- elementwise math
_SCALAR_FAST = {np.abs: abs, np.sqrt: math.sqrt, np.exp: math.exp, np.log: math.log, np.log10: math.log10,
                np.log2: math.log2, np.sin: math.sin, np.cos: math.cos, np.tan: math.tan, np.arctan: math.atan,
                np.arcsin: math.asin, np.arccos: math.acos, np.floor: lambda v: float(math.floor(v)),
                np.ceil: lambda v: float(math.ceil(v)), np.trunc: lambda v: float(math.trunc(v)),
                np.isnan: math.isnan, np.isinf: math.isinf, np.isfinite: math.isfinite}


def _ew(fn):
    fast = _SCALAR_FAST.get(fn)

    def f(x):
        t = type(x)
        if t is np.ndarray:
            return fn(x)
        if fast is not None and (t is float or t is np.float64):
            try:
                return fast(x)
            except (ValueError, OverflowError):
                pass                                               # NaN/Inf/complex results: let NumPy decide
        return fn(x if not isinstance(x, (bool, np.bool_)) else float(x))
    return f


b_abs = _ew(np.abs)
b_sqrt = _ew(np.sqrt)
b_exp = _ew(np.exp)
b_log = _ew(np.log)
b_log10 = _ew(np.log10)
b_log2 = _ew(np.log2)
b_sin = _ew(np.sin)
b_cos = _ew(np.cos)
b_tan = _ew(np.tan)
b_asin = _ew(np.arcsin)
b_acos = _ew(np.arccos)
b_atan = _ew(np.arctan)
b_sinh = _ew(np.sinh)
b_cosh = _ew(np.cosh)
b_tanh = _ew(np.tanh)
b_floor = _ew(np.floor)
b_ceil = _ew(np.ceil)
b_fix = _ew(np.trunc)
b_real = _ew(np.real)
b_imag = _ew(np.imag)
b_conj = _ew(np.conj)
b_angle = _ew(np.angle)
b_sign = _ew(np.sign)
b_isnan = _ew(np.isnan)
b_isinf = _ew(np.isinf)
b_isfinite = _ew(np.isfinite)
b_deg2rad = _ew(np.deg2rad)
b_rad2deg = _ew(np.rad2deg)


def b_atan2(y, x):
    return np.arctan2(y, x)


def b_hypot(a, b):
    ta, tb = type(a), type(b)
    if (ta is float or ta is np.float64) and (tb is float or tb is np.float64):
        return math.hypot(a, b)
    return np.hypot(a, b)


def b_round(x, digits=None):
    if digits is not None:
        f = 10.0 ** _sc(digits)
        return b_round(x * f) / f
    if type(x) is np.ndarray:
        return np.sign(x) * np.floor(np.abs(x) + 0.5)
    x = float(x) if not isinstance(x, complex) else x
    return float(np.sign(x) * np.floor(abs(x) + 0.5))


def b_mod(a, b):
    if _isscalarlike(a) and _isscalarlike(b):
        a, b = float(_sc(a)), float(_sc(b))
        if b == 0:
            return a
        return float(np.mod(a, b))
    A, B = asarr(a), asarr(b)
    with np.errstate(all="ignore"):
        r = np.mod(A, B)
    return np.where(B == 0, A, r)


def b_rem(a, b):
    if _isscalarlike(a) and _isscalarlike(b):
        a, b = float(_sc(a)), float(_sc(b))
        return a if b == 0 else float(np.fmod(a, b))
    A, B = asarr(a), asarr(b)
    return np.where(B == 0, A, np.fmod(A, B))


def b_double(x):
    if type(x) is np.ndarray:
        return x.astype(float) if x.dtype != complex else x
    if isinstance(x, str):
        return asarr(x)
    if isinstance(x, (bool, np.bool_, int, np.integer)):
        return float(x)
    return x


b_single = b_double


def b_logical(x):
    if type(x) is np.ndarray:
        if np.isnan(x).any() if x.dtype != bool else False:
            raise MatlabError("MATLAB:nologicalnan", "NaN's cannot be converted to logicals.")
        return x != 0
    return bool(x)


def _int_cast(lo, hi):
    def f(x):
        a = b_round(asarr(x) if type(x) is np.ndarray else x)
        return np.clip(a, lo, hi) if type(a) is np.ndarray else float(np.clip(a, lo, hi))
    return f


b_int8 = _int_cast(-128, 127)
b_uint8 = _int_cast(0, 255)
b_int16 = _int_cast(-32768, 32767)
b_uint16 = _int_cast(0, 65535)
b_int32 = _int_cast(-2 ** 31, 2 ** 31 - 1)
b_uint32 = _int_cast(0, 2 ** 32 - 1)
b_int64 = _int_cast(-2 ** 63, 2 ** 63 - 1)
b_uint64 = _int_cast(0, 2 ** 64 - 1)


def b_char(*a):
    if _bi.len(a) == 1 and isinstance(a[0], str):
        return a[0]
    if _bi.len(a) == 1 and type(a[0]) is np.ndarray:
        return "".join(chr(int(c)) for c in a[0].ravel(order="F"))
    if _bi.len(a) == 1 and isinstance(a[0], (int, float, np.number)):
        return chr(int(a[0]))
    if _bi.len(a) == 1 and type(a[0]) is Cell:
        return "".join(a[0])
    raise MatlabError("MATLAB:char", "Unsupported char() argument.")


# --------------------------------------------------------------------------- reductions
def _dim(A, dim):
    if dim is not None:
        return int(_sc(dim))
    return 1 if A.shape[0] != 1 else 2


def _numeric(A):
    A = asarr(A)
    if A.dtype == bool or A.dtype.kind in "iu":
        return A.astype(float)
    return A


def _opts(args):
    dim, flags = None, []
    for a in args:
        if isinstance(a, str):
            flags.append(a.lower())
        elif a is not None and not (type(a) is np.ndarray and a.size == 0):
            dim = a
    return dim, flags


def b_sum(A, *args):
    dim, flags = _opts(args)
    A = _numeric(A)
    if A.shape == (0, 0) and dim is None:
        return 0.0
    d = _dim(A, dim)
    f = np.nansum if "omitnan" in flags else np.sum
    return S(f(A, axis=d - 1, keepdims=True))


def b_prod(A, *args):
    dim, _ = _opts(args)
    A = _numeric(A)
    if A.shape == (0, 0) and dim is None:
        return 1.0
    return S(np.prod(A, axis=_dim(A, dim) - 1, keepdims=True))


def b_mean(A, *args):
    dim, flags = _opts(args)
    A = _numeric(A)
    if A.shape == (0, 0) and dim is None:
        return float("nan")
    d = _dim(A, dim)
    f = np.nanmean if "omitnan" in flags else np.mean
    return S(f(A, axis=d - 1, keepdims=True))


def b_cumsum(A, dim=None):
    A = _numeric(A)
    return np.cumsum(A, axis=_dim(A, dim) - 1)


def b_cumprod(A, dim=None):
    A = _numeric(A)
    return np.cumprod(A, axis=_dim(A, dim) - 1)


def b_any(A, dim=None):
    A = asarr(A)
    if A.shape == (0, 0) and dim is None:
        return False
    return S(np.any(A != 0, axis=_dim(A, dim) - 1, keepdims=True) if A.dtype != bool else
             np.any(A, axis=_dim(A, dim) - 1, keepdims=True))


def b_all(A, dim=None):
    A = asarr(A)
    if A.shape == (0, 0) and dim is None:
        return True
    return S(np.all(A != 0, axis=_dim(A, dim) - 1, keepdims=True) if A.dtype != bool else
             np.all(A, axis=_dim(A, dim) - 1, keepdims=True))


def b_nnz(A):
    return float(np.count_nonzero(asarr(A)))


def _minmax(A, b, dim, nargout, is_max):
    fm = np.fmax if is_max else np.fmin
    if b is not None and not (type(b) is np.ndarray and b.size == 0):
        r = fm(_numeric(A) if type(A) is np.ndarray else A, _numeric(b) if type(b) is np.ndarray else b)
        return S(r) if type(r) is np.ndarray else r
    A = _numeric(A)
    if A.size == 0:
        return (np.zeros((0, 0)), np.zeros((0, 0))) if nargout > 1 else np.zeros((0, 0))
    d = _dim(A, dim)
    ax = d - 1
    v = (np.fmax if is_max else np.fmin).reduce(A, axis=ax, keepdims=True)
    if nargout <= 1:
        return S(v)
    filled = np.where(np.isnan(A), -np.inf if is_max else np.inf, A)
    idx = (np.argmax if is_max else np.argmin)(filled, axis=ax)
    idx = np.expand_dims(idx, ax) + 1.0
    allnan = np.isnan(A).all(axis=ax, keepdims=True)
    idx = np.where(allnan, 1.0, idx)
    return S(v), S(idx)


def b_max(A, b=None, dim=None, nargout=1):
    ta, tb = type(A), type(b)
    if (ta is float or ta is np.float64) and (tb is float or tb is np.float64) and A == A and b == b:
        return A if A >= b else b
    if isinstance(b, str):
        return _minmax(A, None, None, nargout, True)
    if isinstance(dim, str):
        dim = None
    return _minmax(A, b, dim, nargout, True)


def b_min(A, b=None, dim=None, nargout=1):
    ta, tb = type(A), type(b)
    if (ta is float or ta is np.float64) and (tb is float or tb is np.float64) and A == A and b == b:
        return A if A <= b else b
    if isinstance(b, str):
        return _minmax(A, None, None, nargout, False)
    if isinstance(dim, str):
        dim = None
    return _minmax(A, b, dim, nargout, False)


def b_diff(A, n=1.0):
    A = asarr(A)
    out = A
    for _ in range(int(_sc(n))):
        if out.size == 0 or out.shape == (1, 1):
            return np.zeros((0, 0))
        if out.shape[0] == 1:
            out = np.diff(out, axis=1)
        else:
            out = np.diff(out, axis=0)
    return out


def b_norm(A, p=2.0):
    if type(A) is np.ndarray and p == 2.0 and A.size in (2, 3) and (A.shape[0] == 1 or A.shape[1] == 1)             and A.dtype == np.float64:
        return math.sqrt(float((A * A).sum()))
    A = asarr(A)
    if A.size == 0:
        return 0.0
    if A.shape[0] == 1 or A.shape[1] == 1:
        if isinstance(p, str):
            p = {"fro": 2.0, "inf": np.inf}.get(p.lower(), 2.0)
        return float(np.linalg.norm(A.ravel(), ord=_sc(p)))
    if isinstance(p, str):
        return float(np.linalg.norm(A, "fro"))
    return float(np.linalg.norm(A, ord=_sc(p)))


def b_dot(a, b):
    A, B = asarr(a), asarr(b)
    if (A.shape[0] == 1 or A.shape[1] == 1) and A.size == B.size:
        return S(np.sum(np.conj(A.ravel(order="F")) * B.ravel(order="F")))
    return S(np.sum(np.conj(A) * B, axis=_dim(A, None) - 1, keepdims=True))


def b_cross(a, b):
    A, B = asarr(a), asarr(b)
    r = np.cross(A.ravel(), B.ravel())
    return r.reshape(A.shape)


def b_fliplr(A):
    return np.fliplr(asarr(A))


def b_flipud(A):
    return np.flipud(asarr(A))


def b_find(A, n=None, nargout=1):
    A = asarr(A)
    flat = np.flatnonzero(A.ravel(order="F"))
    if n is not None:
        flat = flat[:int(_sc(n))]
    if nargout >= 2:
        r, c = flat % A.shape[0], flat // A.shape[0]
        shp = (1, -1) if A.shape[0] == 1 else (-1, 1)
        return (r.reshape(shp) + 1.0, c.reshape(shp) + 1.0)[:nargout]
    if A.shape[0] == 1 and A.shape[1] != 1:
        return (flat + 1.0).reshape(1, -1)
    if A.size == 0 and A.shape == (0, 0):
        return np.zeros((0, 0))
    if A.shape == (1, 1):
        return (flat + 1.0).reshape(-1, 1) if flat.size else np.zeros((0, 0))
    return (flat + 1.0).reshape(-1, 1)


def b_sort(A, *args, nargout=1):
    desc = False
    dim = None
    for a in args:
        if isinstance(a, str):
            desc = a.lower() == "descend"
        else:
            dim = a
    if type(A) is Cell:
        order = sorted(range(_bi.len(A)), key=lambda k: A[k], reverse=desc)
        out = Cell((A[k] for k in order), A.col)
        if nargout > 1:
            return out, np.array(order, dtype=float).reshape((-1, 1) if A.col else (1, -1)) + 1
        return out
    A = asarr(A)
    ax = _dim(A, dim) - 1
    isn = np.isnan(A)
    key = np.where(isn, np.inf, A) if not desc else np.where(isn, -np.inf, A)
    if desc:
        idx = np.argsort(-key if A.dtype != bool else ~key, axis=ax, kind="stable")
        # NaN first for descend
        if isn.any():
            k2 = np.where(isn, -np.inf, -A)
            idx = np.argsort(k2, axis=ax, kind="stable")
    else:
        idx = np.argsort(key, axis=ax, kind="stable")
        if isn.any():
            k2 = np.where(isn, np.inf, A)
            idx = np.argsort(k2, axis=ax, kind="stable")
    out = np.take_along_axis(A, idx, axis=ax)
    if nargout > 1:
        return out, idx + 1.0
    return out


def b_unique(A, *args, nargout=1):
    if type(A) is Cell:
        vals = sorted(set(A))
        out = Cell(vals, A.col if _bi.len(A) else False)
        if nargout > 1:
            last = {v: n_ for n_, v in enumerate(A)}
            first_i = np.array([last[v] + 1 for v in vals], dtype=float).reshape(-1, 1)
            return out, first_i
        return out
    A = asarr(A)
    flat = A.ravel(order="F")
    if A.size == 0:
        return A
    u, ia, ic = np.unique(flat, return_index=False, return_inverse=True, return_counts=False) if False else (None, None, None)
    keys = np.where(np.isnan(flat), np.inf, flat)
    u = np.unique(flat[~np.isnan(flat)])
    nn = int(np.isnan(flat).sum())
    if nn:
        u = np.concatenate([u, np.full(nn, np.nan)])
    out = u.reshape((1, -1) if (A.shape[0] == 1 and A.shape[1] >= 1) else (-1, 1))
    if nargout > 1:
        idx = np.array([np.flatnonzero(flat == v)[-1] + 1 if v == v else 0 for v in u], dtype=float)
        return out, idx.reshape(out.shape)
    return out


def _setop(a, b, op):
    if type(a) is Cell or type(b) is Cell:
        sa, sb = set(a), set(b)
        r = {"intersect": sa & sb, "setdiff": sa - sb, "union": sa | sb}[op]
        row = not ((type(a) is Cell and a.col) and (type(b) is Cell and b.col)) if op != "setdiff" else not (type(a) is Cell and a.col)
        return Cell(sorted(r), not row)
    A, B = asarr(a).ravel(), asarr(b).ravel()
    r = {"intersect": np.intersect1d(A, B), "setdiff": np.setdiff1d(A, B), "union": np.union1d(A, B)}[op]
    ra = asarr(a)
    isrow = ra.shape[0] == 1 or (asarr(b).shape[0] == 1 and op != "setdiff")
    return r.reshape((1, -1) if isrow else (-1, 1))


def b_intersect(a, b):
    return _setop(a, b, "intersect")


def b_setdiff(a, b):
    return _setop(a, b, "setdiff")


def b_union(a, b):
    return _setop(a, b, "union")


def b_ismember(a, s):
    if isinstance(a, str):
        return a in set(s) if type(s) is Cell else False
    if type(a) is Cell:
        return np.array([[x in set(s) for x in a]], dtype=bool).reshape(1, -1)
    A = asarr(a)
    return S(np.isin(A, asarr(s)))


def b_isequal(*a):
    def eq(x, y):
        tx, ty = type(x), type(y)
        if isinstance(x, str) or isinstance(y, str):
            return isinstance(x, str) and isinstance(y, str) and x == y
        if tx is Cell or ty is Cell:
            return tx is Cell and ty is Cell and _bi.len(x) == _bi.len(y) and _bi.all(eq(p, q) for p, q in zip(x, y))
        if tx in (Struct,) or ty in (Struct,):
            return tx is ty and set(x.keys()) == set(y.keys()) and _bi.all(eq(x[k], y[k]) for k in x)
        if tx is SArr or ty is SArr:
            return tx is ty and _bi.len(x.items) == _bi.len(y.items) and _bi.all(eq(p, q) for p, q in zip(x.items, y.items))
        try:
            X, Y = asarr(x), asarr(y)
        except MatlabError:
            return x is y
        return X.shape == Y.shape and bool(np.all(X == Y))
    return _bi.all(eq(a[0], v) for v in a[1:])


def b_trapz(*a):
    if _bi.len(a) == 1:
        return float(np.trapz(asarr(a[0]).ravel()))
    return float(np.trapz(asarr(a[1]).ravel(), asarr(a[0]).ravel()))


def b_polyval(p, x):
    return np.polyval(asarr(p).ravel(), x)


def b_numel_(x):
    return b_numel(x)


# --------------------------------------------------------------------------- interpolation / geometry
def b_interp1(x, v, xq, method="linear", extrap=None):
    X, V = asarr(x).ravel(order="F").astype(float), asarr(v).ravel(order="F")
    Q = asarr(xq)
    if X.size != V.size:
        raise MatlabError("MATLAB:interp1:YInvalidNumRows", "The length of X and the number of rows of V must match.")
    if X.size < 2:
        raise MatlabError("MATLAB:interp1:NotEnoughPts", "At least two points are required.")
    if (np.diff(X) <= 0).any():
        order = np.argsort(X, kind="stable")
        X, V = X[order], V[order]
        if (np.diff(X) <= 0).any():
            raise MatlabError("MATLAB:interp1:RepeatedValuesX", "The grid vectors are not strictly monotonic increasing.")
    q = Q.ravel(order="F")
    k = np.clip(np.searchsorted(X, q, side="right") - 1, 0, X.size - 2)
    x0, x1 = X[k], X[k + 1]
    y0, y1 = V[k], V[k + 1]
    r = y0 + (q - x0) * (y1 - y0) / (x1 - x0)
    r = np.where(q == X[-1], V[-1], r)
    out_of = (q < X[0]) | (q > X[-1]) | np.isnan(q)
    if extrap is None or (isinstance(extrap, str) and extrap == "extrap" and False):
        r = np.where(out_of, np.nan, r)
    elif isinstance(extrap, str):
        pass
    else:
        r = np.where(out_of, _sc(extrap), r)
    return S(r.reshape(Q.shape, order="F"))


def b_inpolygon(x, y, xv, yv, nargout=1):
    tx_, ty_ = type(x), type(y)
    if (tx_ is float or tx_ is np.float64) and (ty_ is float or ty_ is np.float64):
        px = asarr(xv).ravel(order="F").tolist()
        py = asarr(yv).ravel(order="F").tolist()
        n = len(px)
        if 0 < n <= 64:                                           # pure-Python path for one point and a small polygon
            X, Y = float(x), float(y)
            scale = max(max(abs(v) for v in px + py), 1.0)
            tol = 1e-12 * scale
            inside = False
            on = False
            xj, yj = px[-1], py[-1]
            for i in range(n):
                xi, yi = px[i], py[i]
                dy = yj - yi
                if (yi > Y) != (yj > Y) and X < (xj - xi) * (Y - yi) / (dy if dy != 0 else 1.0) + xi:
                    inside = not inside
                if not on and (min(xi, xj) - tol <= X <= max(xi, xj) + tol) and                         (min(yi, yj) - tol <= Y <= max(yi, yj) + tol):
                    cr = (X - xi) * (yj - yi) - (Y - yi) * (xj - xi)
                    if abs(cr) <= tol * max(math.hypot(xj - xi, yj - yi), 1.0):
                        on = True
                xj, yj = xi, yi
            inside = inside or on
            return (inside, on) if nargout > 1 else inside
    X, Y = asarr(x), asarr(y)
    px, py = asarr(xv).ravel(order="F"), asarr(yv).ravel(order="F")
    n = px.size
    xs, ys = X.reshape(-1, 1), Y.reshape(-1, 1)
    xj, yj = np.concatenate((px[-1:], px[:-1])), np.concatenate((py[-1:], py[:-1]))   # previous vertex
    dy = yj - py
    dys = np.where(dy != 0, dy, 1.0)
    cond = ((py > ys) != (yj > ys)) & (xs < (xj - px) * (ys - py) / dys + px)
    inside = (cond.sum(axis=1) % 2) == 1
    scale = _bi.max(float(np.max(np.abs(np.concatenate([px, py])))) if n else 1.0, 1.0)
    tol = 1e-12 * scale
    seglen = np.hypot(xj - px, yj - py)
    cross_ = (xs - px) * (yj - py) - (ys - py) * (xj - px)
    within = ((xs >= np.minimum(px, xj) - tol) & (xs <= np.maximum(px, xj) + tol) &
              (ys >= np.minimum(py, yj) - tol) & (ys <= np.maximum(py, yj) + tol))
    on = (within & (np.abs(cross_) <= tol * np.maximum(seglen, 1.0))).any(axis=1)
    inside = (inside | on).reshape(X.shape)
    on = on.reshape(X.shape)
    return (S(inside), S(on)) if nargout > 1 else S(inside)


# --------------------------------------------------------------------------- strings / errors
def _fmt_args(args):
    out = []
    for a in args:
        if isinstance(a, str):
            out.append(a)
        elif type(a) is Cell:
            out.extend(_fmt_args(a))
        elif isinstance(a, (bool, np.bool_)):
            out.append(float(a))
        elif isinstance(a, (int, float, np.number)):
            out.append(a)
        elif type(a) is np.ndarray:
            out.extend(a.ravel(order="F").tolist())
        else:
            out.append(a)
    return out


_SPEC = re.compile(r"%(?P<flags>[-+ 0#]*)(?P<width>\*|\d+)?(?:\.(?P<prec>\*|\d+))?(?P<conv>[diouxXeEfgGcs%])")


def _escapes(s):
    return (s.replace("\\n", "\n").replace("\\t", "\t").replace("\\r", "\r").replace("\\\\", "\\")
            .replace("\\'", "'").replace('\\"', '"').replace("\\a", "\a"))


def b_sprintf(fmt, *args):
    vals = _fmt_args(args)
    fmt = _escapes(fmt)
    specs = [m for m in _SPEC.finditer(fmt) if m.group("conv") != "%"]
    out, pos = [], 0
    while True:
        used = 0
        buf = []
        last = 0
        for m in _SPEC.finditer(fmt):
            buf.append(fmt[last:m.start()])
            last = m.end()
            conv = m.group("conv")
            if conv == "%":
                buf.append("%")
                continue
            if pos >= _bi.len(vals):
                if vals or used:
                    return "".join(out) + "".join(buf).rstrip() if False else "".join(out) + "".join(buf)
                buf.append("")
                continue
            v = vals[pos]
            pos += 1
            used += 1
            buf.append(_one(m, v))
        buf.append(fmt[last:])
        out.append("".join(buf))
        if pos >= _bi.len(vals) or not specs:
            break
    return "".join(out)


def _one(m, v):
    flags, width, prec, conv = m.group("flags") or "", m.group("width") or "", m.group("prec"), m.group("conv")
    spec = "%" + flags + width + ("." + prec if prec is not None else "")
    if conv in "di":
        if isinstance(v, str):
            return (spec + "s") % v
        if float(v) != int(v) if math.isfinite(float(v)) else True:
            if not math.isfinite(float(v)):
                return (("%" + flags.replace("0", "") + width + "s") % ("NaN" if v != v else ("Inf" if v > 0 else "-Inf")))
            return (spec.replace("." + prec, "") if prec else spec) % float(v) if False else ("%" + flags + width + "f") % float(v) if False else _g(v, flags, width)
        return (spec + "d") % int(v)
    if conv in "ouxX":
        return (spec + conv) % int(v)
    if conv in "eEfgG":
        if isinstance(v, str):
            return ("%" + flags + width + "s") % v
        v = float(v)
        if not math.isfinite(v):
            return ("%" + flags.replace("0", "") + width + "s") % ("NaN" if v != v else ("Inf" if v > 0 else "-Inf"))
        return (spec + conv) % v
    if conv == "c":
        return chr(int(v)) if not isinstance(v, str) else v
    if conv == "s":
        if isinstance(v, str):
            return (spec + "s") % v
        v = float(v)
        s = ("%d" % v) if v == int(v) else ("%g" % v)
        return ("%" + flags + width + "s") % s
    return ""


def _g(v, flags, width):
    s = "%f" % float(v)
    s = ("%g" % float(v)) if len(s.rstrip("0")) > 12 else s.rstrip("0").rstrip(".")
    return ("%" + flags + width + "s") % s


def b_mat2str(A, n=15.0):
    if isinstance(A, str):
        return "'" + A + "'"
    A = asarr(A)

    def f(x):
        if A.dtype == bool:
            return "true" if x else "false"
        return ("%." + str(int(_sc(n))) + "g") % x

    if A.size == 1:
        return f(A.flat[0])
    rows = [" ".join(f(x) for x in A[r]) for r in range(A.shape[0])]
    return "[" + ";".join(rows) + "]"


def b_num2str(x, fmt=None):
    if isinstance(x, str):
        return x
    if fmt is not None:
        if isinstance(fmt, str):
            return b_sprintf(fmt, x)
        return ("%." + str(int(_sc(fmt))) + "g") % _sc(x)
    A = asarr(x)
    if A.size == 1:
        v = float(A.flat[0])
        if v == int(v) if math.isfinite(v) else False:
            return "%d" % v
        return "%.4g" % v if abs(v) < 1e5 else "%.5g" % v
    return "  ".join(b_num2str(v) for v in A.ravel(order="F"))


def b_strcmp(a, b):
    if type(a) is Cell and type(b) is Cell:
        return np.array([[isinstance(p, str) and isinstance(q, str) and p == q for p, q in zip(a, b)]], dtype=bool)
    if type(a) is Cell:
        return np.array([[isinstance(p, str) and isinstance(b, str) and p == b for p in a]], dtype=bool).reshape(
            (-1, 1) if a.col else (1, -1))
    if type(b) is Cell:
        return b_strcmp(b, a)
    return isinstance(a, str) and isinstance(b, str) and a == b


def b_strcmpi(a, b):
    if type(a) is Cell:
        return np.array([[isinstance(p, str) and isinstance(b, str) and p.lower() == b.lower() for p in a]], dtype=bool)
    return isinstance(a, str) and isinstance(b, str) and a.lower() == b.lower()


def b_strncmp(a, b, n):
    n = int(_sc(n))
    return isinstance(a, str) and isinstance(b, str) and _bi.len(a) >= n and _bi.len(b) >= n and a[:n] == b[:n]


def b_lower(s):
    return s.lower() if isinstance(s, str) else Cell(x.lower() for x in s)


def b_upper(s):
    return s.upper() if isinstance(s, str) else Cell(x.upper() for x in s)


def b_strtrim(s):
    return s.strip() if isinstance(s, str) else Cell(x.strip() for x in s)


def b_strcat(*a):
    if _bi.any(type(x) is Cell for x in a):
        n = _bi.max(_bi.len(x) for x in a if type(x) is Cell)
        return Cell("".join((x[k] if type(x) is Cell else x) for x in a) for k in range(n))
    return "".join(x.rstrip() if isinstance(x, str) else "" for x in a)


def b_strrep(s, a, b):
    return s.replace(a, b) if isinstance(s, str) else Cell(x.replace(a, b) for x in s)


def b_regexprep(s, pat, rep, *opts):
    py = re.sub(r"\$(\d)", r"\\\1", rep)
    return re.sub(pat, py, s)


def b_strsplit(s, d=" "):
    return Cell(s.split(d))


def b_strjoin(c, d=" "):
    return d.join(c)


def b_fliplr_(x):
    return b_fliplr(x)


def b_error(*a):
    if not a:
        raise MatlabError("", "")
    if type(a[0]) is Struct:
        raise MatlabError(a[0].get("identifier", ""), a[0].get("message", ""))
    first = a[0]
    if _bi.len(a) > 1 and isinstance(first, str) and re.fullmatch(r"[A-Za-z][\w-]*(:[\w-]+)+", first):
        raise MatlabError(first, b_sprintf(a[1], *a[2:]))
    if _bi.len(a) == 1:
        if re.fullmatch(r"[A-Za-z][\w-]*(:[\w-]+)+", first):
            raise MatlabError("", first)
        raise MatlabError("", b_sprintf(first))
    raise MatlabError("", b_sprintf(first, *a[1:]))


WARNINGS = []


def b_warning(*a):
    if a and isinstance(a[0], str) and a[0] in ("on", "off", "error", "query"):
        return None
    if a and _bi.len(a) > 1 and isinstance(a[0], str) and re.fullmatch(r"[A-Za-z][\w-]*(:[\w-]+)+", a[0]):
        WARNINGS.append(b_sprintf(a[1], *a[2:]))
    elif a:
        WARNINGS.append(b_sprintf(a[0], *a[1:]))
    return None


def b_disp(x):
    print(x if isinstance(x, str) else b_mat2str(x))


def b_fprintf(*a):
    if a and not isinstance(a[0], str):
        a = a[1:]
    print(b_sprintf(*a), end="")


def b_tic():
    return float(time.perf_counter())


def b_toc(t=None):
    return float(time.perf_counter()) - (t or 0.0)


def b_deal(*a, nargout=1):
    if _bi.len(a) == 1:
        return tuple(copy(a[0]) for _ in range(_bi.max(nargout, 1))) if nargout > 1 else a[0]
    if _bi.len(a) != nargout and nargout > 1:
        raise MatlabError("MATLAB:deal:narginNargoutMismatch", "The number of outputs should match the number of inputs.")
    return tuple(a) if nargout > 1 else a[0]


def b_validateattributes(A, classes, attrs, *rest):
    name = "input"
    nm = [r for r in rest if isinstance(r, str)]
    if nm:
        name = nm[-1]
    cls = list(classes) if type(classes) is Cell else [classes]
    if cls:
        ok = False
        for c in cls:
            if c in ("numeric", "double", "single") and b_isnumeric(A):
                ok = True
            elif c == "logical" and b_islogical(A):
                ok = True
            elif c == "char" and isinstance(A, str):
                ok = True
            elif c == "cell" and type(A) is Cell:
                ok = True
            elif c == "struct" and b_isstruct(A):
                ok = True
            elif c.startswith(("int", "uint")) and b_isnumeric(A):
                ok = True
        if not ok:
            raise MatlabError("MATLAB:invalidType", "Expected %s to be one of these types: %s." % (name, ", ".join(cls)))
    arr = None if (isinstance(A, str) or type(A) in (Cell, Struct, SArr)) else asarr(A)
    at = list(attrs)
    k = 0

    def bad(what):
        raise MatlabError("MATLAB:expectedNonempty" if what == "nonempty" else "MATLAB:expected" + what.title().replace(" ", ""),
                          "Expected %s to be %s." % (name, what))
    while k < _bi.len(at):
        a = at[k]
        k += 1
        if not isinstance(a, str):
            continue
        if arr is None:
            continue
        v = arr
        if a == "vector" and not (v.size >= 1 and (v.shape[0] == 1 or v.shape[1] == 1)):
            bad("vector")
        elif a == "row" and not (v.ndim == 2 and v.shape[0] == 1):
            bad("row")
        elif a == "column" and not (v.shape[1] == 1):
            bad("column")
        elif a == "scalar" and v.size != 1:
            bad("scalar")
        elif a == "nonempty" and v.size == 0:
            bad("nonempty")
        elif a == "numel":
            n = _sc(at[k])
            k += 1
            if v.size != n:
                raise MatlabError("MATLAB:incorrectNumel", "Expected %s to have %d elements." % (name, int(n)))
        elif a == "size":
            k += 1
        elif a == "finite" and not np.isfinite(v).all():
            bad("finite")
        elif a == "real" and np.iscomplexobj(v):
            bad("real")
        elif a == "nonnan" and np.isnan(v).any():
            bad("nonnan")
        elif a == "nonnegative" and (v < 0).any():
            bad("nonnegative")
        elif a == "positive" and not (v > 0).all():
            bad("positive")
        elif a == "integer" and not (v == np.round(v)).all():
            bad("integer")
        elif a in (">=", "<=", ">", "<"):
            lim = _sc(at[k])
            k += 1
            good = {">=": (v >= lim), "<=": (v <= lim), ">": (v > lim), "<": (v < lim)}[a].all()
            if not good:
                raise MatlabError("MATLAB:expectedRange", "Expected %s to be %s %s." % (name, a, lim))


def _callable(f):
    if callable(f):
        return f
    if isinstance(f, str):
        g = globals().get("b_" + f)
        if g is None:
            raise MatlabError("MATLAB:UndefinedFunction", "Undefined function '%s'." % f)
        return g
    raise MatlabError("MATLAB:cellfun", "Invalid function argument.")


def _fun_opts(rest):
    uniform, handler = True, None
    rest = list(rest)
    data = []
    while rest:
        r = rest.pop(0)
        if isinstance(r, str) and r in ("UniformOutput", "ErrorHandler") and rest:
            v = rest.pop(0)
            if r == "UniformOutput":
                uniform = truth(v)
            else:
                handler = v
        else:
            data.append(r)
    return data, uniform, handler


def _map_fun(f, seqs, uniform, shape_like):
    f = _callable(f)
    n = _bi.len(seqs[0])
    res = [f(*[s[k] for s in seqs]) for k in range(n)]
    if uniform:
        if not res:
            return np.zeros((0, 0))
        vals = [_sc(r) if _isscalarlike(r) else r for r in res]
        arr = np.array(vals).reshape((-1, 1) if getattr(shape_like, "col", False) else (1, -1))
        return arr
    return Cell(res, getattr(shape_like, "col", False))


def b_cellfun(f, *rest, nargout=1):
    data, uniform, _ = _fun_opts(rest)
    for d in data:
        if type(d) is not Cell:
            raise MatlabError("MATLAB:cellfun:NotACell", "Input #2 expected to be a cell array.")
    if isinstance(f, str) and f in ("isempty", "length", "numel", "isclass"):
        f = {"isempty": b_isempty, "length": b_length, "numel": b_numel}[f]
    return _map_fun(f, data, uniform, data[0])


def b_arrayfun(f, *rest, nargout=1):
    data, uniform, _ = _fun_opts(rest)
    seqs = []
    for d in data:
        if type(d) is SArr:
            seqs.append(d.items)
        elif type(d) is Cell:
            seqs.append([Cell([x]) for x in d])
        else:
            seqs.append(list(asarr(d).ravel(order="F")))
    return _map_fun(f, seqs, uniform, None)


def b_feval(f, *a, nargout=1):
    return _callable(f)(*a)


def b_func2str(f):
    return getattr(f, "__name__", "anonymous")


def b_numel_dummy():
    return 0.0


def b_fullfile(*parts):
    import os
    return os.path.join(*parts)


def b_isspace(s):
    return np.array([[c.isspace() for c in s]], dtype=bool)


def b_ifelse(c, a, b):
    return a if truth(c) else b


def b_horzcat(*a):
    return hcat(*a)


def b_vertcat(*a):
    return vcat(*a)


def b_cat(dim, *a):
    d = int(_sc(dim))
    if d == 1:
        return vcat(*a)
    if d == 2:
        return hcat(*a)
    raise MatlabError("MATLAB:cat", "cat along dimension 3 is not supported in the generated code.")


def b_rms(x, *a):
    A = _numeric(x)
    d = _dim(A, a[0] if a else None)
    return S(np.sqrt(np.mean(np.abs(A) ** 2, axis=d - 1, keepdims=True)))


def b_prctile_unsupported(*a):
    raise MatlabError("MATLAB:unsupported", "prctile is not supported.")


def empty():
    return np.zeros((0, 0))


def b_imagunit():
    return 1j
