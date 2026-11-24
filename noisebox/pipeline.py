"""The work of each tool (reading ArcGIS data, calling the engine, writing results). Used by NoiseBox.pyt and the tests.

`log` is any object with msg(str), warn(str), progress(done, total, text), cancelled() -> bool.
"""
import math
import os
import re
import time

import numpy as np

from . import arcgis_io as aio
from . import config, engine
from . import outputs as out
from .config import BANDS, MODES, P_KPA, NoiseBoxError

MAX_CELL_SOURCES = 5_000_000     # hard stop: cells x sources
MAX_DETAIL_CELLS = 100_000       # above this no click-to-inspect cell polygons are written
SECONDS_PER_CELL_SOURCE = 0.015  # measured on one core with terrain and one barrier; used for the time estimate only


class PrintLog:
    def msg(self, s): print(s)
    def warn(self, s): print("WARNING:", s)
    def progress(self, d, t, s): pass
    def cancelled(self): return False


# ---------------------------------------------------------------- reading the dialog values
def parse_band_limits(text):
    """'-, -, 50, 50, 45, -, -, -' -> 8 floats (NaN = no limit). Empty text = no band limits."""
    if text is None or str(text).strip() == "":
        return [float("nan")] * 8
    toks = [t.strip() for t in re.split(r"[;,\s]+", str(text).strip()) if t.strip() != ""]
    if len(toks) != 8:
        raise NoiseBoxError("Allowed band levels need exactly 8 entries (63, 125, 250, 500, 1000, 2000, 4000, 8000 Hz); "
                            "write '-' where a band has no limit. Found %d entries." % len(toks))
    vals = []
    for t in toks:
        if t in ("-", "none", "None", "NaN", "nan"):
            vals.append(float("nan"))
        else:
            try:
                vals.append(float(t))
            except ValueError:
                raise NoiseBoxError("Allowed band level '%s' is not a number (use '-' for no limit)." % t)
    return vals


RESERVED_EXTRA = {"dem", "source", "receiver", "grid", "obstacles", "hr", "Lw", "Dc", "G", "atm", "mode", "limits"}


def parse_extra(text):
    """'C0=2; groundMethod=simplified; Gdefault=0.3' -> {name: value}. Numbers, true/false, [1 2 3], text."""
    d = {}
    if text is None or str(text).strip() == "":
        return d
    for part in re.split(r"[;\n]+", str(text)):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise NoiseBoxError("Extra core input '%s': write it as name=value (for example C0=2)." % part)
        name, val = part.split("=", 1)
        name, val = name.strip(), val.strip()
        if not re.fullmatch(r"[A-Za-z]\w*", name):
            raise NoiseBoxError("Extra core input name '%s' is not a valid MATLAB field name." % name)
        if name in RESERVED_EXTRA:
            raise NoiseBoxError("Extra core input '%s' is set by the tool itself (use its own parameter)." % name)
        if val.lower() in ("true", "false"):
            v = val.lower() == "true"
        elif val.startswith("[") and val.endswith("]"):
            try:
                v = [float(x) for x in re.split(r"[,\s;]+", val[1:-1].strip()) if x]
            except ValueError:
                raise NoiseBoxError("Extra core input '%s': the list %s contains a non-number." % (name, val))
        else:
            try:
                v = float(val)
            except ValueError:
                v = val.strip("'\"")
        d[name] = v
    return d


def limits_job(overall, band_text, weighting):
    bands = parse_band_limits(band_text)
    has_bands = any(not math.isnan(b) for b in bands)
    if overall is None and not has_bands:
        return None
    return {"bands": bands, "bands_set": [not math.isnan(b) for b in bands], "weighting": weighting,
            "overall": None if overall is None else float(overall)}


