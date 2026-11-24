"""Calculation engine: loops over grid cells / receivers and sources and calls the Python core.

THERE IS NO ACOUSTICS IN THIS FILE. Every formula comes from the generated package `core_py` (a translation of
matlab/core/*.m). This file only decides which calls to make, adds sources by calling the core's energy sum, picks
the dominant source (a comparison of dB values) and spreads the work over several processes.
"""
import importlib
import os
import pickle
import shutil
import subprocess
import sys
import tempfile
import time

import numpy as np

from . import config
from .config import NoiseBoxError

_CORE = None


# ---------------------------------------------------------------- the Python core
def core(reload=False):
    """The generated Python core (imports it on first use; `reload=True` picks up a newly exported version)."""
    global _CORE
    if _CORE is None or reload:
        try:
            from . import mrt
            cp = importlib.import_module("noisebox.core_py")
        except ImportError as e:
            raise NoiseBoxError("The Python core is missing (%s). Run matlab/nb_export_python.m in MATLAB once." % e)
        _CORE = cp
        cp.reload() if reload else cp.load()
    return _CORE


def core_status():
    """-> dict: generated (time), n_functions, stale (.m files changed after the export), missing, new, inputs."""
    try:
        cp = core()
        man = cp.manifest()
    except Exception as e:                                           # noqa: BLE001
        return {"ok": False, "problem": str(e)}
    import hashlib
    cdir = config.core_dir()
    now = {}
    if os.path.isdir(cdir):
        for f in os.listdir(cdir):
            if f.lower().endswith(".m"):
                with open(os.path.join(cdir, f), "rb") as fh:
                    now[f[:-2]] = hashlib.md5(fh.read()).hexdigest()
    stale, missing = [], []
    for name, info in man["functions"].items():
        if info.get("override"):
            continue
        if name not in now:
            missing.append(name)
        elif now[name] != info["md5"]:
            stale.append(name)
    new = sorted(n for n in now if n not in man["functions"] and n not in man.get("not_translated", {}))
    return {"ok": True, "generated": man["generated"], "n_functions": len(man["functions"]), "stale": sorted(stale),
            "missing": sorted(missing), "new": new, "not_translated": man.get("not_translated", {}),
            "functions": man["functions"], "core_dir": cdir, "notes": man.get("notes", []),
            "accelerated": sorted(n for n, i in man["functions"].items() if i.get("accelerated"))}


def check_core_up_to_date(log):
    """Tell the user when the MATLAB files were changed after the last export (the tools then use the OLD Python)."""
    st = core_status()
    if not st["ok"]:
        raise NoiseBoxError("Python core not available: %s" % st["problem"])
    if st["stale"] or st["missing"] or st["new"]:
        what = []
        if st["stale"]:
            what.append("changed: " + ", ".join(st["stale"]))
        if st["new"]:
            what.append("new: " + ", ".join(st["new"]))
        if st["missing"]:
            what.append("deleted: " + ", ".join(st["missing"]))
        log.warn("The MATLAB core was edited after the last export (%s). This run uses the OLD Python version. "
                 "Run nb_export_python in MATLAB to update it." % "; ".join(what))
    return st


# ---------------------------------------------------------------- MATLAB-style values
def _rt():
    from . import mrt
    return mrt


def row(a):
    return np.asarray(a, dtype=float).reshape(1, -1)


def _struct(**kw):
    mrt = _rt()
    s = mrt.Struct()
    s.update(kw)
    return s


def to_value(v):
    """Python value (from the 'extra inputs' box) -> MATLAB-style value."""
    mrt = _rt()
    if isinstance(v, (list, tuple, np.ndarray)):
        return row(v)
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, dict):
        return _struct(**{k: to_value(x) for k, x in v.items()})
    return v


