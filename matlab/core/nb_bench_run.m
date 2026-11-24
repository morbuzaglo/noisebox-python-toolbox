function r = nb_bench_run(id, modeOverride)
%NB_BENCH_RUN Execute one ISO/TR 17534-3 test case with the production code.
%   r = NB_BENCH_RUN('T08'). The case is solved through the SAME functions the
%   application uses (nb_receiver_3d -> run_acoustic_case, or run_acoustic_case
%   directly where the geometry is tabulated), in the labelled 'iso1996'
%   compatibility mode, and compared with the transcribed reference values
%   (see nb_bench_cases for the source of each number).
%   Returns vectors, one entry per compared quantity:
%     qname   cellstr  'L', 'LA', 'Abar', 'L total', 'LA total', 'Gs', ...
%     band    Hz (0 for totals)
%     expected, actual, err = actual - expected, tol, pass (logical)
%   plus r.status 'PASS' | 'FAIL' | 'BLOCKED', r.geometry diagnostics.
c = nb_bench_cases(id);
if nargin > 1 && ~isempty(modeOverride), c.mode = modeOverride; end   % compare the same scene in another mode (informative only)
b = nb_bands();
r.id = id;  r.title = c.title;  r.group = c.group;  r.ref = c.ref;  r.notes = c.notes;
r.mode = c.mode;  r.blockedReason = c.blocked;  r.tol = c.tol;
r.qname = {};  r.band = [];  r.expected = [];  r.actual = [];  r.err = [];  r.pass = false(0,1);  r.tols = [];
add = @(nm, bd, e, a, t) deal(1);  %#ok<NASGU>
e = c.expected;
expRows = {'L', b.f, e.L; 'L total', 0, e.Ltot; 'LA', b.f, e.LA; 'LA total', 0, e.LAtot};
if ~isempty(e.Abar), expRows(end+1,:) = {'Abar', b.f, e.Abar}; end
if strcmp(c.status, 'blocked')
    for i = 1:size(expRows,1)
        for k = 1:numel(expRows{i,3})
            r.qname{end+1} = expRows{i,1};  r.band(end+1) = expRows{i,2}(min(k, numel(expRows{i,2})));  %#ok<AGROW>
            r.expected(end+1) = expRows{i,3}(k);  r.actual(end+1) = NaN;  r.err(end+1) = NaN;  r.tols(end+1) = c.tol;  r.pass(end+1,1) = false;
        end
    end
    r.status = 'BLOCKED';  r.geometry = struct();
    return
end

base = struct('Lw', c.Lw, 'atm', c.atm, 'mode', c.mode, 'G', struct('Gs', c.G, 'Gm', c.G, 'Gr', c.G), ...
    'skipFingerprint', true, 'groundMethod', c.groundMethod);
if ~isempty(c.areas)
    base.groundAreas = c.areas;  base.Gdefault = c.G0;
    base.G = struct('Gs', c.G0, 'Gm', c.G0, 'Gr', c.G0);
end
Sxy = c.S(1:2);  Rxy = c.R(1:2);
geometry = struct();
if strcmp(c.type, 'dem')
    nx = 40;  ny = 60;
    dem = struct('x0', -60, 'y0', -260, 'cs', 10, 'Z', zeros(ny, nx));      % flat ground at 0 m, covers every case
    res = nb_receiver_3d(dem, c.obstacles, Sxy, c.S(3), Rxy, c.R(3), base);
    if ~res.valid, error('nb:bench:invalid', '%s: %s', id, res.reason); end
    out = res.out;  geometry = res.geom;
else
    d = c.direct;
    cc = base;  cc.hs = d.hs;  cc.hr = d.hr;  cc.dp = d.dp;  cc.dh = d.dh;
    if isfield(d, 'hm'), cc.hm = d.hm; end
    gf = nb_ground_factors(c.areas, c.G0, Sxy, Rxy, d.hs, d.hr);
    cc.G = struct('Gs', gf.Gs, 'Gm', gf.Gm, 'Gr', gf.Gr);
    out = run_acoustic_case(cc);
    geometry = struct('groundFactors', gf);
end
Lp = out.Lp;  LA = out.LpA_bands;
act = {'L', b.f, Lp; 'L total', 0, nb_energy_sum(Lp); 'LA', b.f, LA; 'LA total', 0, nb_energy_sum(LA)};
if ~isempty(e.Abar), act(end+1,:) = {'Abar', b.f, out.Abar}; end
for i = 1:size(expRows,1)
    for k = 1:numel(expRows{i,3})
        r.qname{end+1} = expRows{i,1};  r.band(end+1) = expRows{i,2}(min(k, numel(expRows{i,2}))); %#ok<AGROW>
        r.expected(end+1) = expRows{i,3}(k);  r.actual(end+1) = act{i,3}(k);
        r.err(end+1) = act{i,3}(k) - expRows{i,3}(k);  r.tols(end+1) = c.tol;
        r.pass(end+1,1) = abs(r.err(end)) <= c.tol + 1e-9;
    end
end
% ground-factor cross-check where the table's values are legible
if isfield(c, 'groundCheck') && isfield(geometry, 'groundFactors')
    gf = geometry.groundFactors;
    for nm = {'Gs', 'Gm', 'Gr'}
        k = nm{1};
        r.qname{end+1} = k;  r.band(end+1) = 0;  r.expected(end+1) = c.groundCheck.(k);  r.actual(end+1) = gf.(k);
        r.err(end+1) = gf.(k) - c.groundCheck.(k);  r.tols(end+1) = 0.005;  r.pass(end+1,1) = abs(r.err(end)) <= 0.005 + 1e-9;
    end
end
r.geometry = geometry;
r.atmosphereMethod = 'ISO 9613-2:1996 Table 2 (rounded alpha at nominal frequencies)';
r.groundMethod = out.groundMethod;
if all(r.pass), r.status = 'PASS'; else, r.status = 'FAIL'; end
r.nPass = sum(r.pass);  r.nTotal = numel(r.pass);  r.maxAbsErr = max(abs(r.err));
end
