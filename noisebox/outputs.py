"""Writing results (rasters, polygons, tables) and adding them to the active map in groups. Needs arcpy."""
import math
import os
import time

import numpy as np

from .config import BANDS
from .arcgis_io import NODATA, _arcpy

STATUS = {1: "PASS", 0: "FAIL", -1: "NO LIMITS"}
PATH_TYPE = {0: "free (no screening)", 1: "blocked (diffraction)", 2: "clear crest"}


# ---------------------------------------------------------------- naming
def out_path(gdb, name):
    arcpy = _arcpy()
    return os.path.join(gdb, arcpy.ValidateTableName(name, gdb))


def unique_run_name(gdb, base):
    """Run name that does not collide with existing items: base, base_2, base_3 ..."""
    arcpy = _arcpy()
    arcpy.env.workspace = gdb
    existing = {n.lower() for n in (arcpy.ListRasters() or []) + (arcpy.ListFeatureClasses() or []) +
                (arcpy.ListTables() or [])}
    base = arcpy.ValidateTableName(base, gdb)
    name, i = base, 1
    while any(e.startswith((name + "_").lower()) or e == name.lower() for e in existing):
        i += 1
        name = "%s_%d" % (base, i)
    return name


# ---------------------------------------------------------------- rasters
def write_raster(array_ny_nx, lower_left, cs, sr, path, dtype="float32"):
    """Rows follow increasing y (MATLAB order); NaN -> NoData."""
    arcpy = _arcpy()
    a = np.flipud(np.asarray(array_ny_nx, dtype="float64")).copy()
    bad = ~np.isfinite(a)
    if dtype == "uint8":
        a = np.where(bad, 255, a).astype("uint8")
        nodata = 255
    else:
        a = np.where(bad, NODATA, a).astype("float32")
        nodata = NODATA
    ras = arcpy.NumPyArrayToRaster(a, arcpy.Point(lower_left[0], lower_left[1]), cs, cs, value_to_nodata=nodata)
    ras.save(path)
    arcpy.management.DefineProjection(path, sr)
    return path


def write_passfail(code, lower_left, cs, sr, path):
    """1 = PASS, 0 = FAIL raster with a 'Status' text column in its attribute table."""
    arcpy = _arcpy()
    c = np.where(np.isin(code, (0, 1)), code, np.nan)
    write_raster(c, lower_left, cs, sr, path, dtype="uint8")
    try:
        arcpy.management.BuildRasterAttributeTable(path, "OVERWRITE")
        arcpy.management.AddField(path, "Status", "TEXT", field_length=10)
        with arcpy.da.UpdateCursor(path, ["Value", "Status"]) as cur:
            for v, _ in cur:
                cur.updateRow([v, "PASS" if v == 1 else "FAIL"])
    except Exception:
        pass
    return path


# ---------------------------------------------------------------- polygons
def write_isophones(laeq, lower_left, cs, sr, step, path):
    """Noise bands: polygons of equal dB(A) class (floor(L/step)*step) with LAeq_lo / LAeq_hi / Label."""
    arcpy = _arcpy()
    cls = np.floor(laeq / step) * step
    tmp = "memory/nb_iso_cls"
    ras_path = write_raster(cls, lower_left, cs, sr, tmp, dtype="float32")
    ints = "memory/nb_iso_int"
    try:
        arcpy.management.CopyRaster(ras_path, ints, pixel_type="32_BIT_SIGNED")
        arcpy.conversion.RasterToPolygon(ints, path, "SIMPLIFY", "Value")
    finally:
        for t in (tmp, ints):
            try:
                arcpy.management.Delete(t)
            except Exception:
                pass
    arcpy.management.AddField(path, "LAeq_lo", "DOUBLE", field_alias="Band from (dB(A))")
    arcpy.management.AddField(path, "LAeq_hi", "DOUBLE", field_alias="Band to (dB(A))")
    arcpy.management.AddField(path, "Label", "TEXT", field_length=24)
    with arcpy.da.UpdateCursor(path, ["gridcode", "LAeq_lo", "LAeq_hi", "Label"]) as cur:
        for g, _, _, _ in cur:
            lo = float(g)
            hi = lo + step
            cur.updateRow([g, lo, hi, "%g-%g dB(A)" % (lo, hi)])
    return path


