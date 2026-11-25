# -*- coding: utf-8 -*-
"""Writes the 'i' help of every tool parameter (NoiseBox.<Tool>.pyt.xml next to NoiseBox.pyt).

Run with ArcGIS Pro's python, with the toolbox NOT open in Pro (or refresh it afterwards):
    propy docs\\make_help.py
Edit the texts below, run again, then Refresh the toolbox in Catalog.
Every text says what the input is and what happens when it is left empty / at its default.
"""
import importlib.machinery
import importlib.util
import os
import sys
from xml.sax.saxutils import escape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYT = os.path.join(ROOT, "NoiseBox.pyt")

OPT = "Optional. "

# ---- texts shared by several tools -------------------------------------------------------------------------------
HELP = {
    "sources": (
        "The point layer with the noise sources. One point = one source.<br/>"
        "Needed fields: <b>h_src</b> (height of the source above ground, m) and <b>Lw_63, Lw_125, Lw_250, Lw_500, "
        "Lw_1000, Lw_2000, Lw_4000, Lw_8000</b> (sound power level per octave band, dB re 1 pW, unweighted). "
        "'Create Input Layers' makes a ready-made layer.<br/>"
        "Required. The layer must be in a projected coordinate system in metres. Selected features only are used if "
        "the layer has a selection."),
    "out_gdb": (
        "The file geodatabase where all results are written.<br/>"
        "Required. Pre-filled with the default geodatabase of the project."),
    "barriers": (
        OPT + "Polygon layer with buildings and barriers that block or reduce sound. Each polygon needs the height "
        "above ground in the field <b>h_bar</b> (m; field name can be changed under Advanced).<br/>"
        "If left empty: no barriers, sound travels freely."),
    "dem": (
        OPT + "Elevation raster (single band, metres). It is clipped and, if needed, projected to the coordinate "
        "system of the sources. Terrain changes the heights of the sources, receivers and barriers above ground, "
        "and the ground attenuation.<br/>"
        "If left empty: the ground is flat at 0 m."),
    "G": (
        "Ground factor of the ground between source and receiver: 0 = hard ground (asphalt, water, concrete), "
        "1 = porous ground (grass, soil, fields). Values between 0 and 1 are allowed.<br/>"
        "Default: 0.5."),
    "hr": (
        "Height of the receiver (the 'ear') above the ground, in metres. Must be greater than 0.<br/>"
        "Default: 1.5 m. In the map tool every cell uses it. In the receivers tool it is used for receivers that "
        "have no height of their own."),
    "T": (
        "Air temperature in degrees Celsius. It affects the absorption of sound by the air.<br/>"
        "Default: 15 deg C."),
    "RH": (
        "Relative humidity of the air in percent (more than 0, up to 100). It affects the absorption of sound by the "
        "air.<br/>Default: 70 %."),
    "mode": (
        "Which version of the ISO 9613-2 formulas the MATLAB core uses.<br/>"
        "<b>ISO 9613-2:2024</b> is the current standard. <b>1996</b> reproduces the old standard and the "
        "ISO/TR 17534-3 benchmark cases (valid for 20 deg C and 70 % humidity only). The <b>draft amendment</b> is "
        "experimental.<br/>Default: ISO 9613-2:2024."),
    "overall": (
        OPT + "Allowed overall A-weighted level LAeq in dB(A). Cells above it are marked as failing in the "
        "pass/fail output.<br/>"
        "If left empty: no overall limit."),
    "band_limits": (
        OPT + "Allowed levels per octave band, eight values for 63, 125, 250, 500, 1000, 2000, 4000, 8000 Hz, "
        "separated by commas. Write <b>-</b> for a band without limit, for example <b>-,-,55,50,45,40,-,-</b>. "
        "Exactly eight entries are needed.<br/>"
        "If left empty: no band limits. A cell fails if ANY limit (overall or band) is exceeded."),
    "weighting": (
        "How the band limits are compared: with the unweighted band level Lp, or with the A-weighted band level LpA. "
        "Only used when band limits are given.<br/>"
        "Default: unweighted Lp."),
    "run_name": (
        "Start of the name of every output of this run (for example NoiseRun_LAeq). If the name already exists in the "
        "geodatabase a number is added, so nothing is overwritten.<br/>"
        "Default: NoiseRun (Receivers / Compare in the other tools)."),
    "add_map": (
        "Add the results to the active map (grouped, with a ready symbology).<br/>"
        "Default: yes. If off, the results are only written to the geodatabase."),
    "h_field": (
        "Name of the field in the source layer that holds the source height above ground (m).<br/>"
        "Default: h_src."),
    "lw_prefix": (
        "Start of the names of the sound power fields in the source layer. The tool adds the band: with the prefix "
        "<b>Lw_</b> it reads Lw_63, Lw_125 ... Lw_8000.<br/>"
        "Default: Lw_."),
    "b_field": (
        "Name of the field in the barrier layer that holds the height above ground (m). Only used if a barrier layer "
        "is given.<br/>Default: h_bar."),
    "extra": (
        OPT + "Extra inputs for your MATLAB core. If you added an input that the core reads from the case structure "
        "<b>c</b> (for example c.C0), write it here as <b>name=value</b>, several separated by semicolons: "
        "<b>C0=2; groundMethod=simplified</b>. Values can be numbers, true/false, [1 2 3] or text. Names the tool "
        "sets itself (G, mode, dem ...) are refused.<br/>"
        "If left empty: nothing extra is passed and the core uses its own defaults."),
}

