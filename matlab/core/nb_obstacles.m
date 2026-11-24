function varargout = nb_obstacles(action, varargin)
%NB_OBSTACLES Obstacle footprints (walls and buildings) for 3D screening.
%   Obstacles are a cell array of structs:
%     o.x, o.y   plan vertices, metres. Two vertices = THIN WALL (a single
%                centre line, treated as one diffracting edge, e = 0).
%                Three or more = building footprint polygon.
%     o.top      ABSOLUTE elevation of the (flat) top edge, m
%   Actions:
%     iv = nb_obstacles('intervals', obs, Sxy, Rxy)
%          rows [t_in t_out top index] where the plan line S->R (t in 0..1)
%          is inside obstacle k; thin walls give t_in == t_out.
%     [s,z,ok,edgePts] = nb_obstacles('profile', dem, obs, Sxy, Rxy)
%          vertical-plane profile: DEM samples with the obstacle tops
%          inserted as steps; edgePts are the obstacle top edge points
%          [s z] (used to tell obstacle edges from terrain crests).
%   An obstacle never has its vertical walls "invented": heights come
%   only from o.top.
switch action
    case 'resolve',   varargout{1} = resolve(varargin{:});
    case 'intervals', varargout{1} = intervals(varargin{:});
    case 'profile',   [varargout{1:4}] = profile(varargin{:});
    otherwise, error('nb:obstacles:action', 'unknown action');
end
end

function obs = resolve(dem, obs)
% Give every obstacle an ABSOLUTE top elevation. If o.top is missing,
% o.h (height above ground) is added to the highest DEM elevation under
% the obstacle's vertices (a flat top cannot be lower than its tallest
% ground point). Vertices over no-data cells make the obstacle invalid.
for k = 1:numel(obs)
    o = obs{k};
    if numel(o.x) ~= numel(o.y) || numel(o.x) < 2 || any(~isfinite(o.x)) || any(~isfinite(o.y))
        error('nb:obstacles:shape', 'Obstacle %d: needs matching finite x/y with at least 2 vertices.', k);
    end
    if ~isfield(o, 'top') || isempty(o.top)
        if ~isfield(o, 'h') || isempty(o.h) || o.h <= 0
            error('nb:obstacles:height', 'Obstacle %d: give a positive height h or an absolute top.', k);
        end
        g = nb_dem_sample(dem, o.x(:), o.y(:));
        if any(isnan(g)), error('nb:obstacles:ground', 'Obstacle %d lies over no-data or outside the DEM.', k); end
        o.top = max(g) + o.h;
    end
    obs{k} = o;
end
end

function iv = intervals(obs, Sxy, Rxy)
iv = zeros(0,4);
for k = 1:numel(obs)
    o = obs{k};  px = o.x(:);  py = o.y(:);
    t = crossings(px, py, Sxy, Rxy);
    if numel(px) == 2
        for j = 1:numel(t), iv(end+1,:) = [t(j) t(j) o.top k]; end %#ok<AGROW>
        continue
    end
    if inpolygon(Sxy(1), Sxy(2), px, py), t = [0, t]; end
    if inpolygon(Rxy(1), Rxy(2), px, py), t = [t, 1]; end
    for j = 1:2:2*floor(numel(t)/2)
        iv(end+1,:) = [t(j) t(j+1) o.top k]; %#ok<AGROW>
    end
end
end

function t = crossings(px, py, Sxy, Rxy)
d = Rxy - Sxy;  n = numel(px);  t = [];
nEdges = n;  if n == 2, nEdges = 1; end
for i = 1:nEdges
    j = mod(i, n) + 1;
    p = [px(i) py(i)];  e = [px(j) py(j)] - p;
    den = d(1)*e(2) - d(2)*e(1);
    if abs(den) < 1e-12, continue; end
    w = p - Sxy;
    tt = (w(1)*e(2) - w(2)*e(1)) / den;
    uu = (w(1)*d(2) - w(2)*d(1)) / den;
    if n == 2, okEdge = uu >= 0 && uu <= 1; else, okEdge = uu >= 0 && uu < 1; end
    if okEdge && tt >= 0 && tt <= 1, t(end+1) = tt; end %#ok<AGROW>
end
t = sort(t);
end

function [s, z, ok, edgePts] = profile(dem, obs, Sxy, Rxy)
[s, z, ok] = nb_profile_dem(dem, Sxy, Rxy);
edgePts = zeros(0,2);
if ~ok || isempty(obs), return; end
L = s(end);
iv = intervals(obs, Sxy, Rxy);
if isempty(iv), return; end
eps_ = 1e-6;
ps = s;  pz = z;
for r = 1:size(iv,1)
    s_in = iv(r,1)*L;  s_out = iv(r,2)*L;  T = iv(r,3);
    g = @(q) interp1(s, z, min(max(q, 0), L));
    if s_in == s_out
        pts = [s_in - eps_, g(s_in - eps_); s_in, max(T, g(s_in)); s_in + eps_, g(s_in + eps_)];
        top = pts(2,:);
        lo = s_in - eps_;  hi = s_in + eps_;
    else
        pts = [s_in - eps_, g(s_in - eps_); s_in, max(T, g(s_in)); s_out, max(T, g(s_out)); s_out + eps_, g(s_out + eps_)];
        top = pts(2:3,:);
        lo = s_in - eps_;  hi = s_out + eps_;
    end
    top = top(top(:,1) > 0 & top(:,1) < L, :);
    pts = pts(pts(:,1) > 0 & pts(:,1) < L, :);          % never move the source / receiver samples
    keep = ~(ps > lo & ps < hi) | ps == 0 | ps == L;
    ps = [ps(keep), pts(:,1)'];  pz = [pz(keep), pts(:,2)'];
    edgePts = [edgePts; top]; %#ok<AGROW>
end
[ps, ord] = sort(ps);  pz = pz(ord);
% enforce strictly increasing s (keep the higher point at equal s)
good = true(size(ps));
for i = 2:numel(ps)
    if ps(i) - ps(i-1) <= 0
        if pz(i) >= pz(i-1), good(i-1) = false; else, good(i) = false; end
    end
end
s = ps(good);  z = pz(good);
end