def cell_arrays(arr, n, ids, has_limits, has_band_limits):
    """Structured array (Cell_ID + all attributes) for the cells whose LAeq is valid."""
    cols = [("Cell_ID", "i4", ids)]
    la = arr["LAeq"]
    cols.append(("LAeq", "f8", la))
    if has_limits:
        cols.append(("Status", "U10", np.array([STATUS.get(int(c), "NO DATA") if np.isfinite(c) else "NO DATA"
                                                  for c in arr["code"]])))
        cols.append(("Margin_dBA", "f8", arr["margin_overall"]))
        cols.append(("Worst_Hz", "f8", np.array([BANDS[int(b) - 1] if np.isfinite(b) and b >= 1 else np.nan
                                                  for b in arr["worst_band"]])))
        cols.append(("Worst_dB", "f8", arr["worst_margin"]))
    if "LZ" in arr:
        cols.append(("LZ", "f8", arr["LZ"]))               # unweighted energy sum of the 8 bands
    for i, b in enumerate(BANDS):
        cols.append(("Lp_%d" % b, "f8", arr["Lp"][:, i]))
    for i, b in enumerate(BANDS):
        cols.append(("LpA_%d" % b, "f8", arr["LpA"][:, i]))
    if "Adiv" in arr:
        cols.append(("DomSrc", "f8", arr["dom_id"]))
        cols.append(("Dist_m", "f8", arr["dist"]))
        cols.append(("Ground_m", "f8", arr["ground"]))
        cols.append(("PathType", "U24", np.array([PATH_TYPE.get(int(k), "") if np.isfinite(k) else ""
                                                  for k in arr["kind"]])))
        for key in ("Adiv", "Aatm", "Agr", "Abar"):
            for i, b in enumerate(BANDS):
                cols.append(("%s_%d" % (key, b), "f8", arr[key][:, i]))
    if has_band_limits and "margin_bands" in arr:
        for i, b in enumerate(BANDS):
            cols.append(("Marg_%d" % b, "f8", arr["margin_bands"][:, i]))
    dtype = [(n, t) for n, t, _ in cols]
    out = np.empty(len(ids), dtype=dtype)
    for n, _, v in cols:
        out[n] = v
    return out


def write_cells(ids2d, struct, lower_left, cs, sr, path):
    """Square polygons (one per valid cell) carrying every attribute: click a cell with Identify to read them.

    Fast route: the attributes go into a point feature class in one call (NumPyArrayToFeatureClass), its schema
    becomes the schema of the polygon class, and the polygons are written with one InsertCursor (WKT geometry).
    """
    arcpy = _arcpy()
    ids = np.asarray(struct["Cell_ID"], dtype=np.int64) - 1                       # row-major index into the grid
    ny, nx = ids2d.shape
    iy, ix = ids // nx, ids % nx
    x0 = lower_left[0] + ix * cs
    y0 = lower_left[1] + iy * cs
    dtype = [("CX", "f8"), ("CY", "f8")] + [(n, struct.dtype[n]) for n in struct.dtype.names]
    pts = np.empty(len(struct), dtype=dtype)
    pts["CX"], pts["CY"] = x0 + cs / 2.0, y0 + cs / 2.0
    for n in struct.dtype.names:
        pts[n] = struct[n]
    tmp = "memory/nb_cells_pts"
    try:
        arcpy.da.NumPyArrayToFeatureClass(pts, tmp, ("CX", "CY"), sr)
        arcpy.management.DeleteField(tmp, ["CX", "CY"])
        d, n = os.path.split(path)
        arcpy.management.CreateFeatureclass(d, n, "POLYGON", template=tmp, spatial_reference=sr)
    finally:
        try:
            arcpy.management.Delete(tmp)
        except Exception:
            pass
    names = [f.name for f in arcpy.ListFields(path) if f.type not in ("OID", "Geometry")
             and f.name.lower() not in ("shape_length", "shape_area")]
    cols = []
    for nm in names:
        a = struct[nm]
        if a.dtype.kind == "f":
            cols.append([None if not math.isfinite(v) else float(v) for v in a])
        elif a.dtype.kind in "iu":
            cols.append([int(v) for v in a])
        else:
            cols.append([str(v) for v in a])
    wkt = ["POLYGON ((%r %r, %r %r, %r %r, %r %r, %r %r))" % (x, y, x + cs, y, x + cs, y + cs, x, y + cs, x, y)
           for x, y in zip(x0.tolist(), y0.tolist())]
    with arcpy.da.InsertCursor(path, ["SHAPE@WKT"] + names) as cur:
        for row in zip(wkt, *cols):
            cur.insertRow(row)
    return path


def write_summary(rows, path):
    arcpy = _arcpy()
    d, n = os.path.split(path)
    arcpy.management.CreateTable(d, n)
    arcpy.management.AddField(path, "Item", "TEXT", field_length=60)
    arcpy.management.AddField(path, "Value", "DOUBLE")
    arcpy.management.AddField(path, "Unit", "TEXT", field_length=20)
    arcpy.management.AddField(path, "Note", "TEXT", field_length=120)
    with arcpy.da.InsertCursor(path, ["Item", "Value", "Unit", "Note"]) as cur:
        for item, val, unit, note in rows:
            cur.insertRow([item, None if val is None or not math.isfinite(val) else float(val), unit, note])
    return path


