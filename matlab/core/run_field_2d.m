function out = run_field_2d(c)
%RUN_FIELD_2D Prediction on an X-Z grid of receivers in a vertical plane.
%   out = RUN_FIELD_2D(c). c has the fields of run_case_2d (terrain,
%   source.x, source.h, Lw, G, atm, mode, optional limits) plus
%     c.grid.x  1xNX receiver x positions, m
%     c.grid.z  1xNZ receiver ABSOLUTE elevations, m
%   Points inside the ground (z < terrain) or at the source x are masked
%   (NaN, out.valid = false). Receivers LEFT of the source are handled by
%   mirroring the profile so the source is always on the left.
%   Point order is row-major over z: index = (iz-1)*NX + ix.
%   Outputs (NP = NX*NZ): Lp NPx8, LpA NPx8, Lp_broadband NPx1,
%   LpA_broadband NPx1, Abar NPx8, Agr NPx8, kind NPx1 (0 none, 1 blocked,
%   2 clear_crest), valid NPx1, compliance (if limits given).
if ~isfield(c,'mode') || isempty(c.mode), c.mode = 'iso2024'; end
xg = c.grid.x(:)';  zg = c.grid.z(:)';
NX = numel(xg);  NZ = numel(zg);  NP = NX*NZ;
xp = c.terrain.x(:)';  zp = c.terrain.z(:)';
xs = c.source.x;  gs = interp1(xp, zp, xs);
S  = [xs, gs + c.source.h];

base = rmfield(c, {'terrain','source','grid'});
base.skipFingerprint = true;
if isfield(base, 'limits'), base = rmfield(base, 'limits'); end

Lp = nan(NP,8);  LpA = nan(NP,8);  Abar = nan(NP,8);  Agr = nan(NP,8);
kind = nan(NP,1);  valid = false(NP,1);
kindCode = containers.Map({'none','blocked','clear_crest'}, {0,1,2});
tol = 1e-9;
k = 0;
for iz = 1:NZ
    for ix = 1:NX
        k = k + 1;
        xr = xg(ix);  zr = zg(iz);
        if xr < xp(1) || xr > xp(end), continue; end
        if abs(xr - xs) < 1e-6, continue; end
        gr = interp1(xp, zp, xr);
        if zr < gr - tol, continue; end                  % inside the ground
        if xr > xs
            gx = xp;  gz = zp;  Sx = S;  Rx = [xr, zr];
        else                                             % mirror so S stays on the left
            gx = -fliplr(xp);  gz = fliplr(zp);  Sx = [-S(1), S(2)];  Rx = [-xr, zr];
        end
        try
            g = nb_geom2d(gx, gz, Sx, Rx);
        catch
            continue;                                    % degenerate geometry: leave as NaN (no data)
        end
        cc = base;
        cc.hs = g.hs;  cc.hr = g.hr;  cc.dp = g.dp;  cc.dh = g.dh;
        cc.barrier = [];
        if ~isempty(g.z), cc.barrier = struct('z', g.z, 'dss', g.dss, 'dsr', g.dsr, 'e', g.e); end
        o = run_acoustic_case(cc);
        Lp(k,:) = o.Lp;  LpA(k,:) = o.LpA_bands;  Abar(k,:) = o.Abar;  Agr(k,:) = o.Agr;
        kind(k) = kindCode(g.kind);  valid(k) = true;
    end
end
out.x = xg;  out.z = zg;  out.NX = NX;  out.NZ = NZ;
out.Lp = Lp;  out.LpA = LpA;  out.Abar = Abar;  out.Agr = Agr;
out.Lp_broadband  = 10*log10(sum(10.^(Lp/10), 2));
out.LpA_broadband = 10*log10(sum(10.^(LpA/10), 2));
out.kind = kind;  out.valid = valid;  out.mode = c.mode;
if isfield(c, 'limits') && ~isempty(c.limits)
    lim = c.limits;
    out.compliance = nb_compliance(Lp, LpA, lim);
    out.compliance.status = [];                          % keep payload small; code carries it
end
out.fingerprint = nb_fingerprint();
end