def settings(p):
    G = p.get("G")
    G = 0.5 if G is None else float(G)
    if not 0.0 <= G <= 1.0:
        raise NoiseBoxError("Ground factor G must be between 0 (hard ground) and 1 (porous ground).")
    hr = 1.5 if p.get("hr") is None else float(p["hr"])
    if hr <= 0:
        raise NoiseBoxError("Receiver height must be greater than 0 m.")
    RH = 70.0 if p.get("RH") is None else float(p["RH"])
    if not 0 < RH <= 100:
        raise NoiseBoxError("Relative humidity must be between 0 and 100 %.")
    T = 15.0 if p.get("T") is None else float(p["T"])
    mode = MODES.get(p.get("mode"), p.get("mode") or "iso2024")
    if mode not in ("iso2024", "iso1996", "draft2026"):
        raise NoiseBoxError("Unknown formula version: %s" % p.get("mode"))
    if mode == "iso1996" and (abs(T - 20) > 1e-9 or abs(RH - 70) > 1e-9):
        raise NoiseBoxError("The ISO 9613-2:1996 compatibility mode only has atmospheric absorption for 20 deg C and "
                            "70 % humidity. Set the temperature to 20 and the humidity to 70, or use the 2024 version.")
    lim = limits_job(p.get("overall"), p.get("band_limits"), "A" if p.get("weighting") == "A-weighted band level LpA" else "Z")
    return {"G": G, "hr": hr, "T_C": T, "RH": RH, "p_kPa": P_KPA, "mode": mode, "limits": lim,
            "extra": parse_extra(p.get("extra"))}


# ---------------------------------------------------------------- shared pieces
def _bbox(points, extent=None):
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    if extent is not None:
        xs += [extent[0], extent[2]]
        ys += [extent[1], extent[3]]
    return (min(xs), min(ys), max(xs), max(ys))


def _need_gdb(p):
    arcpy = aio._arcpy()
    gdb = p.get("out_gdb")
    if not gdb:
        raise NoiseBoxError("Choose the output geodatabase.")
    if not arcpy.Exists(gdb):
        raise NoiseBoxError("The output geodatabase does not exist: %s" % gdb)
    return gdb


def _inputs(p, log):
    """-> (sr, sources, barrier layer or None, barrier field)"""
    arcpy = aio._arcpy()
    if not p.get("sources"):
        raise NoiseBoxError("Choose the source layer (point features with h_src and Lw_63 ... Lw_8000).")
    sr = arcpy.Describe(p["sources"]).spatialReference
    aio.require_metric_projected(sr, "The source layer")
    sources = aio.read_sources(p["sources"], sr, p.get("h_field") or "h_src", p.get("lw_prefix") or "Lw_")
    log.msg("Sources: %d." % len(sources))
    bar, bfield = p.get("barriers"), p.get("b_field") or "h_bar"
    return sr, sources, bar, bfield


def _scene(p, sr, bbox, bar, bfield, log):
    pad = max(100.0, 0.05 * max(bbox[2] - bbox[0], bbox[3] - bbox[1]))
    obstacles = aio.read_obstacles(bar, sr, bfield, bbox) if bar else []
    log.msg("Barriers / buildings used: %d" % len(obstacles))
    if p.get("dem"):
        dem, Z, nod = aio.dem_from_raster(p["dem"], sr, bbox, pad)
        log.msg("Elevation: %d x %d cells of %.1f m (resampled to the coordinate system of the sources)" %
                (dem["nx"], dem["ny"], dem["cs"]))
        if nod > 0:
            log.warn("%.1f %% of the elevation raster in the area is NoData; receivers there become NoData." % (100 * nod))
    else:
        dem, Z = aio.flat_dem(bbox, pad)
        log.msg("No elevation raster given: flat ground at 0 m.")
    dem = dict(dem, Z=Z)
    return obstacles, dem


def _job(st, sources, obstacles, dem):
    return {"mode": st["mode"], "G": st["G"], "T_C": st["T_C"], "RH": st["RH"], "p_kPa": st["p_kPa"],
            "extra": st["extra"], "dem": dem, "obstacles": obstacles, "sources": sources, "hr": st["hr"],
            "limits": st["limits"]}