def make_base(job):
    """The struct of settings every core call shares (G, atm, mode, optional extras)."""
    G = job["G"]
    Gs, Gm, Gr = (G, G, G) if np.isscalar(G) else tuple(G)
    base = _struct(G=_struct(Gs=float(Gs), Gm=float(Gm), Gr=float(Gr)),
                   atm=_struct(T_C=float(job["T_C"]), RH=float(job["RH"]), p_kPa=float(job["p_kPa"])),
                   mode=job["mode"])
    for k, v in (job.get("extra") or {}).items():
        base[k] = to_value(v)
    return base


def make_dem(job):
    d = job["dem"]
    return _struct(x0=float(d["x0"]), y0=float(d["y0"]), cs=float(d["cs"]), Z=np.asarray(d["Z"], dtype=float))


def make_obstacles(job):
    mrt = _rt()
    out = mrt.Cell()
    for o in job.get("obstacles") or []:
        s = _struct(x=row(o["x"]), y=row(o["y"]))
        if o.get("top") is not None:
            s["top"] = float(o["top"])
        else:
            s["h"] = float(o["h"])
        if o.get("gap"):
            s["gap"] = float(o["gap"])
        out.append(s)
    return out


def make_limits(job):
    lim = job.get("limits")
    if not lim:
        return None
    bands = np.asarray(lim["bands"], dtype=float).reshape(1, -1)
    return _struct(bands=bands, weighting=lim.get("weighting", "Z"),
                   overallA=(float(lim["overall"]) if lim.get("overall") is not None else _rt().empty()))


def _source_struct(s):
    return _struct(x=float(s["x"]), y=float(s["y"]), h=float(s["h"]))


# ---------------------------------------------------------------- helpers around core calls
def esum_stack(cp, arrays):
    """Elementwise energy sum of several N x 8 arrays, done by the core's nb_energy_sum (no formula here)."""
    if len(arrays) == 1:
        return arrays[0]
    n = arrays[0].shape
    M = np.vstack([a.reshape(1, -1, order="F") for a in arrays])
    r = cp.nb_energy_sum(M, 1.0)
    return np.asarray(r).reshape(n, order="F")


def aatm_for(cp, d, base_mode, atm):
    """Atmospheric absorption per distance, from the core (same branch run_acoustic_case uses). d: 1-D array."""
    A = np.full((d.size, 8), np.nan)
    ok = np.isfinite(d)
    if not ok.any():
        return A
    if base_mode == "iso1996":
        for k in np.flatnonzero(ok):
            A[k, :] = np.asarray(cp.nb_aatm_1996(float(d[k]), atm["T_C"], atm["RH"])).ravel()
    else:
        vals = cp.nb_aatm(d[ok].reshape(-1, 1), atm["T_C"], atm["RH"], atm["p_kPa"])
        A[ok, :] = np.asarray(vals).reshape(-1, 8)
    return A


def compliance_arrays(cp, Lp, LpA, lim):
    c = cp.nb_compliance(Lp, LpA, lim)
    code = np.asarray(c["code"], float).ravel()
    return {
        "code": code,
        "margin_overall": np.asarray(c["overallMargin"], float).ravel(),
        "worst_band": np.asarray(c["worstBand"], float).ravel(),
        "worst_margin": np.where(np.isfinite(np.asarray(c["worstMargin"], float).ravel()),
                                 np.asarray(c["worstMargin"], float).ravel(), np.nan),
        "margin_bands": np.asarray(c["margin"], float).reshape(-1, 8),
    }


