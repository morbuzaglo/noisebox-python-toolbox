function r = nb_receiver_3d(dem, obs, Sxy, hSrc, Rxy, hRec, base)
%NB_RECEIVER_3D One source-receiver pair over a DEM with obstacles.
%   r = NB_RECEIVER_3D(dem, obs, Sxy, hSrc, Rxy, hRec, base)
%     dem      DEM struct (nb_dem_sample); obs cell array (nb_obstacles), {} ok
%     hSrc,hRec heights above LOCAL ground, m
%     base     struct with Lw, G, atm, mode, (Dc, C0, enclosure): chain inputs
%   Obstacle fields: x, y, top (absolute) or h, optional
%     gap   bottom clearance of a hanging screen, m (default 0 = to the ground)
%     mat   material struct (nb_material) -> sound also TRANSMITS through it
%   Returns r.valid; if valid: r.out (run_acoustic_case result), r.geom,
%   r.profile, r.screens; r.reason when invalid.
%   Steps: (1) hanging screens whose bottom edge is above the line of sight
%   do not block it; (2) vertical-plane profile (DEM + obstacle tops) and
%   exact top path; (3) lateral paths only if an obstacle blocks the
%   line, no terrain edge is on the top path, factor-8 rule (7.4.3);
%   (4) per-band relevance: object width normal to S-R must exceed the
%   wavelength (7.4.1); (5) ENGINEERING EXTENSIONS, reported separately:
%   the path under a bottom gap and transmission through the fabric.
r.valid = false;  r.reason = '';  r.screens = struct('present', false);
zS = nb_dem_sample(dem, Sxy(1), Sxy(2));
zR = nb_dem_sample(dem, Rxy(1), Rxy(2));
if isnan(zS) || isnan(zR), r.reason = 'no-data or outside DEM'; return; end
for k = 1:numel(obs)
    o = obs{k};
    if numel(o.x) >= 3 && inpolygon(Rxy(1), Rxy(2), o.x, o.y)
        r.reason = 'receiver inside an obstacle footprint'; return;
    end
    if numel(o.x) >= 3 && inpolygon(Sxy(1), Sxy(2), o.x, o.y)
        r.reason = 'source inside an obstacle footprint'; return;
    end
end
Lplan = hypot(Rxy(1)-Sxy(1), Rxy(2)-Sxy(2));
if Lplan < 1e-6, r.reason = 'receiver at source'; return; end
Sz = zS + hSrc;  Rz = zR + hRec;
dtot = hypot(Lplan, Rz - Sz);

% ---- (1) hanging screens: does the line of sight pass under the bottom edge?
iv0 = nb_obstacles('intervals', obs, Sxy, Rxy);
keep = true(1, numel(obs));
underEdges = zeros(0, 2);
for q = 1:size(iv0, 1)
    k = iv0(q,4);  o = obs{k};
    gap = 0;  if isfield(o,'gap') && ~isempty(o.gap), gap = o.gap; end
    if gap <= 0, continue; end
    tc = mean(iv0(q,1:2));
    P = Sxy + tc*(Rxy - Sxy);  g = nb_dem_sample(dem, P(1), P(2));
    bottom = g + gap;  los = Sz + tc*(Rz - Sz);
    if los < bottom - 1e-9
        keep(k) = false;                               % LOS passes under the fabric
    elseif los < o.top
        underEdges(end+1,:) = [tc*Lplan, bottom];      %#ok<AGROW>
    end
end
obs = obs(keep);

[s, z, ok, edgePts] = nb_obstacles('profile', dem, obs, Sxy, Rxy);
if ~ok, r.reason = 'invalid terrain profile (no-data cell)'; return; end
L = s(end);
try
    g = nb_geom2d(s, z, [0, zS + hSrc], [L, zR + hRec]);
catch ME
    r.reason = ME.message; return;
end

% ---- which obstacles block the direct line of sight?
iv = nb_obstacles('intervals', obs, Sxy, Rxy);
blockIdx = [];  blockRows = [];
for q = 1:size(iv,1)
    los = @(t) Sz + t*(Rz - Sz);
    if min(los(iv(q,1)), los(iv(q,2))) < iv(q,3) - 1e-9
        blockIdx(end+1) = iv(q,4);  blockRows(end+1) = q; %#ok<AGROW>
    end
end
blockIdx = unique(blockIdx);

geom = struct('kind', g.kind, 'z', g.z, 'dss', g.dss, 'dsr', g.dsr, 'e', g.e, ...
    'topPathSE', g.path, 'blockers', blockIdx, 'lateral', struct());
barrier = [];
if ~isempty(g.z)
    barrier = struct('z', g.z, 'dss', g.dss, 'dsr', g.dsr, 'e', g.e);
end

% ---- lateral paths
% ISO 9613-2:2024 7.4.3 and ISO/TR 17534-3 cl. 5.2 state the factor-8 rule, but the TR's own reference
% results T08 and T09 include lateral edges beyond it, so the 1996 compatibility mode does not apply it.
applyF8 = ~(isfield(base, 'mode') && strcmp(base.mode, 'iso1996'));
latInfo = struct('considered', false, 'reason', 'no obstacle blocks the line of sight', ...
    'left', struct('valid', false), 'right', struct('valid', false));