# ---- texts that differ per tool ------------------------------------------------------------------------------------
HELP_TOOL = {
    "NoiseMap": {
        "area": (
            OPT + "Polygon layer that defines where the map is calculated (the polygon's outer extent). Cells "
            "outside the polygon stay empty if 'Leave cells outside the area polygon empty' is on.<br/>"
            "If left empty: the extent below is used; if that is empty too, the bounding box of the sources plus "
            "300 m on every side."),
        "extent": (
            OPT + "Alternative to the area layer: draw or type a rectangle. Used only if no area layer is given.<br/>"
            "If left empty: the bounding box of the sources plus 300 m on every side."),
        "cell": (
            OPT + "Size of one map cell in metres. Smaller cells = finer map but much longer calculation "
            "(time grows with the number of cells times the number of sources).<br/>"
            "Filled in automatically as soon as the sources, area or extent are chosen: the value from 1, 2, 5, 10, 20, "
            "25, 50, 100, 200, 250, 500, 1000 m that makes the area about 150 cells across. You can overwrite it; "
            "it follows the area again only while you leave the automatic value. If you clear it, the same "
            "automatic value is used when the tool runs."),
        "run_name": HELP["run_name"],
        "iso_step": (
            "Width of the classes for the noise-band polygons, in dB(A) (for example 5 gives 40-45, 45-50 ...). "
            "Enter 0 for no polygons.<br/>Default: 5."),
        "bands": (
            "Also write one raster per octave band (unweighted level Lp). Takes a few extra seconds per raster.<br/>"
            "Default: off (only the LAeq raster is written)."),
        "detail": (
            "Create the 'click-to-inspect' cells: a polygon layer where clicking a cell shows every band level and "
            "every attenuation (distance, air, ground, barrier ...). Writing it takes longer the more cells there "
            "are, and it is skipped automatically for very large grids.<br/>"
            "Default: on. Switch off for the fastest run."),
        "copy_inputs": (
            "Save a copy of the inputs used (sources, barriers) next to the results so the run can be reproduced "
            "later.<br/>Default: on."),
        "clip": (
            "Only used with an area polygon: cells outside the polygon get no value (instead of filling the whole "
            "bounding rectangle).<br/>Default: on."),
        "add_map": "Add the results of this run to the active map (grouped, with symbology). Default: yes. If off, the "
                   "results are only written to the geodatabase.",
    },
    "NoiseAtReceivers": {
        "receivers": (
            "The point layer with the receivers (houses, windows, measuring points). A copy is written to the "
            "geodatabase with the levels and attenuations as new fields; your layer is not changed.<br/>"
            "Required. Projected coordinate system in metres."),
        "rh_field": (
            OPT + "Name of the field in the receiver layer with the receiver height above ground (m). A receiver with "
            "an empty value there uses the 'Receiver height' below.<br/>"
            "Default: h_rec. If the field is empty or does not exist: all receivers use the 'Receiver height'."),
        "run_name": HELP["run_name"],
        "add_map": "Add the result to the active map. Default: yes. If off, it is only written to the geodatabase.",
    },
    "CompareNoiseMaps": {
        "baseline": (
            "The LAeq raster of the reference situation (for example today), made by 'Noise Map'.<br/>Required."),
        "scenario": (
            "The LAeq raster of the situation to compare (for example with a new barrier), made by 'Noise Map'.<br/>"
            "Required. It must have the same area and cell size as the baseline: run both with the same "
            "calculation area and cell size."),
        "out_gdb": HELP["out_gdb"],
        "threshold": (
            "Change in dB that counts as 'quieter' or 'louder'. The tool reports the share of the area quieter by at "
            "least this value and louder by at least this value.<br/>Default: 3 dB."),
        "run_name": HELP["run_name"],
        "add_map": "Add the difference raster (scenario minus baseline) to the active map. Default: yes.",
    },
    "CreateInputLayers": {
        "out_gdb": ("The file geodatabase where the empty layers are created.<br/>"
                    "Required. Pre-filled with the default geodatabase of the project."),
        "prefix": (
            "Start of the names of the new layers (NB_Sources, NB_Barriers, NB_Receivers, NB_Area).<br/>"
            "Default: NB_. If a name exists already, a number is added; nothing is overwritten."),
        "sr": (
            "Coordinate system of the new layers. It must be projected and in metres.<br/>"
            "Default: the coordinate system of the active map if it is projected in metres, otherwise ITM "
            "(EPSG 2039)."),
        "add_map": "Add the new layers to the active map, ready to draw. Default: yes.",
    },
}

