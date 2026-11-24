"""Compare MATLAB results (saved by matlab/nb_export_python.m) with the generated Python on the same inputs.

    python -I tests/parity_check.py <cases.mat> [--tol 1e-9]

Exit code 0 = every case agrees (numbers within rtol/atol, same shapes, same fields, same error identifiers).
"""
import argparse
import os
import sys
import traceback

import numpy as np
from scipy.io import loadmat
from scipy.io.matlab import mat_struct

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from noisebox import mrt                                        # noqa: E402

SKIP_FIELDS = {"fingerprint"}                                   # file hashes / dates differ by design


def from_mat(x):
    """loadmat object -> runtime type (Struct / SArr / Cell / str / 2-D ndarray)."""
    if isinstance(x, mat_struct):
        s = mrt.Struct()
        for f in x._fieldnames:
            s[f] = from_mat(getattr(x, f))
        return s
    if isinstance(x, np.ndarray):
        if x.dtype == object:
            if x.size and all(isinstance(e, mat_struct) for e in x.ravel()):
                items = [from_mat(e) for e in x.ravel(order="F")]
                if len(items) == 1:
                    return items[0]
                return mrt.SArr(items, list(items[0].keys()), x.shape)
            c = mrt.Cell((from_mat(e) for e in x.ravel(order="F")), x.ndim == 2 and x.shape[1] == 1 and x.shape[0] != 1)
            return c
        if x.dtype.kind in "US":
            if x.size == 0:
                return ""
            return "".join(str(e) for e in x.ravel(order="F")) if x.size == 1 or x.ndim < 2 else "".join(map(str, x.ravel()))
        a = np.atleast_2d(x) if x.ndim < 2 else x
        if a.dtype.kind in "iu":
            a = a.astype(float)
        return a
    return x


def tolist(res):
    return res


def same(a, b, path, tol, issues):
    """Append a message to issues for each difference."""
    if isinstance(a, str) or isinstance(b, str):
        if not (isinstance(a, str) and isinstance(b, str) and a == b):
            if isinstance(a, str) and isinstance(b, np.ndarray) and b.size == 0 and a == "":
                return
            issues.append("%s: text differs: %r vs %r" % (path, a, b))
        return
    ta, tb = type(a), type(b)
    if ta is mrt.Cell or tb is mrt.Cell:
        if not (ta is mrt.Cell and tb is mrt.Cell):
            if (isinstance(a, np.ndarray) and a.size == 0) or (isinstance(b, np.ndarray) and b.size == 0):
                if (len(a) if ta is mrt.Cell else 0) == (len(b) if tb is mrt.Cell else 0):
                    return
            issues.append("%s: one is a cell, the other is not" % path)
            return
        if len(a) != len(b):
            issues.append("%s: cell sizes %d vs %d" % (path, len(a), len(b)))
            return
        for i, (p, q) in enumerate(zip(a, b)):
            same(p, q, "%s{%d}" % (path, i + 1), tol, issues)
        return
    sa = ta in (mrt.Struct, mrt.SArr)
    sb = tb in (mrt.Struct, mrt.SArr)
    if sa or sb:
        if not (sa and sb):
            issues.append("%s: one is a struct, the other is not" % path)
            return
        ia = [a] if ta is mrt.Struct else a.items
        ib = [b] if tb is mrt.Struct else b.items
        if len(ia) != len(ib):
            issues.append("%s: struct array sizes %d vs %d" % (path, len(ia), len(ib)))
            return
        for n, (p, q) in enumerate(zip(ia, ib)):
            ka = set(p) - SKIP_FIELDS
            kb = set(q) - SKIP_FIELDS
            if ka != kb:
                issues.append("%s: fields differ: only MATLAB %s, only Python %s" % (path, sorted(ka - kb), sorted(kb - ka)))
            sub = path if len(ia) == 1 else "%s(%d)" % (path, n + 1)
            for k in sorted(ka & kb):
                same(p[k], q[k], sub + "." + k, tol, issues)
        return
    if callable(a) or callable(b):
        return
    try:
        A, B = mrt.asarr(a), mrt.asarr(b)
    except Exception as e:                                       # noqa: BLE001
        issues.append("%s: not comparable (%s)" % (path, e))
        return
    if A.size == 0 and B.size == 0:
        return
    if A.shape != B.shape:
        issues.append("%s: size %s vs %s" % (path, A.shape, B.shape))
        return
    Af, Bf = A.astype(complex if np.iscomplexobj(A) or np.iscomplexobj(B) else float), \
        B.astype(complex if np.iscomplexobj(A) or np.iscomplexobj(B) else float)
    fin = np.isfinite(Af) & np.isfinite(Bf)
    if not np.array_equal(np.isnan(Af), np.isnan(Bf)):
        issues.append("%s: NaN positions differ" % path)
        return
    if not np.array_equal(Af[~fin & ~np.isnan(Af)], Bf[~fin & ~np.isnan(Bf)]):
        issues.append("%s: Inf values differ" % path)
        return
    if fin.any():
        d = np.abs(Af[fin] - Bf[fin])
        lim = tol * (1 + np.abs(Bf[fin])) + 1e-9
        if (d > lim).any():
            k = int(np.argmax(d - lim))
            idx = np.argwhere(fin)[k]
            issues.append("%s: value differs at %s: MATLAB %.12g, Python %.12g (|diff| %.3g)" %
                          (path, tuple(int(i) + 1 for i in idx), Af[tuple(idx)], Bf[tuple(idx)], d[k]))