# ---------------------------------------------------------------- grid
def field_chunk(job, rows):
    """Levels for the grid rows `rows` (0-based) from all sources. Returns {"idx": flat cell indices, arrays...}."""
    cp = core()
    base = make_base(job)
    dem = make_dem(job)
    obs = make_obstacles(job)
    lim = make_limits(job)
    g = job["grid"]
    NX, cs = int(g["nx"]), float(g["cs"])
    xg = g["x0"] + np.arange(NX) * cs
    rows = np.asarray(rows, dtype=int)
    yg = g["y0"] + rows * cs
    idx = (rows[:, None] * NX + np.arange(NX)[None, :]).ravel()
    xv = np.tile(xg, rows.size)
    yv = np.repeat(yg, NX)
    detail = bool(job["detail"])
    N = idx.size
    srcs = job["sources"]
    acc_lp, acc_lpa = [], []
    best = None
    dom = np.ones(N)
    closure = 0.0
    det = {}
    for s_i, S in enumerate(srcs):
        c = _struct(**base)
        c["dem"] = dem
        c["source"] = _source_struct(S)
        c["Lw"] = row(S["Lw"])
        c["Dc"] = row(S.get("Dc", [0.0] * 8))
        c["grid"] = _struct(x=row(xg), y=row(yg))
        c["hr"] = float(job["hr"])
        c["obstacles"] = obs
        o = cp.run_field_3d(c)
        Lp, LpA = np.asarray(o["Lp"]), np.asarray(o["LpA"])
        cLA = np.asarray(cp.nb_energy_sum(LpA, 2.0)).reshape(-1)
        acc_lp.append(Lp)
        acc_lpa.append(LpA)
        ground = np.asarray(o["ground"]).reshape(-1)
        if detail:
            dp = np.hypot(xv - S["x"], yv - S["y"])
            dd = np.sqrt(dp ** 2 + ((ground + job["hr"]) - (float(o["sourceGround"]) + S["h"])) ** 2)
            sAdiv = np.full((N, 8), np.nan)
            okd = np.isfinite(dd) & (dd > 0)
            if okd.any():
                sAdiv[okd, :] = np.asarray(cp.nb_adiv(dd[okd].reshape(-1, 1))).reshape(-1, 1) * np.ones((1, 8))
            sAatm = aatm_for(cp, dd, job["mode"], base["atm"])
            Agr, Abar = np.asarray(o["Agr"]), np.asarray(o["Abar"])
            kind = np.asarray(o["kind"]).reshape(-1)
            if len(srcs) == 1:
                res = Lp - ((c["Lw"] + c["Dc"]) - (sAdiv + sAatm + Agr + Abar))
                if np.isfinite(res).any():
                    closure = max(closure, float(np.nanmax(np.abs(res))))
        if s_i == 0:
            best = cLA.copy()
            if detail:
                det = {"Adiv": sAdiv, "Aatm": sAatm, "Agr": Agr.copy(), "Abar": Abar.copy(), "kind": kind.copy(),
                       "dist": dd.copy(), "ground": ground.copy()}
        else:
            upd = np.isnan(best) | (cLA > best)
            best[upd] = cLA[upd]
            dom[upd] = s_i + 1
            if detail:
                det["Adiv"][upd] = sAdiv[upd]
                det["Aatm"][upd] = sAatm[upd]
                det["Agr"][upd] = Agr[upd]
                det["Abar"][upd] = Abar[upd]
                det["kind"][upd] = kind[upd]
                det["dist"][upd] = dd[upd]
                det["ground"][upd] = ground[upd]
    accLp = esum_stack(cp, acc_lp)
    accLpA = esum_stack(cp, acc_lpa)
    out = {"idx": idx, "LAeq": np.asarray(cp.nb_energy_sum(accLpA, 2.0)).reshape(-1),
           "closure": closure}
    if job["want_bands"] or detail or lim is not None:
        out["Lp"], out["LpA"] = accLp, accLpA
        out["LZ"] = np.asarray(cp.nb_energy_sum(accLp, 2.0)).reshape(-1)
    if detail:
        out.update(det)
        out["dom"] = dom
    if lim is not None:
        out.update(compliance_arrays(cp, accLp, accLpA, lim))
    return out


