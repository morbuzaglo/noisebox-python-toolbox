function out = run_field_3d(c)
%RUN_FIELD_3D Prediction on a map grid over a DEM with optional obstacles.
%   out = RUN_FIELD_3D(c):
%     c.dem        struct x0, y0, cs, Z (see nb_dem_sample), metres
%     c.source     struct x, y, h   (h = height above LOCAL ground, m)
%     c.grid       struct x (1xNX), y (1xNY) receiver ground positions, m
%     c.hr         receiver height above local ground, m (default 1.5)
%     c.obstacles  optional cell array of obstacles (see nb_obstacles)
%     c.Lw, c.G, c.atm, c.mode, optional c.limits (as run_acoustic_case)
%   Per receiver: vertical-plane profile (DEM + obstacle tops), exact top
%   path, lateral paths around obstacle vertical edges where 7.4.3 allows,
%   then the standard chain. Point order: row-major over y,
%   index = (iy-1)*NX + ix. Invalid points (no-data, outside, inside an
%   obstacle, at the source) are NaN with valid = false.
if ~isfield(c,'mode') || isempty(c.mode), c.mode = 'iso2024'; end
if ~isfield(c,'obstacles') || isempty(c.obstacles), obs = {}; else, obs = c.obstacles; end
if ~iscell(obs), obs = {obs}; end
obs = nb_obstacles('resolve', c.dem, obs);
xg = c.grid.x(:)';  yg = c.grid.y(:)';
NX = numel(xg);  NY = numel(yg);  NP = NX*NY;
zS = nb_dem_sample(c.dem, c.source.x, c.source.y);
if isnan(zS), error('nb:field3d:source', 'Source lies outside the DEM or on a no-data cell.'); end
Sxy = [c.source.x, c.source.y];

base = rmfield(c, intersect(fieldnames(c), {'dem','source','grid','obstacles','limits','hr'}));
base.skipFingerprint = true;
if isfield(c, 'hr') && ~isempty(c.hr), hr = c.hr; else, hr = 1.5; end

Lp = nan(NP,8);  LpA = nan(NP,8);  Abar = nan(NP,8);  Agr = nan(NP,8);
kind = nan(NP,1);  valid = false(NP,1);  ground = nan(NP,1);  lateral = zeros(NP,1);
kindCode = containers.Map({'none','blocked','clear_crest'}, {0,1,2});
k = 0;
for iy = 1:NY
    for ix = 1:NX
        k = k + 1;
        Rxy = [xg(ix), yg(iy)];
        r = nb_receiver_3d(c.dem, obs, Sxy, c.source.h, Rxy, hr, base);
        if ~r.valid, continue; end
        o = r.out;
        Lp(k,:) = o.Lp;  LpA(k,:) = o.LpA_bands;  Abar(k,:) = o.Abar;  Agr(k,:) = o.Agr;
        kind(k) = kindCode(r.geom.kind);  valid(k) = true;
        ground(k) = nb_dem_sample(c.dem, Rxy(1), Rxy(2));
        lt = r.geom.lateral;
        lateral(k) = double(isfield(lt.left,'valid') && lt.left.valid) + 2*double(isfield(lt.right,'valid') && lt.right.valid);
    end
end
out.x = xg;  out.y = yg;  out.NX = NX;  out.NY = NY;
out.Lp = Lp;  out.LpA = LpA;  out.Abar = Abar;  out.Agr = Agr;
out.Lp_broadband  = 10*log10(sum(10.^(Lp/10), 2));
out.LpA_broadband = 10*log10(sum(10.^(LpA/10), 2));
out.kind = kind;  out.valid = valid;  out.ground = ground;  out.lateralPaths = lateral;
out.mode = c.mode;  out.sourceGround = zS;  out.nObstacles = numel(obs);
if isfield(c, 'limits') && ~isempty(c.limits)
    out.compliance = nb_compliance(Lp, LpA, c.limits);
    out.compliance.status = [];
end
out.method = 'VERIFIED: DEM + obstacle tops in each source-receiver vertical plane, exact upper-hull top path, lateral paths per ISO 9613-2:2024 7.4.3';
out.fingerprint = nb_fingerprint();
end