def _area(p, sr, sources, log):
    """-> (bbox, rings or None, area layer or None)"""
    fc = p.get("area")
    if fc:
        bbox, rings = aio.read_area(fc, sr)
        log.msg("Calculation area: polygon layer (%d ring(s)); cells outside it stay empty." % len(rings))
        return bbox, (rings if p.get("clip", True) else None), fc
    ext = p.get("extent")
    if ext is not None:
        if ext.spatialReference is not None and ext.spatialReference.factoryCode and \
                ext.spatialReference.factoryCode != sr.factoryCode:
            ext = ext.projectAs(sr)
        log.msg("Calculation area: the extent you gave.")
        return (ext.XMin, ext.YMin, ext.XMax, ext.YMax), None, None
    pad = 300.0
    b = _bbox([(s["x"], s["y"]) for s in sources])
    log.msg("No calculation area given: using the sources' bounding box + %d m on every side." % pad)
    return (b[0] - pad, b[1] - pad, b[2] + pad, b[3] + pad), None, None


def _status_of(code):
    return np.array([out.STATUS.get(int(c), "NO DATA") if np.isfinite(c) else "NO DATA" for c in code])


class _Ticker:
    """Logs how long each output took to write (helps to see what to switch off for a faster run)."""

    def __init__(self, log):
        self.log, self.t = log, time.time()

    def __call__(self, what):
        now = time.time()
        self.log.msg("   %s written in %.0f s" % (what, now - self.t))
        self.t = now


class _Step:
    """Numbered progress messages: 'Step 2 of 5: ...'."""

    def __init__(self, log, total):
        self.log, self.total, self.n = log, total, 0
        self.t0 = time.time()

    def __call__(self, text):
        self.n += 1
        self.log.msg("Step %d of %d: %s (%.0f s elapsed)" % (self.n, self.total, text, time.time() - self.t0))


