"""ArcPy-side data preparation: reading inputs, templates, DEM, grid. Imports arcpy lazily."""
import math
import os

import numpy as np

from . import config
from .config import BANDS, NoiseBoxError

NODATA = -9999.0
CELL_CHOICES = (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000)


def _arcpy():
    import arcpy
    return arcpy


# ---------------------------------------------------------------- spatial reference
def require_metric_projected(sr, what):
    if sr is None or getattr(sr, "name", "") in ("", "Unknown") or sr.type == "Unknown":
        raise NoiseBoxError("%s has no coordinate system. Define one (a projected, metre-based CRS)." % what)
    if sr.type != "Projected":
        raise NoiseBoxError(
            "%s uses a geographic coordinate system (%s, degrees). NoiseBox needs metres: project the data "
            "first (e.g. Israeli TM Grid, EPSG 2039, or the right UTM zone)." % (what, sr.name))
    if abs(sr.metersPerUnit - 1.0) > 1e-9:
        raise NoiseBoxError("%s uses %s units (%.6g m per unit). NoiseBox needs a CRS in metres."
                            % (what, sr.linearUnitName, sr.metersPerUnit))


def default_template_sr():
    """Metric CRS for new drawn features: the active map's CRS if it is projected in metres, else ITM (2039)."""
    arcpy = _arcpy()
    try:
        sr = arcpy.mp.ArcGISProject("CURRENT").activeMap.spatialReference
        if sr is not None and sr.type == "Projected" and abs(sr.metersPerUnit - 1.0) < 1e-9 and sr.factoryCode:
            return sr
    except Exception:
        pass
    return arcpy.SpatialReference(2039)


# ---------------------------------------------------------------- feature templates (drawing on the map)
def create_layers(workspace, prefix, sr):
    """Create empty sources/barriers/receivers/area feature classes with the NoiseBox schema. Returns dict."""
    arcpy = _arcpy()
    out = {}

    def fc(name, geom):
        n = arcpy.ValidateTableName(prefix + name, workspace)
        path = os.path.join(workspace, n)
        if arcpy.Exists(path):
            return path
        arcpy.management.CreateFeatureclass(workspace, n, geom, spatial_reference=sr)
        return path

    s = fc("sources", "POINT")
    if "h_src" not in {f.name for f in arcpy.ListFields(s)}:
        arcpy.management.AddField(s, "h_src", "DOUBLE", field_alias="Source height above ground (m)")
        for b in BANDS:
            arcpy.management.AddField(s, "Lw_%d" % b, "DOUBLE", field_alias="Lw %d Hz (dB re 1 pW)" % b)
        arcpy.management.AddField(s, "Name", "TEXT", field_length=60)
    out["sources"] = s
    b = fc("barriers", "POLYGON")
    if "h_bar" not in {f.name for f in arcpy.ListFields(b)}:
        arcpy.management.AddField(b, "h_bar", "DOUBLE", field_alias="Barrier/building height above ground (m)")
        arcpy.management.AddField(b, "Name", "TEXT", field_length=60)
    out["barriers"] = b
    r = fc("receivers", "POINT")
    if "h_rec" not in {f.name for f in arcpy.ListFields(r)}:
        arcpy.management.AddField(r, "h_rec", "DOUBLE", field_alias="Receiver height above ground (m)")
        arcpy.management.AddField(r, "Name", "TEXT", field_length=60)
    out["receivers"] = r
    a = fc("area", "POLYGON")
    if "Name" not in {f.name for f in arcpy.ListFields(a)}:
        arcpy.management.AddField(a, "Name", "TEXT", field_length=60)
    out["area"] = a
    return out


def feature_count(fc):
    arcpy = _arcpy()
    if not fc:
        return 0
    try:
        return int(arcpy.management.GetCount(fc).getOutput(0))
    except Exception:
        return 0


# ---------------------------------------------------------------- fields
def find_field(fc, name, what):
    arcpy = _arcpy()
    if not name:
        raise NoiseBoxError("No %s field given." % what)
    for f in arcpy.ListFields(fc):
        if f.name.lower() == name.lower():
            if f.type not in ("Double", "Single", "Integer", "SmallInteger", "BigInteger"):
                raise NoiseBoxError("%s field '%s' must be numeric (it is %s)." % (what, f.name, f.type))
            return f.name
    raise NoiseBoxError("%s field '%s' not found in %s." % (what, name, os.path.basename(str(fc))))


def lw_field_names(fc, prefix):
    names = []
    for b in BANDS:
        try:
            names.append(find_field(fc, "%s%d" % (prefix, b), "Lw band %d Hz" % b))
        except NoiseBoxError as e:
            raise NoiseBoxError(str(e) + " Sources need 8 fields %s63 ... %s8000 (unweighted Lw, dB re 1 pW)."
                                % (prefix, prefix))
    return names


