# ACCELERATOR for matlab/core/nb_dem_sample.m  (hand-optimised; used only while the .m file is unchanged)
# MATLAB-MD5: aa11ce765097ba6ebe21fa74d142b2e3
import math

import numpy as np

from noisebox import mrt


def nb_dem_sample(dem=mrt.UNSET, X=mrt.UNSET, Y=mrt.UNSET, nargout=1):
    """NB_DEM_SAMPLE bilinear DEM elevation. Python accelerator: scalar points take a pure-Python path,
    arrays take the vectorised path. Same results as the MATLAB function."""
    tx_, ty_ = type(X), type(Y)
    Zm = dem["Z"]
    if (tx_ is float or tx_ is np.float64) and (ty_ is float or ty_ is np.float64):
        NY, NX = Zm.shape
        fx = (X - dem["x0"]) / dem["cs"] + 1.0
        fy = (Y - dem["y0"]) / dem["cs"] + 1.0
        if not (fx >= 1.0 and fx <= NX and fy >= 1.0 and fy <= NY):
            return float("nan")
        ix = min(max(math.floor(fx), 1), NX - 1)
        iy = min(max(math.floor(fy), 1), NY - 1)
        tx = fx - ix
        ty = fy - iy
        z00 = Zm[iy - 1, ix - 1]
        z10 = Zm[iy - 1, ix]
        z01 = Zm[iy, ix - 1]
        z11 = Zm[iy, ix]
        return (1 - tx) * (1 - ty) * z00 + tx * (1 - ty) * z10 + (1 - tx) * ty * z01 + tx * ty * z11
    X, Y = mrt.asarr(X), mrt.asarr(Y)
    NY, NX = Zm.shape
    fx = (X - dem["x0"]) / dem["cs"] + 1.0
    fy = (Y - dem["y0"]) / dem["cs"] + 1.0
    z = np.full(X.shape, np.nan)
    inb = (fx >= 1) & (fx <= NX) & (fy >= 1) & (fy <= NY)
    ix = np.minimum(np.maximum(np.floor(fx), 1), NX - 1)
    iy = np.minimum(np.maximum(np.floor(fy), 1), NY - 1)
    tx = fx - ix
    ty = fy - iy
    ixi, iyi = np.where(np.isnan(ix), 1, ix).astype(int), np.where(np.isnan(iy), 1, iy).astype(int)
    z00 = Zm[iyi - 1, ixi - 1]
    z10 = Zm[iyi - 1, ixi]
    z01 = Zm[iyi, ixi - 1]
    z11 = Zm[iyi, ixi]
    v = (1 - tx) * (1 - ty) * z00 + tx * (1 - ty) * z10 + (1 - tx) * ty * z01 + tx * ty * z11
    z[inb] = v[inb]
    return mrt.S(z)