# ---------------------------------------------------------------- noise map
def noise_map(p, log):
    arcpy = aio._arcpy()
    step = _Step(log, 5)
    step("checking the inputs")
    gdb = _need_gdb(p)
    engine.check_core_up_to_date(log)
    st = settings(p)
    sr, sources, bar, bfield = _inputs(p, log)
    bbox, rings, area_fc = _area(p, sr, sources, log)
    cs = p.get("cell")
    if not cs:
        cs = aio.auto_cell(bbox)
        log.msg("Cell size not given: using %g m (about 150 cells across the area)." % cs)
    cs = float(cs)
    grid, ll = aio.make_grid(bbox, cs)
    nx, ny = grid["nx"], grid["ny"]
    ncell = nx * ny
    if rings:
        xc = grid["x0"] + np.arange(nx) * cs
        yc = grid["y0"] + np.arange(ny) * cs
        XX, YY = np.meshgrid(xc, yc)
        inside = aio.points_in_rings(XX.ravel(), YY.ravel(), rings).reshape(ny, nx)
        if not inside.any():
            raise NoiseBoxError("No cell centre lies inside the calculation-area polygon. Use a smaller cell size.")
    else:
        inside = np.ones((ny, nx), dtype=bool)
    active_rows = [int(i) for i in np.flatnonzero(inside.any(axis=1))]
    n_active = int(inside.sum())
    log.msg("Grid: %d x %d = %d cells of %g m (%d inside the area), %d source(s)." %
            (nx, ny, ncell, cs, n_active, len(sources)))
    if ncell * len(sources) > MAX_CELL_SOURCES:
        raise NoiseBoxError("%d cells x %d sources is too much for one run (limit %d). Use a larger cell size or a "
                            "smaller area." % (ncell, len(sources), MAX_CELL_SOURCES))
    detail = bool(p.get("detail", True))
    if detail and n_active > MAX_DETAIL_CELLS:
        log.warn("%d cells is more than %d: the click-to-inspect cell layer is skipped. Use a larger cell size to get it."
                 % (n_active, MAX_DETAIL_CELLS))
        detail = False
    nwork = config.worker_count(len(active_rows))
    est = n_active * len(sources) * SECONDS_PER_CELL_SOURCE / nwork / 60.0
    log.msg("Estimated calculation time: about %.1f min on %d process(es)." % (max(est, 0.05), nwork))
    if est > 20:
        log.warn("This will take a while. A larger cell size or a smaller area is much faster.")

    step("reading barriers and elevation")
    scene_bbox = _bbox([(s["x"], s["y"]) for s in sources], bbox)
    obstacles, dem = _scene(p, sr, scene_bbox, bar, bfield, log)
    job = _job(st, sources, obstacles, dem)
    job.update({"grid": grid, "active_rows": active_rows, "detail": detail,
                "want_bands": bool(p.get("bands")) or detail or st["limits"] is not None})

    step("calculating")
    run = out.unique_run_name(gdb, p.get("run_name") or "NoiseRun")
    arr = engine.run("field", job, log)
    flat_inside = inside.ravel()
    for k, a in arr.items():
        if isinstance(a, np.ndarray) and a.shape[:1] == (ncell,):
            a[~flat_inside] = np.nan
    laeq = arr["LAeq"].reshape(ny, nx)
    n_ok = int(np.isfinite(laeq).sum())
    log.msg("Valid cells: %d of %d inside the area (a cell is empty when it lies inside a barrier, at a source, or "
            "outside the elevation raster)." % (n_ok, n_active))
    if n_ok == 0:
        raise NoiseBoxError("No cell could be calculated. Check that the area lies inside the elevation raster and "
                            "outside the barrier polygons.")
    if detail and len(sources) == 1:
        log.msg("Self-check: Lp = Lw - (Adiv + Aatm + Agr + Abar) holds to %.1e dB in every cell." %
                arr["closure_max_abs_dB"])

    step("writing results")
    lim = st["limits"]
    has_lim = lim is not None
    overall = lim["overall"] if has_lim else None
    created = {}
    tick = _Ticker(log)
    path = out.out_path(gdb, run + "_LAeq")
    out.write_raster(laeq, ll, cs, sr, path)
    created["laeq"] = path
    tick("LAeq raster")
    log.msg("LAeq range: %.1f to %.1f dB(A)" % (np.nanmin(laeq), np.nanmax(laeq)))
    if p.get("bands"):
        for i, b in enumerate(BANDS):
            path = out.out_path(gdb, "%s_Lp%d" % (run, b))
            out.write_raster(arr["Lp"][:, i].reshape(ny, nx), ll, cs, sr, path)
            created["Lp%d" % b] = path
        tick("octave-band rasters")
    iso = p.get("iso_step")
    if iso and float(iso) > 0:
        path = out.out_path(gdb, run + "_Bands")
        out.write_isophones(laeq, ll, cs, sr, float(iso), path)
        created["bands"] = path
        tick("noise-band polygons")
    if has_lim:
        margin = arr["margin_overall"] if overall is not None else arr["worst_margin"]
        path = out.out_path(gdb, run + "_Margin")
        out.write_raster(margin.reshape(ny, nx), ll, cs, sr, path)
        created["margin"] = path
        path = out.out_path(gdb, run + "_PassFail")
        out.write_passfail(arr["code"].reshape(ny, nx), ll, cs, sr, path)
        created["passfail"] = path
        tick("margin and pass/fail rasters")
    if detail:
        ids_src = np.array([s["id"] for s in sources], dtype="float64")
        dom = arr["dom"]
        arr["dom_id"] = np.where(np.isfinite(dom), ids_src[np.clip(np.nan_to_num(dom, nan=1).astype(int) - 1, 0,
                                                                     len(sources) - 1)], np.nan)
        ids = np.arange(1, ncell + 1, dtype="int32")
        v = np.isfinite(arr["LAeq"])
        sub = {k: a[v] for k, a in arr.items() if isinstance(a, np.ndarray) and a.shape[:1] == (ncell,)}
        struct = out.cell_arrays(sub, int(v.sum()), ids[v], has_lim, has_lim and any(lim["bands_set"]))
        ids2d = np.where(v.reshape(ny, nx), ids.reshape(ny, nx), 0)
        path = out.out_path(gdb, run + "_Cells")
        out.write_cells(ids2d, struct, ll, cs, sr, path)
        created["cells"] = path
        tick("click-to-inspect cells")
    if p.get("copy_inputs", True):
        for role, fc, nm in (("in_sources", p["sources"], "_Sources"), ("in_barriers", bar, "_Barriers"),
                             ("in_area", area_fc, "_Area")):
            if fc:
                path = out.out_path(gdb, run + nm)
                arcpy.management.CopyFeatures(fc, path)
                created[role] = path
    tick("copies of the inputs")
    rows = [("Formula version", None, "", st["mode"]), ("Cells calculated", n_ok, "cells", ""),
            ("Cell size", cs, "m", ""), ("Sources", len(sources), "", ""),
            ("Barriers / buildings", len(obstacles), "", ""), ("LAeq minimum", float(np.nanmin(laeq)), "dB(A)", ""),
            ("LAeq maximum", float(np.nanmax(laeq)), "dB(A)", ""),
            ("LAeq mean (arithmetic over cells)", float(np.nanmean(laeq)), "dB(A)", ""),
            ("Ground factor G", st["G"], "", ""), ("Temperature", st["T_C"], "deg C", ""),
            ("Relative humidity", st["RH"], "%", ""), ("Receiver height", st["hr"], "m", "")]
    if st["extra"]:
        rows.append(("Extra core inputs", None, "", "; ".join("%s=%s" % kv for kv in st["extra"].items())))
    if has_lim:
        code = arr["code"]
        nfail, npass = int((code == 0).sum()), int((code == 1).sum())
        tot = max(nfail + npass, 1)
        m = arr["margin_overall"] if overall is not None else arr["worst_margin"]
        rows += [("Overall limit", overall, "dB(A)", "none" if overall is None else ""),
                 ("Area above a limit", nfail * cs * cs, "m2", "cells where any limit is exceeded"),
                 ("Share of the area above a limit", 100.0 * nfail / tot, "%", ""),
                 ("Largest exceedance", float(np.nanmax(np.where(code == 0, m, np.nan))) if nfail else 0.0, "dB", "")]
        log.msg("Allowed-level check: %d cells PASS, %d cells FAIL (%.1f %% of the area above a limit)." %
                (npass, nfail, 100.0 * nfail / tot))
    path = out.out_path(gdb, run + "_Summary")
    out.write_summary(rows, path)
    created["summary"] = path
    tick("summary table")

    step("adding to the map")
    sink = out.MapSink(bool(p.get("add_map", True)), log)
    if sink.on:
        _add_noise_map(sink, run, created, has_lim, overall, p)
    for k, v in created.items():
        log.msg("Created %s: %s" % (k, v))
    return created


