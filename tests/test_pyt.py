"""Run the real toolbox (NoiseBox.pyt) in ArcGIS Pro's Python on synthetic data. No MATLAB needed.

    propy tests\test_pyt.py <output folder>
"""
import os
import shutil
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
CHECKS = []


def check(name, ok, detail=""):
    CHECKS.append((name, bool(ok)))
    print("RESULT %s %s %s" % (name, "ok" if ok else "bad", detail))


def build_data(arcpy, folder):
    gdb_dir = folder
    name = "t.gdb"
    gdb = os.path.join(gdb_dir, name)
    if arcpy.Exists(gdb):
        arcpy.management.Delete(gdb)
    arcpy.management.CreateFileGDB(gdb_dir, name)
    sr = arcpy.SpatialReference(2039)
    x0, y0 = 180000.0, 660000.0
    # layers made by the tool itself
    made = arcpy.noisebox.CreateInputLayers(gdb, "NB_", sr, False)
    src, bar, rec = os.path.join(gdb, "NB_sources"), os.path.join(gdb, "NB_barriers"), os.path.join(gdb, "NB_receivers")
    lw = ["Lw_%d" % b for b in (63, 125, 250, 500, 1000, 2000, 4000, 8000)]
    with arcpy.da.InsertCursor(src, ["SHAPE@XY", "h_src"] + lw) as cur:
        cur.insertRow([(x0 + 100, y0 + 120), 2.0] + [100, 100, 100, 100, 100, 95, 90, 85])
        cur.insertRow([(x0 + 260, y0 + 300), 3.0] + [95, 95, 95, 95, 95, 90, 85, 80])
    with arcpy.da.InsertCursor(bar, ["SHAPE@", "h_bar"]) as cur:
        cur.insertRow([arcpy.Polygon(arcpy.Array([arcpy.Point(x0 + a, y0 + b) for a, b in
                                                  [(140, 100), (160, 100), (160, 140), (140, 140)]]), sr), 9.0])
    with arcpy.da.InsertCursor(rec, ["SHAPE@XY", "h_rec"]) as cur:
        for dx, dy, h in ((250, 120, 1.5), (300, 200, 4.0), (150, 120, None)):
            cur.insertRow([(x0 + dx, y0 + dy), h])
    X, Y = np.meshgrid(np.arange(100), np.arange(100))
    Z = (6 * np.exp(-((X - 40) ** 2 + (Y - 28) ** 2) / 60) + 3 * np.sin(X / 12) * np.cos(Y / 18) + 0.02 * X).astype("float32")
    dem = arcpy.NumPyArrayToRaster(np.flipud(Z), arcpy.Point(x0, y0), 5, 5)
    dem_path = os.path.join(folder, "dem.tif")
    dem.save(dem_path)
    arcpy.management.DefineProjection(dem_path, sr)
    return gdb, src, bar, rec, dem_path, sr


if __name__ == "__main__":
    out = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(ROOT, "tests", "_out")
    os.makedirs(out, exist_ok=True)
    import arcpy
    arcpy.env.overwriteOutput = True
    tb = arcpy.ImportToolbox(os.path.join(ROOT, "NoiseBox.pyt"))
    gdb, src, bar, rec, dem, sr = build_data(arcpy, out)
    tools = [t for t in dir(arcpy.noisebox) if t[0].isupper()]
    check("toolbox_has_tools", {"CreateInputLayers", "NoiseMap", "NoiseAtReceivers", "CompareNoiseMaps",
                                "CheckNoiseBox"} <= set(tools), str(tools))
    arcpy.noisebox.CheckNoiseBox()
    t = time.time()
    arcpy.noisebox.NoiseMap(src, gdb, bar, dem, None, None, 10, 0.5, 1.5, 15, 70, None, 45, "-,-,-,-,-,-,-,-", None,
                            "NM", 5, True, True, True, False, None, None, None, None, True)
    print("noise map took %.1f s" % (time.time() - t))
    ras = os.path.join(gdb, "NM_LAeq")
    check("laeq_raster_exists", arcpy.Exists(ras))
    a = arcpy.RasterToNumPyArray(ras, nodata_to_value=np.nan)
    check("laeq_plausible", np.nanmax(a) > 55 and np.nanmin(a) > 10, "%.1f ... %.1f" % (np.nanmin(a), np.nanmax(a)))
    check("cells_layer_exists", arcpy.Exists(os.path.join(gdb, "NM_Cells")))
    check("passfail_exists", arcpy.Exists(os.path.join(gdb, "NM_PassFail")))
    arcpy.noisebox.NoiseAtReceivers(src, gdb, rec, "h_rec", bar, dem, 0.5, 1.5, 15, 70, None, 45, None, None, "RC",
                                    False, None, None, None, None)
    flds = [f.name for f in arcpy.ListFields(os.path.join(gdb, "RC_Receivers"))]
    check("receiver_fields", "LAeq" in flds and "Lp_1000" in flds and "Adiv_500" in flds, str(flds[:8]))
    vals = [r[0] for r in arcpy.da.SearchCursor(os.path.join(gdb, "RC_Receivers"), ["LAeq"])]
    check("receiver_values", len(vals) == 3 and sum(v is not None for v in vals) >= 2, str(vals))
    arcpy.noisebox.CompareNoiseMaps(ras, ras, gdb, 3, "CP", False)
    d = arcpy.RasterToNumPyArray(os.path.join(gdb, "CP_Change"), nodata_to_value=np.nan)
    check("compare_zero_change", np.nanmax(np.abs(d)) < 1e-6)
    bad = [c for c in CHECKS if not c[1]]
    print("\n%d checks, %d failed" % (len(CHECKS), len(bad)))
    sys.exit(1 if bad else 0)
