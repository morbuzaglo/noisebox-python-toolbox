# ACCELERATOR for matlab/core/nb_obstacles.m  (hand-optimised; used only while the .m file is unchanged)
# MATLAB-MD5: 1804f4042211b9b3ea3159c14fb34ed7
import math
from bisect import bisect_right

import numpy as np

from noisebox import mrt


def nb_obstacles(action=mrt.UNSET, *varargin, nargout=1):
    """NB_OBSTACLES obstacle footprints for 3D screening (Python accelerator; same results as the .m file).
    Actions: 'resolve', 'intervals', 'profile'."""
    if action == "intervals":
        return _intervals(*varargin)
    if action == "profile":
        return mrt.ret(_profile(*varargin), nargout)
    if action == "resolve":
        return _resolve(*varargin)
    raise mrt.MatlabError("nb:obstacles:action", "unknown action")


def _vec(a):
    return mrt.asarr(a).ravel(order="F").tolist()


def _resolve(dem, obs):
    out = mrt.Cell()
    for k, o in enumerate(obs):
        ox, oy = _vec(o["x"]), _vec(o["y"])
        if len(ox) != len(oy) or len(ox) < 2 or not all(math.isfinite(v) for v in ox) \
                or not all(math.isfinite(v) for v in oy):
            raise mrt.MatlabError("nb:obstacles:shape",
                                  "Obstacle %d: needs matching finite x/y with at least 2 vertices." % (k + 1))
        o = mrt.Struct(o)
        top = o.get("top")
        if top is None or mrt.b_isempty(top):
            h = o.get("h")
            if h is None or mrt.b_isempty(h) or h <= 0:
                raise mrt.MatlabError("nb:obstacles:height", "Obstacle %d: give a positive height h or an absolute top." % (k + 1))
            g = np.asarray(nb_dem_sample(dem, np.array(ox).reshape(-1, 1), np.array(oy).reshape(-1, 1)))
            if np.isnan(g).any():
                raise mrt.MatlabError("nb:obstacles:ground", "Obstacle %d lies over no-data or outside the DEM." % (k + 1))
            o["top"] = float(np.nanmax(g)) + float(h)
        out.append(o)
    return out


def _crossings(px, py, sx, sy, rx, ry):
    dx, dy = rx - sx, ry - sy
    n = len(px)
    nE = 1 if n == 2 else n
    t = []
    for i in range(nE):
        j = (i + 1) % n
        e1, e2 = px[j] - px[i], py[j] - py[i]
        den = dx * e2 - dy * e1
        if abs(den) < 1e-12:
            continue
        w1, w2 = px[i] - sx, py[i] - sy
        tt = (w1 * e2 - w2 * e1) / den
        uu = (w1 * dy - w2 * dx) / den
        okE = (uu >= 0 and uu <= 1) if n == 2 else (uu >= 0 and uu < 1)
        if okE and tt >= 0 and tt <= 1:
            t.append(tt)
    t.sort()
    return t


def _intervals_list(obs, Sxy, Rxy):
    Sa, Ra = _vec(Sxy), _vec(Rxy)
    sx, sy, rx, ry = Sa[0], Sa[1], Ra[0], Ra[1]
    rows = []
    for k, o in enumerate(obs):
        px, py = _vec(o["x"]), _vec(o["y"])
        top = float(mrt.asarr(o["top"]).flat[0])
        t = _crossings(px, py, sx, sy, rx, ry)
        if len(px) == 2:
            for tj in t:
                rows.append((tj, tj, top, k + 1.0))
            continue
        pxa, pya = np.array(px), np.array(py)
        if mrt.b_inpolygon(sx, sy, pxa, pya):
            t = [0.0] + t
        if mrt.b_inpolygon(rx, ry, pxa, pya):
            t = t + [1.0]
        for j in range(0, 2 * (len(t) // 2), 2):
            rows.append((t[j], t[j + 1], top, k + 1.0))
    return rows


def _intervals(obs, Sxy, Rxy):
    rows = _intervals_list(obs, Sxy, Rxy)
    return np.array(rows, dtype=float).reshape(-1, 4) if rows else np.zeros((0, 4))


def _interp(xl, zl, q):
    n = len(xl)
    if q == xl[-1]:
        return zl[-1]
    k = min(max(bisect_right(xl, q) - 1, 0), n - 2)
    x0, x1, y0, y1 = xl[k], xl[k + 1], zl[k], zl[k + 1]
    return y0 + (q - x0) * (y1 - y0) / (x1 - x0)


def _profile(dem, obs, Sxy, Rxy):
    s, z, ok = nb_profile_dem(dem, Sxy, Rxy, nargout=3)
    edgePts = np.zeros((0, 2))
    if not mrt.truth(ok) or len(obs) == 0:
        return s, z, ok, edgePts
    sl = _vec(s)
    zl = _vec(z)
    L = sl[-1]
    iv = _intervals_list(obs, Sxy, Rxy)
    if not iv:
        return s, z, ok, edgePts
    eps = 1e-6

    def gq(q):
        return _interp(sl, zl, min(max(q, 0.0), L))

    ps, pz = list(sl), list(zl)
    edge = []
    for (t_in, t_out, T, _k) in iv:
        s_in, s_out = t_in * L, t_out * L
        if s_in == s_out:
            g0 = gq(s_in)
            pts = [(s_in - eps, gq(s_in - eps)), (s_in, T if g0 != g0 else max(T, g0)), (s_in + eps, gq(s_in + eps))]
            top = [pts[1]]
            lo, hi = s_in - eps, s_in + eps
        else:
            g1, g2 = gq(s_in), gq(s_out)
            pts = [(s_in - eps, gq(s_in - eps)), (s_in, T if g1 != g1 else max(T, g1)),
                   (s_out, T if g2 != g2 else max(T, g2)), (s_out + eps, gq(s_out + eps))]
            top = pts[1:3]
            lo, hi = s_in - eps, s_out + eps
        top = [p for p in top if p[0] > 0 and p[0] < L]
        pts = [p for p in pts if p[0] > 0 and p[0] < L]
        keepi = [i for i in range(len(ps)) if (not (ps[i] > lo and ps[i] < hi)) or ps[i] == 0 or ps[i] == L]
        ps = [ps[i] for i in keepi] + [p[0] for p in pts]
        pz = [pz[i] for i in keepi] + [p[1] for p in pts]
        edge.extend(top)
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    ps = [ps[i] for i in order]
    pz = [pz[i] for i in order]
    good = [True] * len(ps)
    for i in range(1, len(ps)):
        if ps[i] - ps[i - 1] <= 0:
            if pz[i] >= pz[i - 1]:
                good[i - 1] = False
            else:
                good[i] = False
    s2 = np.array([ps[i] for i in range(len(ps)) if good[i]]).reshape(1, -1)
    z2 = np.array([pz[i] for i in range(len(ps)) if good[i]]).reshape(1, -1)
    edgePts = np.array(edge).reshape(-1, 2) if edge else np.zeros((0, 2))
    return s2, z2, ok, edgePts
