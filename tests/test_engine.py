"""Engine tests (plain Python, no arcpy, no MATLAB): consistency of serial / parallel runs and with direct core calls.

    propy tests\test_engine.py
"""
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from noisebox import engine                                      # noqa: E402

CHECKS = []


def check(name, ok, detail=""):
    CHECKS.append((name, ok))
    print("RESULT %s %s %s" % (name, "ok" if ok else "bad", detail))


def scene(n_src=2, cells=36):
    X, Y = np.meshgrid(np.arange(40), np.arange(40))
    Z = 6 * np.exp(-((X - 20) ** 2 + (Y - 14) ** 2) / 30) + 3 * np.sin(X / 6) * np.cos(Y / 9) + 0.02 * X
    srcs = [{"id": 1, "x": 100.0, "y": 120.0, "h": 2.0, "Lw": [100, 100, 100, 100, 100, 95, 90, 85]},
            {"id": 2, "x": 260.0, "y": 300.0, "h": 3.0, "Lw": [95, 95, 95, 95, 95, 90, 85, 80]}][:n_src]
    return {"mode": "iso2024", "G": 0.5, "T_C": 15.0, "RH": 70.0, "p_kPa": 101.325, "extra": {},
            "dem": {"x0": 0.0, "y0": 0.0, "cs": 10.0, "Z": Z},
            "obstacles": [{"x": [140, 160, 160, 140], "y": [100, 100, 140, 140], "h": 9.0}],
            "sources": srcs, "hr": 1.5,
            "grid": {"x0": 205.0, "y0": 85.0, "cs": 10.0, "nx": cells, "ny": 12}, "active_rows": None,
            "limits": {"bands": [np.nan] * 8, "weighting": "Z", "overall": 45.0},
            "detail": True, "want_bands": True}


if __name__ == "__main__":
    engine.core()
    job = scene()
    t = time.time()
    a = engine.run("field", job, parallel=1)
    ts = time.time() - t
    t = time.time()
    b = engine.run("field", job, parallel=4)
    tp = time.time() - t
    n = int(job["grid"]["nx"] * job["grid"]["ny"])
    check("grid_serial_equals_parallel", all(np.array_equal(a[k], b[k], equal_nan=True) for k in a if k != "closure_max_abs_dB"),
          "serial %.1f s, 4 processes %.1f s for %d cells x 2 sources" % (ts, tp, n))
    check("grid_valid_cells", int(np.isfinite(a["LAeq"]).sum()) > 0.5 * n, str(int(np.isfinite(a["LAeq"]).sum())))
    # one source: detail closure Lp = Lw - (Adiv+Aatm+Agr+Abar)
    job1 = scene(n_src=1)
    c = engine.run("field", job1, parallel=1)
    check("closure_single_source", c["closure_max_abs_dB"] < 1e-9, "%.2e" % c["closure_max_abs_dB"])
    # two sources are louder than one
    ok = np.isfinite(a["LAeq"]) & np.isfinite(c["LAeq"])
    check("two_sources_louder", bool((a["LAeq"][ok] >= c["LAeq"][ok] - 1e-9).all()))
    # points = the same numbers as the matching grid cells
    g = job["grid"]
    cells = [(3, 5), (10, 2), (20, 8)]
    recv = [{"x": g["x0"] + ix * g["cs"], "y": g["y0"] + iy * g["cs"], "h": job["hr"]} for ix, iy in cells]
    pj = dict(job, receivers=recv)
    p = engine.run("points", pj, parallel=1)
    ref = np.array([a["LAeq"][iy * g["nx"] + ix] for ix, iy in cells])
    check("points_equal_grid_cells", np.allclose(p["LAeq"], ref, equal_nan=True, atol=1e-9), "%s vs %s" % (p["LAeq"], ref))
    rng = np.random.default_rng(3)
    recv = [{"x": float(x), "y": float(y), "h": 1.5} for x, y in zip(rng.uniform(20, 370, 60), rng.uniform(20, 370, 60))]
    pj = dict(job, receivers=recv)
    p1 = engine.run("points", pj, parallel=1)
    p3 = engine.run("points", pj, parallel=3)
    same = all(np.array_equal(np.asarray(p1[k]), np.asarray(p3[k]), equal_nan=True) for k in p1 if k not in ("reasons",))
    check("points_serial_equals_parallel", same and p1["reasons"] == p3["reasons"])
    bad = [c for c in CHECKS if not c[1]]
    print("\n%d checks, %d failed" % (len(CHECKS), len(bad)))
    sys.exit(1 if bad else 0)