terrainOnTop = false;
if ~isempty(blockIdx)
    latInfo.reason = '';
    if strcmp(g.kind, 'blocked') && ~isempty(g.edges)
        isObsEdge = false(size(g.edges,1),1);
        for i = 1:size(g.edges,1)
            isObsEdge(i) = any(abs(edgePts(:,1) - g.edges(i,1)) < 1e-9 & abs(edgePts(:,2) - g.edges(i,2)) < 1e-9);
        end
        terrainOnTop = any(~isObsEdge);
    end
    if terrainOnTop
        latInfo.reason = 'elevated ground contributes to the top path (7.4.3): lateral paths not considered';
    else
        lat = nb_lateral(obs, blockIdx, [Sxy Sz], [Rxy Rz], dem);
        vd = 0;
        if ~isempty(g.edges)
            dir = [L, Rz - Sz];
            for i = 1:size(g.edges,1)
                vd = max(vd, abs(dir(1)*(g.edges(i,2)-Sz) - dir(2)*g.edges(i,1)) / norm(dir));
            end
        end
        latInfo.considered = true;  latInfo.maxVerticalSupportDistance = vd;
        names = {'left', 'right'};
        for si = 1:2
            sd = lat.side(si);
            info = struct('valid', false, 'reason', 'no supporting vertical edge on this side');
            if sd.valid
                if applyF8 && vd > 0 && sd.maxv > 8*vd
                    info = struct('valid', false, 'reason', sprintf('neglected: lateral support %.2f m > 8 x vertical support %.2f m (7.4.3)', sd.maxv, vd), ...
                        'z', sd.z, 'maxv', sd.maxv);
                else
                    info = struct('valid', true, 'reason', '', 'z', sd.z, 'dss', sd.dss, 'dsr', sd.dsr, 'e', sd.e, ...
                        'edges', sd.edges, 'maxv', sd.maxv);
                end
            end
            latInfo.(names{si}) = info;
        end
    end
end
if ~isempty(barrier)
    if isfield(latInfo.left, 'valid') && latInfo.left.valid
        barrier.side1 = struct('z', latInfo.left.z, 'dss', latInfo.left.dss, 'dsr', latInfo.left.dsr, 'e', latInfo.left.e);
    end
    if isfield(latInfo.right, 'valid') && latInfo.right.valid
        barrier.side2 = struct('z', latInfo.right.z, 'dss', latInfo.right.dss, 'dsr', latInfo.right.dsr, 'e', latInfo.right.e);
    end
end
geom.lateral = latInfo;

% ---- (4) per-band relevance: width of the object normal to S-R must exceed lambda (7.4.1)
b = nb_bands();
if ~isempty(barrier) && ~isempty(blockIdx) && ~terrainOnTop
    pd = Rxy - Sxy;  n2 = [-pd(2), pd(1)] / norm(pd);
    mask = false(1,8);
    for k = blockIdx
        pv = (obs{k}.x(:) - Sxy(1))*n2(1) + (obs{k}.y(:) - Sxy(2))*n2(2);
        mask = mask | ((max(pv) - min(pv)) > 340 ./ b.f);
    end
    barrier.mask = mask;
    geom.objectWidthCriterion = mask;
end

% ---- (5a) path under a bottom gap (ENGINEERING EXTENSION, not in ISO 9613-2)
geom.under = struct('present', false);
if ~isempty(barrier) && ~isempty(underEdges) && ~terrainOnTop
    zu = -Inf;  best = 0;
    for q = 1:size(underEdges,1)
        zq = hypot(underEdges(q,1), underEdges(q,2) - Sz) + hypot(L - underEdges(q,1), underEdges(q,2) - Rz) - dtot;
        if zq > zu, zu = zq; best = q; end
    end
    du = nb_dz(max(zu, 0), hypot(underEdges(best,1), underEdges(best,2)-Sz), ...
        hypot(L-underEdges(best,1), underEdges(best,2)-Rz), dtot, 0, base.mode, true);
    barrier.extra = du.Dz;
    geom.under = struct('present', true, 'z', zu, 'edge', underEdges(best,:), ...
        'note', 'Path under the bottom clearance; an engineering extension, not prescribed by ISO 9613-2.');
end

% ---- ground factors from ground areas (G varies in plan; Formula 10)
cc = base;
if isfield(base, 'groundAreas') && ~isempty(base.groundAreas)
    areas = base.groundAreas;  if ~iscell(areas), areas = {areas}; end
    G0 = base.G.Gs;  if isfield(base, 'Gdefault') && ~isempty(base.Gdefault), G0 = base.Gdefault; end
    gf = nb_ground_factors(areas, G0, Sxy, Rxy, g.hs, g.hr);
    cc.G = struct('Gs', gf.Gs, 'Gm', gf.Gm, 'Gr', gf.Gr);
    geom.groundFactors = gf;
end

% ---- (5b) transmission through fabric crossed by the direct ray (ENGINEERING EXTENSION)
if ~isempty(blockRows) && ~terrainOnTop
    allMat = true;  TLsum = zeros(1,8);  infos = {};  warn = {};
    for q = blockRows
        o = obs{iv(q,4)};
        if ~isfield(o, 'mat') || isempty(o.mat), allMat = false; break; end
        m = nb_material('resolve', o.mat);
        TLsum = TLsum + m.TLeff;
        infos{end+1} = sprintf('obstacle %d: %s, surface mass %s', iv(q,4), m.source, mat2str(m.surface_mass)); %#ok<AGROW>
        warn = [warn, m.warnings]; %#ok<AGROW>
    end
    if allMat
        cc.screenTL = struct('TL', TLsum, 'info', struct('materials', {infos}, 'warnings', {unique(warn)}));
        r.screens = struct('present', true, 'TL', TLsum, 'warnings', {unique(warn)});
    end
end

cc.hs = g.hs;  cc.hr = g.hr;  cc.dp = g.dp;  cc.dh = g.dh;
cc.barrier = barrier;
r.out = run_acoustic_case(cc);
r.geom = geom;
r.profile = [s(:), z(:)];
r.valid = true;
end
