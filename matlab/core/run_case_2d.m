function out = run_case_2d(c)
%RUN_CASE_2D Prediction in a vertical X-Z cross-section with a real terrain profile.
%   out = RUN_CASE_2D(c). Fields of c as in run_acoustic_case, except the
%   geometry (dp, hs, hr, dh, barrier) is DERIVED from:
%     c.terrain.x, c.terrain.z   profile vertices, m (z absolute)
%     c.source.x,  c.source.h    source x and height above local ground, m
%     c.receiver.x, c.receiver.h receiver x and height above local ground, m
%   Source must lie left of the receiver (mirror the profile otherwise).
%   The geometry (kind, edges, z, dss, dsr, e, path) is returned in
%   out.geom so the UI can draw the actual path.
%   Terrain-profile ground attenuation uses hs, hr above LOCAL ground and
%   dp = horizontal distance, as the general method requires (cl. 7.3.1).
xp = c.terrain.x(:)';  zp = c.terrain.z(:)';
gs = interp1(xp, zp, c.source.x);
gr = interp1(xp, zp, c.receiver.x);
S = [c.source.x,   gs + c.source.h];
R = [c.receiver.x, gr + c.receiver.h];
g = nb_geom2d(xp, zp, S, R);

c2 = rmfield(c, {'terrain','source','receiver'});
c2.hs = g.hs;  c2.hr = g.hr;  c2.dp = g.dp;  c2.dh = g.dh;
c2.barrier = [];
if ~isempty(g.z)
    c2.barrier = struct('z', g.z, 'dss', g.dss, 'dsr', g.dsr, 'e', g.e);
end
out = run_acoustic_case(c2);
out.geom = g;
end
