"""Locations, constants and settings. No arcpy import here (so the engine can run in plain Python)."""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BANDS = (63, 125, 250, 500, 1000, 2000, 4000, 8000)
P_KPA = 101.325                      # ISO 9613-1 reference pressure; not a tool option (see "Extra core inputs")
MODES = {
    "ISO 9613-2:2024 (default)": "iso2024",
    "ISO 9613-2:1996 (benchmark compatibility, 20 deg C / 70 % only)": "iso1996",
    "ISO 9613-2:2024 draft amendment (experimental)": "draft2026",
}


class NoiseBoxError(Exception):
    """A problem the user can fix (bad input, missing data ...). Shown as one clean tool error."""


def core_dir():
    """Folder with the MATLAB core (.m files). NOISEBOX_CORE_DIR overrides it (used by tests)."""
    return os.environ.get("NOISEBOX_CORE_DIR") or os.path.join(ROOT, "matlab", "core")


def _config_value(key, default=None):
    path = os.path.join(ROOT, "config.json")
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                v = (json.load(f) or {}).get(key)
            if v is not None:
                return v
        except (OSError, ValueError):
            pass
    return default


def worker_count(n_jobs):
    """Number of parallel worker processes: NOISEBOX_WORKERS, config.json "workers", else all cores but one."""
    v = os.environ.get("NOISEBOX_WORKERS") or _config_value("workers")
    try:
        n = int(v) if v else max(1, (os.cpu_count() or 2) - 1)
    except (TypeError, ValueError):
        n = max(1, (os.cpu_count() or 2) - 1)
    return max(1, min(n, 32, max(1, n_jobs)))


def python_exe():
    """python.exe used for the worker processes (ArcGIS Pro's own Python)."""
    import sys
    cand = [os.environ.get("NOISEBOX_PYTHON"), _config_value("python"),
            os.path.join(sys.exec_prefix, "python.exe"), sys.executable]
    for c in cand:
        if c and os.path.isfile(c) and os.path.basename(c).lower().startswith("python"):
            return c
    raise NoiseBoxError("Could not find python.exe for the calculation workers. Set the environment variable "
                        "NOISEBOX_PYTHON or \"python\" in config.json.")