# ---------------------------------------------------------------- map
class MapSink:
    """Adds outputs to the active map inside group layers. Does nothing outside ArcGIS Pro."""

    def __init__(self, enabled, log):
        self.log = log
        self.m = None
        self.aprx = None
        self.failed = False
        if not enabled:
            return
        arcpy = _arcpy()
        try:
            self.aprx = arcpy.mp.ArcGISProject("CURRENT")
            self.m = self.aprx.activeMap
            if self.m is None:
                self.log.warn("No active map: results were written to the geodatabase but not added to a map.")
        except Exception:
            self.m = None
            self.log.msg("(Not running inside ArcGIS Pro: results are not added to a map.)")

    @property
    def on(self):
        return self.m is not None

    def _find(self, name, group=False):
        for lyr in self.m.listLayers(name):
            if lyr.name == name and (lyr.isGroupLayer == group):
                return lyr
        return None

    def group(self, name, parent=None, visible=True):
        if not self.on:
            return None
        g = self.m.createGroupLayer(name)
        if parent is not None:
            self.m.addLayerToGroup(parent, g)
            self.m.removeLayer(g)
            g = self._find(name, group=True)
        if g is not None:
            g.visible = visible
        return g

    def add(self, path, group, name, visible=True, style=None):
        """Add a dataset to `group` (or the map root), rename it, optionally style it."""
        if not self.on:
            return None
        if self.failed:
            return None
        try:
            lyr = self.m.addDataFromPath(path)
        except RuntimeError as e:
            self.failed = True
            self.log.warn("The result layers could not be added to the map (%s). The data is saved in the geodatabase: "
                          "drag it into the map from the Catalog pane." % e)
            return None
        if group is not None:
            self.m.addLayerToGroup(group, lyr)
            self.m.removeLayer(lyr)
            base = os.path.basename(path)
            cand = [x for x in group.listLayers() if x.supports("DATASOURCE") and
                    os.path.normcase(x.dataSource).endswith(os.path.normcase(base))]
            lyr = cand[0] if cand else None
        if lyr is None:
            return None
        lyr.name = name
        lyr.visible = visible
        if style:
            try:
                style(lyr, self.aprx)
            except Exception as e:  # symbology is cosmetic
                self.log.msg("(Could not style %s: %s)" % (name, e))
        return lyr


# ---------------------------------------------------------------- styles
def _ramp(aprx, *names):
    for n in names:
        r = aprx.listColorRamps(n)
        if r:
            return r[0]
    return None


def style_level(lyr, aprx):
    sym = lyr.symbology
    sym.updateColorizer("RasterStretchColorizer")
    sym.colorizer.stretchType = "MinimumMaximum"
    ramp = _ramp(aprx, "Orange-Red (Continuous)", "Yellow-Orange-Red")
    if ramp:
        sym.colorizer.colorRamp = ramp
    lyr.symbology = sym


def style_margin(lyr, aprx):
    sym = lyr.symbology
    sym.updateColorizer("RasterStretchColorizer")
    sym.colorizer.stretchType = "MinimumMaximum"
    ramp = _ramp(aprx, "Red to Green Diverging, Bright")
    if ramp:
        sym.colorizer.colorRamp = ramp
        sym.colorizer.invertColorRamp = True      # positive (exceedance) = red
    lyr.symbology = sym


def style_diff(lyr, aprx):
    style_margin(lyr, aprx)                       # reduction (negative) = green, increase = red


def style_passfail(lyr, aprx):
    sym = lyr.symbology
    sym.updateColorizer("RasterUniqueValueColorizer")
    sym.colorizer.field = "Status"
    for grp in sym.colorizer.groups:
        for item in grp.items:
            item.color = {"RGB": [215, 48, 39, 200]} if item.label == "FAIL" else {"RGB": [26, 152, 80, 120]}
    lyr.symbology = sym


def style_bands(lyr, aprx):
    sym = lyr.symbology
    sym.updateRenderer("UniqueValueRenderer")
    sym.renderer.fields = ["Label"]
    ramp = _ramp(aprx, "Orange-Red (Continuous)", "Yellow-Orange-Red")
    if ramp:
        sym.renderer.colorRamp = ramp
    lyr.symbology = sym


def style_invisible_cells(lyr, aprx):
    """Fully transparent cells (and outline) so Identify still works on them without hiding the rasters."""
    sym = lyr.symbology
    sym.renderer.symbol.color = {"RGB": [0, 0, 0, 0]}
    sym.renderer.symbol.outlineColor = {"RGB": [0, 0, 0, 0]}
    lyr.symbology = sym


def style_barriers(lyr, aprx):
    sym = lyr.symbology
    sym.renderer.symbol.color = {"RGB": [80, 80, 80, 255]}
    lyr.symbology = sym


def style_area(lyr, aprx):
    sym = lyr.symbology
    sym.renderer.symbol.color = {"RGB": [0, 0, 0, 0]}
    sym.renderer.symbol.outlineColor = {"RGB": [20, 20, 20, 255]}
    sym.renderer.symbol.outlineWidth = 1.5
    lyr.symbology = sym