def _add_noise_map(sink, run, c, has_lim, overall, p):
    top = sink.group("NoiseBox: " + run)
    g_in = sink.group(run + " | 4 Inputs", top, visible=False)
    g_ins = sink.group(run + " | 3 Inspect", top) if "cells" in c else None
    g_lim = sink.group(run + " | 2 Allowed levels", top) if has_lim else None
    g_res = sink.group(run + " | 1 Results", top)
    if "in_area" in c:
        sink.add(c["in_area"], g_in, run + " area", style=out.style_area)
    if "in_barriers" in c:
        sink.add(c["in_barriers"], g_in, run + " barriers", style=out.style_barriers)
    if "in_sources" in c:
        sink.add(c["in_sources"], g_in, run + " sources")
    if "cells" in c:
        sink.add(c["cells"], g_ins, "Detail cells: click a cell to read all values", style=out.style_invisible_cells)
    if has_lim:
        if "margin" in c:
            sink.add(c["margin"], g_lim, "Margin to limit (dB, + = exceeds)", visible=False, style=out.style_margin)
        sink.add(c["passfail"], g_lim, "Allowed levels (PASS / FAIL)", style=out.style_passfail)
    if p.get("bands"):
        g_b = sink.group(run + " | Octave bands (Lp, unweighted)", g_res, visible=False)
        for b in reversed(BANDS):
            sink.add(c["Lp%d" % b], g_b, "Lp %d Hz (dB)" % b, visible=False, style=out.style_level)
    if "bands" in c:
        sink.add(c["bands"], g_res, "Noise bands dB(A)", visible=False, style=out.style_bands)
    sink.add(c["laeq"], g_res, "LAeq dB(A)", style=out.style_level)


