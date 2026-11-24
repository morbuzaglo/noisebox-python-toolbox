# HAND-WRITTEN override of matlab/core/nb_fingerprint.m (kept in matlab/python_overrides/).
# flake8: noqa
"""Python version of nb_fingerprint.m: md5 of every .m file of the MATLAB core (provenance of a result)."""
import hashlib
import os

from noisebox import mrt


def nb_fingerprint(nargout=1):
    core = os.environ.get("NOISEBOX_CORE_DIR") or os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "matlab", "core")
    names = sorted(f for f in os.listdir(core) if f.lower().endswith(".m")) if os.path.isdir(core) else []
    fp = mrt.Struct()
    fp["file"] = mrt.Cell(names)
    fp["md5"] = mrt.Cell(hashlib.md5(open(os.path.join(core, n), "rb").read()).hexdigest() for n in names)
    fp["modified"] = mrt.hcat(*[os.path.getmtime(os.path.join(core, n)) for n in names]) if names else mrt.empty()
    return fp