# ---------------------------------------------------------------- points
def points_chunk(job, which):
    """Levels at receivers `which` (0-based list) from all sources."""
    cp = core()
    base = make_base(job)
    dem = make_dem(job)
    obs = make_obstacles(job)
    lim = make_limits(job)
    n = len(which)
    A = {k: np.full((n, 8), np.nan) for k in ("Lp", "LpA", "Adiv", "Aatm", "Agr", "Abar")}
    for k in ("LAeq", "LZ", "dom", "kind", "ground", "dist"):
        A[k] = np.full(n, np.nan)
    reasons = [""] * n
    for a, ri in enumerate(which):
        R = job["receivers"][ri]
        ok, best, dm = True, -np.inf, None
        accLp = accLpA = None
        for s_i, S in enumerate(job["sources"]):
            c = _struct(**base)
            c["dem"] = dem
            c["source"] = _source_struct(S)
            c["Lw"] = row(S["Lw"])
            c["Dc"] = row(S.get("Dc", [0.0] * 8))
            c["receiver"] = _struct(x=float(R["x"]), y=float(R["y"]), h=float(R["h"]))
            c["obstacles"] = obs
            o = cp.run_case_3d(c)
            if not o["valid"]:
                ok = False
                reasons[a] = o["reason"]
                break
            q = o["out"]
            lp, lpa = np.asarray(q["Lp"]).reshape(1, 8), np.asarray(q["LpA_bands"]).reshape(1, 8)
            if accLp is None:
                accLp, accLpA = lp, lpa
            else:
                accLp = esum_stack(cp, [accLp, lp])
                accLpA = esum_stack(cp, [accLpA, lpa])
            if float(q["LpA_broadband"]) > best:
                best = float(q["LpA_broadband"])
                kind = o["geom"]["kind"]
                dm = (s_i + 1, np.asarray(q["Adiv"]).reshape(8), np.asarray(q["Aatm"]).reshape(8),
                      np.asarray(q["Agr"]).reshape(8), np.asarray(q["Abar"]).reshape(8),
                      float(q["d"]), 1.0 * (kind == "blocked") + 2.0 * (kind == "clear_crest"))
        if ok:
            A["LAeq"][a] = float(cp.nb_energy_sum(accLpA))
            A["LZ"][a] = float(cp.nb_energy_sum(accLp))
            A["Lp"][a], A["LpA"][a] = accLp.ravel(), accLpA.ravel()
            A["dom"][a], A["Adiv"][a], A["Aatm"][a], A["Agr"][a], A["Abar"][a], A["dist"][a], A["kind"][a] = dm
            A["ground"][a] = float(cp.nb_dem_sample(dem, float(R["x"]), float(R["y"])))
    A["reasons"] = reasons
    A["idx"] = np.asarray(which, dtype=int)
    if lim is not None:
        A.update(compliance_arrays(cp, A["Lp"], A["LpA"], lim))
    return A


# ---------------------------------------------------------------- running (in this process or in workers)
class _Log:
    def msg(self, s): print(s)
    def warn(self, s): print("WARNING:", s)
    def progress(self, d, t, s): pass
    def cancelled(self): return False


def _split(items, n):
    return [items[k::n] for k in range(n)]