# ---------------------------------------------------------------- receivers
def receivers(p, log):
    arcpy = aio._arcpy()
    step = _Step(log, 4)
    step("checking the inputs")
    gdb = _need_gdb(p)
    engine.check_core_up_to_date(log)
    st = settings(p)
    sr, sources, bar, bfield = _inputs(p, log)
    rec_fc = p.get("receivers")
    if not rec_fc:
        raise NoiseBoxError("Choose the receiver layer (point features).")
    rdesc = arcpy.Describe(rec_fc)
    if rdesc.shapeType != "Point":
        raise NoiseBoxError("Receivers must be a point feature class.")
    aio.require_metric_projected(rdesc.spatialReference, "The receiver layer")
    run = out.unique_run_name(gdb, p.get("run_name") or "Receivers")
    path_out = out.out_path(gdb, run + "_Receivers")
    arcpy.management.CopyFeatures(rec_fc, path_out)
    hname = p.get("rh_field")
    hf = aio.find_field(path_out, hname, "Receiver height") if hname else None
    recs, oids = [], []
    flds = ["OID@", "SHAPE@XY"] + ([hf] if hf else [])
    with arcpy.da.SearchCursor(path_out, flds, spatial_reference=sr) as cur:
        for row in cur:
            h = row[2] if hf else None
            if h is None:
                h = st["hr"]
            if row[1] is None or row[1][0] is None:
                continue
            if not math.isfinite(h) or h <= 0:
                raise NoiseBoxError("Receiver OID %s: height must be greater than 0." % row[0])
            oids.append(row[0])
            recs.append({"x": float(row[1][0]), "y": float(row[1][1]), "h": float(h)})
    if not recs:
        raise NoiseBoxError("The receiver layer has no features.")
    log.msg("Receivers: %d." % len(recs))
    step("reading barriers and elevation")
    bbox = _bbox([(s["x"], s["y"]) for s in sources] + [(r["x"], r["y"]) for r in recs])
    obstacles, dem = _scene(p, sr, bbox, bar, bfield, log)
    job = _job(st, sources, obstacles, dem)
    job["receivers"] = recs
    step("calculating")
    arr = engine.run("points", job, log)
    n = len(recs)
    ids_src = np.array([s["id"] for s in sources], dtype="float64")
    arr["dom_id"] = np.where(np.isfinite(arr["dom"]),
                             ids_src[np.clip(np.nan_to_num(arr["dom"], nan=1).astype(int) - 1, 0, len(sources) - 1)],
                             np.nan)
    lim = st["limits"]
    has_lim = lim is not None
    sub = {k: a for k, a in arr.items() if isinstance(a, np.ndarray) and a.shape[:1] == (n,)}
    struct = out.cell_arrays(sub, n, np.array(oids, dtype="int32"), has_lim, has_lim and any(lim["bands_set"]))
    step("writing the results into the copy of the receivers")
    existing = {f.name.lower() for f in arcpy.ListFields(path_out)}
    names = [x for x in struct.dtype.names if x != "Cell_ID"]
    for nm in names:
        if nm.lower() in existing:
            raise NoiseBoxError("The receiver layer already has a field named %s; rename that field first." % nm)
        if struct.dtype[nm].kind == "U":
            arcpy.management.AddField(path_out, nm, "TEXT", field_length=24)
        else:
            arcpy.management.AddField(path_out, nm, "DOUBLE")
    lut = {int(o): i for i, o in enumerate(oids)}
    with arcpy.da.UpdateCursor(path_out, ["OID@"] + names) as cur:
        for row in cur:
            i = lut.get(row[0])
            if i is None:
                continue
            vals = []
            for nm in names:
                v = struct[nm][i]
                vals.append(str(v) if struct.dtype[nm].kind == "U" else (None if not math.isfinite(v) else float(v)))
            cur.updateRow([row[0]] + vals)
    nbad = int((~np.isfinite(arr["LAeq"])).sum())
    log.msg("Wrote %d fields to %s" % (len(names), path_out))
    if has_lim:
        stt = _status_of(arr["code"])
        log.msg("Allowed-level check at the receivers: %d PASS, %d FAIL." % (int((stt == "PASS").sum()),
                                                                          int((stt == "FAIL").sum())))
    if nbad:
        why = {}
        for r in arr["reasons"]:
            if r:
                why[r] = why.get(r, 0) + 1
        log.warn("%d receiver(s) have no value (%s)." % (nbad, "; ".join("%s: %d" % kv for kv in why.items())
                                                         or "outside the elevation raster or inside a barrier"))
    sink = out.MapSink(bool(p.get("add_map", True)), log)
    if sink.on:
        top = sink.group("NoiseBox: " + run)
        sink.add(path_out, top, run + " receivers (click for levels)")
    return {"receivers": path_out}


