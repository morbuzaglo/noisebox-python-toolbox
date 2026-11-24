function out = run_case_3d(c)
%RUN_CASE_3D One receiver over a DEM with obstacles, with full path geometry.
%   out = RUN_CASE_3D(c): c as run_field_3d but
%     c.receiver  struct x, y, h (height above local ground)
%   out.out   the per-band chain result (all attenuation terms)
%   out.geom  top path (kind, z, dss, dsr, e), blockers, lateral paths with
%             their applicability flags and reasons
%   out.paths 3D polylines for display:
%               direct   [x y z; x y z]
%               top      [x y z; ...]  S -> top edges -> R
%               left, right  [x y z; ...] or empty
%   out.profile  [s z] vertical-plane profile used.
if ~isfield(c,'mode') || isempty(c.mode), c.mode = 'iso2024'; end
if ~isfield(c,'obstacles') || isempty(c.obstacles), obs = {}; else, obs = c.obstacles; end
if ~iscell(obs), obs = {obs}; end
obs = nb_obstacles('resolve', c.dem, obs);
Sxy = [c.source.x, c.source.y];  Rxy = [c.receiver.x, c.receiver.y];
base = rmfield(c, intersect(fieldnames(c), {'dem','source','receiver','obstacles','limits','hr','grid'}));
r = nb_receiver_3d(c.dem, obs, Sxy, c.source.h, Rxy, c.receiver.h, base);
out.valid = r.valid;  out.reason = r.reason;
if ~r.valid, return; end
out.out = r.out;  out.geom = r.geom;  out.profile = r.profile;
if isfield(c, 'limits') && ~isempty(c.limits)
    out.compliance = nb_compliance(r.out.Lp, r.out.LpA_bands, c.limits);
end
zS = nb_dem_sample(c.dem, Sxy(1), Sxy(2)) + c.source.h;
zR = nb_dem_sample(c.dem, Rxy(1), Rxy(2)) + c.receiver.h;
S = [Sxy zS];  R = [Rxy zR];
L = r.profile(end,1);
to3 = @(sz) [S(1) + (R(1)-S(1))*sz(:,1)/L, S(2) + (R(2)-S(2))*sz(:,1)/L, sz(:,2)];
out.paths.direct = [S; R];
out.paths.top = [S; R];
if ~isempty(r.geom.topPathSE), out.paths.top = to3(r.geom.topPathSE); end
lt = r.geom.lateral;
out.paths.left = zeros(0,3);  out.paths.right = zeros(0,3);
if isfield(lt.left, 'valid') && lt.left.valid,   out.paths.left  = [S; lt.left.edges;  R]; end
if isfield(lt.right, 'valid') && lt.right.valid, out.paths.right = [S; lt.right.edges; R]; end
end