def run(mat_path, tol=1e-9, verbose=True, pkg="noisebox.core_py"):
    import importlib
    core_py = importlib.import_module(pkg)
    core_py.load()
    data = loadmat(mat_path, struct_as_record=False, squeeze_me=False)
    cases = data["cases"].ravel(order="F")
    results = data["res"].ravel(order="F")
    stats = {}
    failures = []
    for n, (cs, rs) in enumerate(zip(cases, results)):
        cs, rs = cs.ravel()[0] if isinstance(cs, np.ndarray) else cs, rs.ravel()[0] if isinstance(rs, np.ndarray) else rs
        fn = str(from_mat(cs.fn))
        args = from_mat(cs.args)
        nout = int(np.squeeze(cs.nargout))
        st = stats.setdefault(fn, [0, 0])
        st[0] += 1
        ok_m = bool(np.squeeze(rs.ok))
        issues = []
        try:
            f = getattr(core_py, fn)
        except AttributeError:
            issues.append("function %s is not in the generated Python package" % fn)
            f = None
        if f is not None:
            try:
                got = f(*list(args), nargout=nout) if nout > 1 else f(*list(args))
                py_ok = True
            except Exception as e:                               # noqa: BLE001
                py_ok = False
                py_err = e
            if ok_m and not py_ok:
                issues.append("Python raised %s: %s\n%s" % (type(py_err).__name__, py_err,
                                                              "".join(traceback.format_exception(py_err)[-3:])))
            elif not ok_m and py_ok:
                issues.append("MATLAB raised an error (%s) but Python did not" % str(from_mat(rs.id)))
            elif not ok_m and not py_ok:
                mid = str(from_mat(rs.id))
                pid = getattr(py_err, "identifier", "")
                if mid and pid and mid != pid:
                    issues.append("different error identifiers: MATLAB %s, Python %s" % (mid, pid))
            else:
                outs = from_mat(rs.out)
                outs = list(outs) if isinstance(outs, mrt.Cell) else [outs]
                got = list(got) if (nout > 1 and isinstance(got, tuple)) else [got]
                if len(outs) != len(got):
                    issues.append("number of outputs %d vs %d" % (len(outs), len(got)))
                else:
                    for k, (m_, p_) in enumerate(zip(outs, got)):
                        same(m_, p_, "out%d" % (k + 1), tol, issues)
        if issues:
            failures.append((n + 1, fn, issues))
        else:
            st[1] += 1
    if verbose:
        print("\nPARITY MATLAB <-> Python  (tolerance: relative %.0e, absolute 1e-9)" % tol)
        print("%-26s %6s %6s" % ("function", "cases", "equal"))
        for fn, (n, k) in sorted(stats.items()):
            print("%-26s %6d %6d %s" % (fn, n, k, "" if n == k else "  <-- DIFFERENT"))
        try:
            untested = sorted(set(core_py.manifest()["functions"]) - set(stats))
        except Exception:                                      # noqa: BLE001
            untested = []
        tot = sum(v[0] for v in stats.values())
        good = sum(v[1] for v in stats.values())
        print("-" * 42)
        print("%-26s %6d %6d" % ("TOTAL", tot, good))
        if untested:
            print("\nNo test call in nb_parity_cases.m for: %s" % ", ".join(untested))
        for n, fn, iss in failures[:25]:
            print("\ncase %d  %s" % (n, fn))
            for i in iss[:6]:
                print("    " + i.replace("\n", "\n    "))
    return failures


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mat")
    ap.add_argument("--tol", type=float, default=1e-9)
    ap.add_argument("--pkg", default="noisebox.core_py")
    ns = ap.parse_args()
    bad = run(ns.mat, ns.tol, pkg=ns.pkg)
    print("\nRESULT: " + ("ALL CASES IDENTICAL" if not bad else "%d CASE(S) DIFFER" % len(bad)))
    sys.exit(0 if not bad else 1)