# ---------------------------------------------------------------- compare
def compare(p, log):
    arcpy = aio._arcpy()
    gdb = _need_gdb(p)
    a, b = p.get("baseline"), p.get("scenario")
    if not a or not b:
        raise NoiseBoxError("Choose the baseline raster and the scenario raster.")
    ra, rb = arcpy.Raster(a), arcpy.Raster(b)
    ea, eb = ra.extent, rb.extent
    if (abs(ra.meanCellWidth - rb.meanCellWidth) > 1e-6 or abs(ea.XMin - eb.XMin) > 1e-3 or abs(ea.YMin - eb.YMin) > 1e-3
            or ra.width != rb.width or ra.height != rb.height):
        raise NoiseBoxError("The two rasters are not on the same grid (extent / cell size). Run both noise maps with "
                            "the same calculation area and cell size.")
    A = arcpy.RasterToNumPyArray(ra, nodata_to_value=np.nan).astype("float64")
    B = arcpy.RasterToNumPyArray(rb, nodata_to_value=np.nan).astype("float64")
    D = B - A
    ok = np.isfinite(D)
    if not ok.any():
        raise NoiseBoxError("The rasters have no cells with values in both.")
    run = out.unique_run_name(gdb, p.get("run_name") or "Compare")
    path = out.out_path(gdb, run + "_Change")
    cs = ra.meanCellWidth
    out.write_raster(np.flipud(D), (ea.XMin, ea.YMin), cs, ra.spatialReference, path)
    thr = float(p.get("threshold") or 3.0)
    n = int(ok.sum())
    quieter, louder = int((D <= -thr).sum()), int((D >= thr).sum())
    log.msg("Change (scenario minus baseline): min %.1f, max %.1f, mean %.2f dB over %d cells." %
            (np.nanmin(D), np.nanmax(D), np.nanmean(D), n))
    log.msg("Quieter by at least %g dB: %.1f %% of the cells (%d m2); louder by at least %g dB: %.1f %% (%d m2)." %
            (thr, 100.0 * quieter / n, quieter * cs * cs, thr, 100.0 * louder / n, louder * cs * cs))
    sink = out.MapSink(bool(p.get("add_map", True)), log)
    if sink.on:
        top = sink.group("NoiseBox: " + run)
        sink.add(path, top, "Change in dB(A) (negative = quieter)", style=out.style_diff)
    return {"change": path}


