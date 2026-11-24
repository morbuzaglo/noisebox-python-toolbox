# NoiseBox (Python toolbox for ArcGIS Pro)

ISO 9613-2 noise maps in ArcGIS Pro. A normal Python toolbox: add `NoiseBox.pyt` to a project and run the tools.
The acoustics are **your MATLAB core** (`matlab/core/*.m`), automatically translated to Python, so the calculation
runs inside Pro (no MATLAB needed to run the tools) and on all CPU cores.

```
NoiseBox.pyt              the tool dialogs (thin)
noisebox/                 pipeline.py (what each tool does), engine.py (calculation loops), worker.py,
                          arcgis_io.py / outputs.py (read inputs, write results), mrt.py (MATLAB runtime)
noisebox/core_py/         GENERATED Python version of matlab/core (do not edit)
matlab/core/              YOUR MATLAB functions (the physics)
matlab/nb_export_python.m THE SCRIPT: translate + prove identical + install
matlab/nb_parity_cases.m  test calls used to compare MATLAB and Python
matlab/python_accel/      optional hand-optimised versions of a few hot functions (see "Speed")
matlab/python_overrides/  hand-written Python for something the translator cannot do
m2py/                     the MATLAB -> Python translator
tests/                    tests (run with propy)
```

## Use the tools (ArcGIS Pro 3.5)

Catalog pane > Toolboxes > right-click > Add Toolbox > `NoiseBox.pyt`.

| Tool | What it does |
|---|---|
| **1 Create Input Layers** | Empty *Sources*, *Barriers*, *Receivers*, *Area* layers with the right fields, added to the map. |
| **2 Noise Map** | LAeq raster (+ noise-band polygons, octave-band rasters, pass/fail against allowed levels, click-to-inspect cells). |
| **3 Noise at Receivers** | Levels and attenuations at receiver points, written as fields on a copy of the receivers. |
| **4 Compare Noise Maps** | Scenario minus baseline, with the share of the area that became quieter / louder. |
| **Check NoiseBox** | Is the Python core up to date with the MATLAB files? Runs a self-test. |

Inputs (all in a projected coordinate system in **metres**):

* **Sources** - points with `h_src` (m above ground) and `Lw_63 ... Lw_8000` (sound power level per octave band, dB re 1 pW, unweighted).
* **Barriers and buildings** (optional) - polygons with `h_bar` (m above ground).
* **Elevation raster** (optional) - flat ground at 0 m if empty.
* **Calculation area** (optional) - a polygon layer, or an extent; otherwise the sources' bounding box + 300 m.

Settings: ground factor G, receiver height, temperature, humidity, formula version. Allowed levels (optional): one overall
dB(A) value and/or eight octave-band values (`-,-,55,50,45,40,-,-`). Everything has a default; the dialog groups
Required / Calculation settings / Allowed levels / Outputs / Advanced.

Time: the calculation uses all cores; writing results through ArcGIS is the slower part (each raster takes a few
seconds, the click-to-inspect cells scale with the number of cells). The messages show how long each output took; switch off
*octave-band rasters* / *click-to-inspect cells* for the fastest run.

**Extra inputs of the MATLAB core** (Advanced): if you add an input to a MATLAB function that it reads from the case
struct `c` (for example `c.C0`, `c.groundMethod`), type `C0=2; groundMethod=simplified` here and it is passed on, no
Python change needed.

What the tools do **not** expose (the core supports it): enclosures, transmission through screens, ground areas with
different G, directivity, per-source settings. They can be added in `noisebox/engine.py` (see `make_base`).

## You change the MATLAB core

Edit anything in `matlab/core` (formulas, add inputs, rename or add functions), then in MATLAB:

```matlab
cd <project>\matlab
nb_export_python
```

(or from a terminal: `matlab -batch "cd('<project>\matlab'); nb_export_python"`). It:

1. translates **every** `.m` file to `noisebox/core_py_new/<name>.py` - same function names, same input and output
   names and order, your help text as docstring, every MATLAB line kept as a comment above its Python line;
2. runs the test calls in `nb_parity_cases.m` in **MATLAB with your files** and in the new Python and compares every
   number, text, struct field and error identifier (ISO/TR 17534-3 benchmark cases T01-T19 included);
3. only if all agree, installs the new package as `noisebox/core_py`. The next tool run uses it (no restart; after
   changing the tools' Python code refresh the toolbox once).

If something differs, the old Python core stays and the report names the case and the value. **Add a test call to
`nb_parity_cases.m` for every new function** (the report lists functions without one). Calls that must fail are fine:
both languages must raise the same error identifier.

The tools warn when `matlab/core` was edited after the last export ("This run uses the OLD Python version").
**Check NoiseBox** shows the same.

### What the translator understands

Functions, local functions, `if/for/while/switch/try`, structs and struct arrays, cells (1-D and 2-D), logical
masks, `end`, growth and deletion, `nargin/nargout/varargin/varargout`, anonymous functions, `containers.Map`, and
about 150 built-ins (see `noisebox/mrt.py`, names `b_<name>`). A construct it does not know stops that file with
the file name and line (nothing is guessed). Files that are not needed by the tools (audio analysis, test lab) may stay
untranslated; if a function the tools call fails, the export stops and the old core is kept. A missing built-in can be
added to `mrt.py` as `b_<name>`; anything else can be written by hand in `matlab/python_overrides/<function>.py` (it then
replaces the translation and is still compared with MATLAB). Details and the few known differences:
`docs/TRANSLATION.md`.

### Speed

The generated code is a literal translation, so a calculation costs about the same per cell as in MATLAB, but there is
no MATLAB start-up and the cells are spread over all cores (`workers` in `config.json` or `NOISEBOX_WORKERS`; default:
cores - 1). For the hottest functions (`nb_geom2d`, `nb_obstacles`, `nb_dem_sample`) there are hand-optimised versions in
`matlab/python_accel`. Each one carries the md5 of the `.m` file it was written for and is **used only while that file
is unchanged**; if you edit the `.m` file the export says so and uses the generated (slower, but exactly yours)
version. They are compared with MATLAB on every export like everything else.

## Tests

```
propy tests\test_translator.py            translator on small MATLAB snippets (no MATLAB)
propy tests\test_engine.py                engine: serial = parallel, energy balance, receivers = grid cells
propy tests\test_pyt.py <folder>          the real toolbox on synthetic data (arcpy)
matlab -batch "nb_export_python"          MATLAB vs Python on 550+ calls incl. ISO/TR 17534-3 T01-T19
```

## Notes

* `config.json` (optional): `{"workers": 4, "python": "C:\\...\\python.exe"}`.
* The MATLAB core folder can be overridden with the environment variable `NOISEBOX_CORE_DIR`.
* Pressure is fixed at 101.325 kPa (use *Extra inputs* only for values the core reads from `c`).
* Never edit `noisebox/core_py` by hand: the next export replaces it.