# ---------------------------------------------------------------- inputs
def read_sources(fc, sr, height_field, lw_prefix):
    """-> list of dict(id, x, y, h, Lw[8]) in CRS `sr`. Honours selections.

    A NULL height or Lw value is an error (it names the source).
    """
    arcpy = _arcpy()
    hf = find_field(fc, height_field, "Source height")
    lws = lw_field_names(fc, lw_prefix)
    out = []
    with arcpy.da.SearchCursor(fc, ["OID@", "SHAPE@XY", hf] + lws, spatial_reference=sr) as cur:
        for row in cur:
            oid, xy, h = row[0], row[1], row[2]
            lw = list(row[3:])
            if xy is None or xy[0] is None:
                raise NoiseBoxError("Source OID %s has no geometry." % oid)
            if h is None or h < 0:
                raise NoiseBoxError("Source OID %s: height must be a number >= 0 (got %r)." % (oid, h))
            if any(v is None or not math.isfinite(v) for v in lw):
                raise NoiseBoxError("Source OID %s: all 8 Lw band fields must be filled (no nulls)." % oid)
            out.append({"id": int(oid), "x": float(xy[0]), "y": float(xy[1]), "h": float(h),
                        "Lw": [float(v) for v in lw]})
    if not out:
        raise NoiseBoxError("There are no sources: pick a source layer or draw points on the map.")
    return out


def read_obstacles(fc, sr, height_field, bbox, default_h=None):
    """-> list of dict(x[], y[], h). Polygon exterior rings only (holes ignored). Only those touching bbox."""
    arcpy = _arcpy()
    if not fc:
        return []
    desc = arcpy.Describe(fc)
    if desc.shapeType != "Polygon":
        raise NoiseBoxError("Barriers/buildings must be a polygon feature class.")
    hf = find_field(fc, height_field, "Barrier height")
    xmin, ymin, xmax, ymax = bbox
    out = []
    bad = []
    with arcpy.da.SearchCursor(fc, ["OID@", "SHAPE@", hf], spatial_reference=sr) as cur:
        for oid, shp, h in cur:
            if shp is None:
                continue
            e = shp.extent
            if e.XMax < xmin or e.XMin > xmax or e.YMax < ymin or e.YMin > ymax:
                continue
            if h is None and default_h:
                h = default_h
            if h is None or not math.isfinite(h) or h <= 0:
                bad.append(oid)
                continue
            for part in shp:                         # one array of points per part; first ring = exterior
                xs, ys = [], []
                for p in part:
                    if p is None:                    # a None separates the exterior ring from its holes
                        break
                    xs.append(p.X)
                    ys.append(p.Y)
                if len(xs) > 1 and xs[0] == xs[-1] and ys[0] == ys[-1]:
                    xs, ys = xs[:-1], ys[:-1]        # drop the closing vertex
                if len(xs) >= 3:
                    out.append({"x": xs, "y": ys, "h": float(h)})
    if bad:
        raise NoiseBoxError("Barrier height must be a number > 0. Bad OIDs: %s" % ", ".join(map(str, bad[:20])))
    return out


# ---------------------------------------------------------------- calculation area
def read_area(fc, sr):
    """Polygon(s) -> (bbox, rings). rings = list of (xs, ys) numpy arrays, every ring incl. holes (even-odd)."""
    arcpy = _arcpy()
    desc = arcpy.Describe(fc)
    if desc.shapeType != "Polygon":
        raise NoiseBoxError("The calculation area must be a polygon (or use an extent).")
    rings = []
    xs_all, ys_all = [], []
    with arcpy.da.SearchCursor(fc, ["SHAPE@"], spatial_reference=sr) as cur:
        for (shp,) in cur:
            if shp is None:
                continue
            for part in shp:
                xs, ys = [], []
                for p in list(part) + [None]:
                    if p is None:
                        if len(xs) >= 3:
                            rings.append((np.array(xs), np.array(ys)))
                        xs, ys = [], []
                    else:
                        xs.append(p.X)
                        ys.append(p.Y)
                        xs_all.append(p.X)
                        ys_all.append(p.Y)
    if not rings:
        raise NoiseBoxError("The calculation-area polygon layer is empty.")
    return (min(xs_all), min(ys_all), max(xs_all), max(ys_all)), rings


def points_in_rings(x, y, rings):
    """Vectorised even-odd point-in-polygon for flat arrays x, y."""
    inside = np.zeros(x.shape, dtype=bool)
    for rx, ry in rings:
        n = len(rx)
        for i in range(n):
            j = (i + 1) % n
            x1, y1, x2, y2 = rx[i], ry[i], rx[j], ry[j]
            if y1 == y2:
                continue
            cond = (y1 > y) != (y2 > y)
            xint = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            inside ^= cond & (x < xint)
    return inside