# ---------------------------------------------------------------- input layers
def create_inputs(p, log):
    gdb = _need_gdb(p)
    sr = p.get("sr") or aio.default_template_sr()
    aio.require_metric_projected(sr, "The chosen coordinate system")
    made = aio.create_layers(gdb, p.get("prefix") or "NB_", sr)
    for k, v in made.items():
        log.msg("Created %s: %s" % (k, v))
    sink = out.MapSink(bool(p.get("add_map", True)), log)
    if sink.on:
        top = sink.group("NoiseBox inputs: " + (p.get("prefix") or "NB_"))
        sink.add(made["area"], top, "Calculation area", style=out.style_area)
        sink.add(made["receivers"], top, "Receivers")
        sink.add(made["barriers"], top, "Barriers / buildings", style=out.style_barriers)
        sink.add(made["sources"], top, "Sources")
    log.msg("Draw features with the Create Features pane. Sources need h_src and Lw_63 ... Lw_8000 "
            "(dB re 1 pW, unweighted); barriers need h_bar (m above ground).")
    return made


# ---------------------------------------------------------------- status
def check(log):
    """Report on the Python core and run one calculation as a self-test. Needs no MATLAB."""
    st = engine.core_status()
    if not st["ok"]:
        log.warn("The Python core cannot be loaded: %s" % st["problem"])
        log.msg("Run matlab/nb_export_python.m in MATLAB to create it.")
        return False
    log.msg("MATLAB core folder: %s" % st["core_dir"])
    log.msg("Python core generated: %s, %d functions." % (st["generated"], st["n_functions"]))
    ok = True
    if st["stale"] or st["missing"] or st["new"]:
        ok = False
        if st["stale"]:
            log.warn("Edited in MATLAB after the export: %s" % ", ".join(st["stale"]))
        if st["new"]:
            log.warn("New in MATLAB, not exported yet: %s" % ", ".join(st["new"]))
        if st["missing"]:
            log.warn("Deleted in MATLAB, still in Python: %s" % ", ".join(st["missing"]))
        log.warn("Run nb_export_python in MATLAB to bring the Python core up to date.")
    else:
        log.msg("The Python core matches the MATLAB files (checked by file hash).")
    for n, why in sorted(st["not_translated"].items()):
        log.msg("Not exported (not needed by these tools): %s" % why)
    if st["accelerated"]:
        log.msg("Hand-optimised versions in use (checked against MATLAB at the export): %s" % ", ".join(st["accelerated"]))
    for note in st["notes"]:
        log.warn(note)
    cp = engine.core()
    from . import mrt
    c = mrt.Struct(Lw=np.full((1, 8), 90.0), hs=1.0, hr=1.5, dp=100.0,
                   G=mrt.Struct(Gs=0.5, Gm=0.5, Gr=0.5), atm=mrt.Struct(T_C=15.0, RH=70.0, p_kPa=101.325), mode="iso2024")
    o = cp.run_acoustic_case(c)
    log.msg("Self-test (Lw = 90 dB in every band, 100 m, G = 0.5, 15 deg C, 70 %%): LpA = %.2f dB(A), Lp = %.2f dB" %
            (float(o["LpA_broadband"]), float(o["Lp_broadband"])))
    log.msg("Calculation processes available: %d (of %d cores)." % (config.worker_count(64), os.cpu_count() or 1))
    return ok