def run(kind, job, log=None, parallel=None):
    """kind 'field' | 'points'. Returns the assembled arrays (dict). Spreads chunks over worker processes."""
    log = log or _Log()
    ns = len(job["sources"])
    if kind == "field":
        g = job["grid"]
        NX = int(g["nx"])
        rows = list(job.get("active_rows") or range(int(g["ny"])))
        total_cells = len(rows) * NX
        nwork = config.worker_count(len(rows)) if parallel is None else (parallel or 1)
        if total_cells * ns < 600:
            nwork = 1
        per = max(1, min(300 // NX, -(-len(rows) // (nwork * 6))))        # about 6 blocks per process
        chunks = [rows[i:i + per] for i in range(0, len(rows), per)]
    else:
        n = len(job["receivers"])
        total_cells = n
        nwork = config.worker_count(n) if parallel is None else (parallel or 1)
        if total_cells * ns < 40:
            nwork = 1
        per = max(1, min(8, -(-n // (nwork * 6))))
        chunks = [list(range(i, min(i + per, n))) for i in range(0, n, per)]
    t0 = time.time()
    log.progress(0, len(chunks), "Calculating")
    if nwork <= 1:
        results = []
        for i, ch in enumerate(chunks):
            if log.cancelled():
                raise NoiseBoxError("Cancelled.")
            results.append(field_chunk(job, ch) if kind == "field" else points_chunk(job, ch))
            log.progress(i + 1, len(chunks), "%d of %d blocks" % (i + 1, len(chunks)))
    else:
        results = _run_parallel(kind, job, chunks, nwork, log)
    log.msg("Calculated in %.1f s with %d process(es)." % (time.time() - t0, nwork))
    return _assemble(kind, job, results)


def _run_parallel(kind, job, chunks, nwork, log):
    work = tempfile.mkdtemp(prefix="noisebox_")
    procs = []
    try:
        with open(os.path.join(work, "job.pkl"), "wb") as f:
            pickle.dump({"kind": kind, "job": job}, f, protocol=4)
        py = config.python_exe()
        worker = os.path.join(config.ROOT, "noisebox", "worker.py")
        parts = _split(list(range(len(chunks))), nwork)
        for k, mine in enumerate(parts):
            with open(os.path.join(work, "chunks_%d.pkl" % k), "wb") as f:
                pickle.dump([(i, chunks[i]) for i in mine], f, protocol=4)
            env = dict(os.environ)
            env.pop("PYTHONHOME", None)
            env.pop("PYTHONPATH", None)
            env["PYTHONNOUSERSITE"] = "1"
            procs.append(subprocess.Popen([py, "-s", worker, work, str(k)], stdout=subprocess.PIPE,
                                          stderr=subprocess.STDOUT, env=env, cwd=config.ROOT,
                                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)))
        total = len(chunks)
        while True:
            done = 0
            for k in range(len(procs)):
                p = os.path.join(work, "prog_%d.txt" % k)
                try:
                    with open(p) as f:
                        done += int(f.read().strip() or 0)
                except (OSError, ValueError):
                    pass
            log.progress(done, total, "%d of %d blocks (%d processes)" % (done, total, len(procs)))
            if log.cancelled():
                raise NoiseBoxError("Cancelled.")
            alive = [p for p in procs if p.poll() is None]
            for p in procs:
                if p.poll() not in (None, 0):
                    out = p.stdout.read().decode("utf-8", "replace") if p.stdout else ""
                    raise NoiseBoxError("A calculation process stopped with an error:\n" + out[-2500:])
            if not alive:
                break
            time.sleep(0.4)
        results = []
        for k in range(len(procs)):
            with open(os.path.join(work, "res_%d.pkl" % k), "rb") as f:
                results.extend(pickle.load(f))
        results.sort(key=lambda t: t[0])
        return [r for _, r in results]
    finally:
        for p in procs:
            if p.poll() is None:
                p.kill()
        shutil.rmtree(work, ignore_errors=True)


def _assemble(kind, job, results):
    if kind == "field":
        g = job["grid"]
        NP = int(g["nx"]) * int(g["ny"])
    else:
        NP = len(job["receivers"])
    out = {}
    closure = 0.0
    reasons = [""] * NP
    for r in results:
        idx = r["idx"]
        closure = max(closure, r.get("closure", 0.0) or 0.0)
        for k, v in r.items():
            if k in ("idx", "closure"):
                continue
            if k == "reasons":
                for a, i in enumerate(idx):
                    reasons[i] = v[a]
                continue
            v = np.asarray(v)
            if k not in out:
                out[k] = np.full((NP,) + v.shape[1:], np.nan)
            out[k][idx] = v
    out["closure_max_abs_dB"] = closure
    if kind == "points":
        out["reasons"] = reasons
    return out