def auto_cell(bbox):
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    target = max(w, h) / 150.0
    for c in CELL_CHOICES:
        if c >= target:
            return float(c)
    return float(CELL_CHOICES[-1])


def make_grid(bbox, cs):
    xmin, ymin, xmax, ymax = bbox
    if cs <= 0:
        raise NoiseBoxError("Cell size must be > 0.")
    nx = int(math.ceil((xmax - xmin) / cs - 1e-9))
    ny = int(math.ceil((ymax - ymin) / cs - 1e-9))
    if nx < 1 or ny < 1:
        raise NoiseBoxError("The calculation area is smaller than one cell.")
    return {"x0": xmin + cs / 2.0, "y0": ymin + cs / 2.0, "cs": cs, "nx": nx, "ny": ny}, (xmin, ymin)


# ---------------------------------------------------------------- DEM
def flat_dem(bbox, pad):
    xmin, ymin, xmax, ymax = bbox
    cs = max(xmax - xmin, ymax - ymin) + 2 * pad
    dem = {"x0": xmin - pad, "y0": ymin - pad, "cs": cs, "nx": 2, "ny": 2}
    return dem, np.zeros((2, 2))   # flat ground at elevation 0


def dem_from_raster(raster, sr, bbox, pad):
    """Clip/project the DEM to CRS `sr` over bbox+pad and return (dem dict, Z[iy, ix] y increasing, nodata fraction)."""
    arcpy = _arcpy()
    desc = arcpy.Describe(raster)
    if desc.bandCount != 1:
        raise NoiseBoxError("The DEM must be a single-band raster.")
    dsr = desc.spatialReference
    if dsr is None or dsr.type == "Unknown":
        raise NoiseBoxError("The DEM has no coordinate system.")
    xmin, ymin, xmax, ymax = bbox
    ext = arcpy.Extent(xmin - pad, ymin - pad, xmax + pad, ymax + pad)
    ext.spatialReference = sr
    tmp = []
    try:
        same = bool(dsr.factoryCode) and dsr.factoryCode == sr.factoryCode
        ext_dem = ext if same else ext.projectAs(dsr)
        grow = 3 * max(desc.meanCellWidth, desc.meanCellHeight)
        rect = "%.12f %.12f %.12f %.12f" % (ext_dem.XMin - grow, ext_dem.YMin - grow,
                                           ext_dem.XMax + grow, ext_dem.YMax + grow)
        clip1 = "memory/nb_dem_clip"
        arcpy.management.Clip(raster, rect, clip1, maintain_clipping_extent="NO_MAINTAIN_EXTENT")
        tmp.append(clip1)
        flt = "memory/nb_dem_flt"
        arcpy.management.CopyRaster(clip1, flt, pixel_type="32_BIT_FLOAT")
        tmp.append(flt)
        native = desc.meanCellHeight * (111320.0 if dsr.type == "Geographic" else dsr.metersPerUnit)
        cs = max(round(native, 3), 0.5)
        src = flt
        if not same:
            prj = "memory/nb_dem_prj"
            arcpy.management.ProjectRaster(flt, prj, sr, "BILINEAR", "%s %s" % (cs, cs))
            tmp.append(prj)
            src = prj
        rect2 = "%.6f %.6f %.6f %.6f" % (ext.XMin, ext.YMin, ext.XMax, ext.YMax)
        clip2 = "memory/nb_dem_final"
        arcpy.management.Clip(src, rect2, clip2, maintain_clipping_extent="NO_MAINTAIN_EXTENT")
        tmp.append(clip2)
        r = arcpy.Raster(clip2)
        cw, ch = r.meanCellWidth, r.meanCellHeight
        if abs(cw - ch) > 1e-6 * cw:
            raise NoiseBoxError("DEM cells are not square after projection (%.4f x %.4f)." % (cw, ch))
        arr = arcpy.RasterToNumPyArray(r, nodata_to_value=NODATA).astype("float64")
        arr[arr == NODATA] = np.nan
        Z = np.flipud(arr)                                    # y increasing with row index
        nodata_frac = float(np.isnan(Z).mean())
        info = {"x0": r.extent.XMin + cw / 2.0, "y0": r.extent.YMin + ch / 2.0, "cs": cw,
                "nx": int(Z.shape[1]), "ny": int(Z.shape[0])}
        if Z.shape[0] < 2 or Z.shape[1] < 2:
            raise NoiseBoxError("The DEM covers less than 2x2 cells of the analysis area. Check its extent.")
        return info, Z, nodata_frac
    finally:
        for t in tmp:
            try:
                arcpy.management.Delete(t)
            except Exception:
                pass