SUMMARY_EXTRA = {
    "CheckNoiseBox": "This tool has no inputs. It shows whether the Python core is up to date with the MATLAB files, "
                     "lists what changed since the last export, and runs a small self-test calculation.",
}

DATATYPE = {"GPFeatureLayer": "Feature Layer", "GPRasterLayer": "Raster Layer", "GPDouble": "Double",
            "GPString": "String", "GPBoolean": "Boolean", "DEWorkspace": "Workspace", "GPExtent": "Extent",
            "GPSpatialReference": "Spatial Reference"}


def load_toolbox():
    loader = importlib.machinery.SourceFileLoader("noisebox_pyt", PYT)
    spec = importlib.util.spec_from_loader("noisebox_pyt", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def help_for(tool, name):
    return HELP_TOOL.get(tool, {}).get(name) or HELP.get(name)


def tool_xml(tool_name, tool):
    parts = []
    missing = []
    for p in tool.getParameterInfo():
        txt = help_for(tool_name, p.name)
        if not txt:
            missing.append(p.name)
            continue
        kind = "Required" if p.parameterType == "Required" else "Optional"
        parts.append(
            '<param name="%s" displayname="%s" type="%s" direction="%s" datatype="%s" expression="">'
            '<dialogReference>%s</dialogReference><pythonReference></pythonReference></param>' % (
                escape(p.name), escape(p.displayName, {'"': "&quot;"}), kind, p.direction,
                DATATYPE.get(p.datatype, escape(str(p.datatype))),
                escape("<DIV STYLE=\"text-align:Left;\"><DIV><P><SPAN>%s</SPAN></P></DIV></DIV>" % txt)))
    summary = SUMMARY_EXTRA.get(tool_name) or tool.description
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<metadata xml:lang="en"><Esri><ArcGISFormat>1.0</ArcGISFormat>'
           '<SyncOnce>TRUE</SyncOnce></Esri><tool name="%s" displayname="%s" toolboxalias="noisebox" '
           'xmlns=""><arcToolboxHelpPath>c:\\program files\\arcgis\\pro\\Resources\\Help\\gp</arcToolboxHelpPath>'
           '<parameters>%s</parameters><summary>%s</summary></tool><dataIdInfo><idCitation><resTitle>%s</resTitle>'
           '</idCitation><idAbs>%s</idAbs></dataIdInfo></metadata>\n' % (
               tool_name, escape(tool.label, {'"': "&quot;"}), "".join(parts), escape(escape(summary)),
               escape(tool.label), escape(summary)))
    return xml, missing


def main():
    mod = load_toolbox()
    bad = 0
    for cls in mod.Toolbox().tools:
        name = cls.__name__
        tool = cls()
        xml, missing = tool_xml(name, tool)
        path = os.path.join(ROOT, "NoiseBox.%s.pyt.xml" % name)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(xml)
        n = xml.count("<param ")
        print("%-20s %2d parameter texts%s" % (name, n, ("  MISSING: " + ", ".join(missing)) if missing else ""))
        bad += len(missing)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
