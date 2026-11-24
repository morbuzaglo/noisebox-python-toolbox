# ACCELERATOR for matlab/core/nb_geom2d.m  (hand-optimised; used only while the .m file is unchanged)
# MATLAB-MD5: b6570c74c45d78726a0d1d6917cc3bf6
import math
from bisect import bisect_right

import numpy as np

from noisebox import mrt


def _interp(xl, zl, q):
    n = len(xl)
    if q == xl[-1]:
        return zl[-1]
    k = min(max(bisect_right(xl, q) - 1, 0), n - 2)
    x0, x1, y0, y1 = xl[k], xl[k + 1], zl[k], zl[k + 1]
    return y0 + (q - x0) * (y1 - y0) / (x1 - x0)


def nb_geom2d(xp=mrt.UNSET, zp=mrt.UNSET, S=mrt.UNSET, R=mrt.UNSET, nargout=1):
    """NB_GEOM2D diffraction geometry in a vertical X-Z plane (Python accelerator; same results as the .m file)."""
    xl = mrt.asarr(xp).ravel(order="F").tolist()
    zl = mrt.asarr(zp).ravel(order="F").tolist()
    n = len(xl)
    if n != len(zl) or n < 2 or any(xl[i + 1] - xl[i] <= 0 for i in range(n - 1)):
        raise mrt.MatlabError("nb:geom2d:profile", "Profile needs >= 2 vertices with strictly increasing x.")
    Sa, Ra = mrt.asarr(S).ravel(order="F").tolist(), mrt.asarr(R).ravel(order="F").tolist()
    sx, sy, rx, ry = Sa[0], Sa[1], Ra[0], Ra[1]
    if not (sx < rx):
        raise mrt.MatlabError("nb:geom2d:order", "Source must be left of receiver (S(1) < R(1)).")
    if sx < xl[0] or rx > xl[-1]:
        raise mrt.MatlabError("nb:geom2d:domain", "Source or receiver lies outside the terrain profile.")
    tol = 1e-9
    gS = _interp(xl, zl, sx)
    gR = _interp(xl, zl, rx)
    if sy < gS - tol or ry < gR - tol:
        raise mrt.MatlabError("nb:geom2d:underground", "Source or receiver is below the terrain surface.")
    d = math.hypot(rx - sx, ry - sy)
    if d <= 0:
        raise mrt.MatlabError("nb:geom2d:coincident", "Source and receiver coincide.")
    g = mrt.Struct()
    g["hs"] = sy - gS
    g["hr"] = ry - gR
    g["dp"] = rx - sx
    g["dh"] = gR - gS
    g["d"] = d
    g["kind"] = "none"
    g["edges"] = np.zeros((0, 2))
    g["path"] = np.array([[sx, sy], [rx, ry]])
    g["z"] = mrt.empty()
    g["dss"] = mrt.empty()
    g["dsr"] = mrt.empty()
    g["e"] = 0.0
    g["zn"] = mrt.empty()
    lo, hi = sx + tol, rx - tol
    inside = [i for i in range(n) if xl[i] > lo and xl[i] < hi]
    P = [(sx, sy)] + [(xl[i], zl[i]) for i in inside] + [(rx, ry)]
    hull = []
    for p in P:
        px, py = p
        while len(hull) >= 2:
            ax, ay = hull[-2]
            bx, by = hull[-1]
            if (bx - ax) * (py - ay) - (by - ay) * (px - ax) >= -tol:
                hull.pop()
            else:
                break
        hull.append(p)
    inner = hull[1:-1]
    if inner:
        g["kind"] = "blocked"
        g["edges"] = np.array(inner)
        g["path"] = np.array(hull)
        dss = math.hypot(inner[0][0] - sx, inner[0][1] - sy)
        dsr = math.hypot(rx - inner[-1][0], ry - inner[-1][1])
        e = 0.0
        if len(inner) > 1:
            e = float(np.sum(np.hypot(np.diff([p[0] for p in inner]), np.diff([p[1] for p in inner]))))
        g["dss"], g["dsr"], g["e"] = dss, dsr, e
        g["z"] = dss + dsr + e - d
        return g
    best, bi = -math.inf, -1
    for j in inside:                                   # j is the 0-based index; MATLAB's j is j + 1
        if j <= 0 or j >= n - 1:
            continue
        sl = (zl[j] - zl[j - 1]) / (xl[j] - xl[j - 1])
        sr = (zl[j + 1] - zl[j]) / (xl[j + 1] - xl[j])
        if sl - sr > tol:
            ex, ey = xl[j], zl[j]
            zn = -(math.hypot(ex - sx, ey - sy) + math.hypot(rx - ex, ry - ey) - d)
            if zn > best:
                best, bi = zn, j
    if bi >= 0:
        ex, ey = xl[bi], zl[bi]
        g["kind"] = "clear_crest"
        g["edges"] = np.array([[ex, ey]])
        g["path"] = np.array([[sx, sy], [ex, ey], [rx, ry]])
        g["dss"] = math.hypot(ex - sx, ey - sy)
        g["dsr"] = math.hypot(rx - ex, ry - ey)
        g["z"] = best
    return g
