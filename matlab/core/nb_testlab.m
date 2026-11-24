function out = nb_testlab(action, id)
%NB_TESTLAB Test registry executed with the production MATLAB code.
%   cat = NB_TESTLAB('catalog')  struct of cell arrays: id, group, title, source, calls, status0
%   r   = NB_TESTLAB('run', id)  struct: labels (cellstr), expected, actual, err, tol, pass,
%                                status 'PASS'|'FAIL'|'SKIP'|'BLOCKED'|'EXTERNAL', detail, source
%   Rules (brief, "Testing"): every expected value is documented by its source (formula and
%   page, table, or hand derivation) and is NEVER computed by the function under test; each test
%   lists the production functions it calls (r.calls). A test that does not call the intended
%   function must not claim to validate it.
%   Groups: G1 analytic | G2 independent numerical reference (ISO 9613-1 Table 1) |
%           G3 ISO/TR 17534-3:2015 benchmarks (ISO 9613-2:1996 compatibility mode) |
%           G4 ISO 9613-2:2024 validation | G5 DAmd 1 DRAFT regression | G6 integration (pytest).
T = registry();
switch action
    case 'catalog'
        out.id = cellfun(@(t) t.id, T, 'UniformOutput', false);
        out.group = cellfun(@(t) t.group, T, 'UniformOutput', false);
        out.title = cellfun(@(t) t.title, T, 'UniformOutput', false);
        out.source = cellfun(@(t) t.source, T, 'UniformOutput', false);
        out.calls = cellfun(@(t) t.calls, T, 'UniformOutput', false);
        out.status0 = cellfun(@(t) t.status0, T, 'UniformOutput', false);
    case 'run'
        k = find(strcmp(cellfun(@(t) t.id, T, 'UniformOutput', false), id), 1);
        if isempty(k), error('nb:testlab:id', 'Unknown test %s', id); end
        t = T{k};
        out = struct('id', t.id, 'group', t.group, 'title', t.title, 'source', t.source, 'calls', {t.calls});
        if ~isempty(t.fn)
            try
                r = t.fn();
            catch ME
                r = struct('labels', {{'error'}}, 'expected', NaN, 'actual', NaN, 'tol', 0, 'detail', ME.message);
                r.status = 'FAIL';  r.forceFail = true;
            end
        else
            r = struct('labels', {{}}, 'expected', [], 'actual', [], 'tol', [], 'detail', t.detail);
            r.status = t.status0;
        end
        out = mergeStruct(out, r);
        n = numel(out.expected);
        out.err = out.actual - out.expected;
        if numel(out.tol) == 1, out.tol = out.tol * ones(1, n); end
        if isfield(out, 'status') && ~isempty(out.status)
            % explicit (SKIP / BLOCKED / EXTERNAL / failed with error)
            out.pass = false(1, n);
        else
            out.pass = abs(out.err) <= out.tol + 1e-12;
            out.pass(isnan(out.expected) & isnan(out.actual)) = true;
            if all(out.pass), out.status = 'PASS'; else, out.status = 'FAIL'; end
        end
        if ~isfield(out, 'detail'), out.detail = ''; end
    otherwise
        error('nb:testlab:action', 'unknown action');
end
end

function a = mergeStruct(a, b)
f = fieldnames(b);
for i = 1:numel(f), a.(f{i}) = b.(f{i}); end
end

function t = mk(id, group, title, source, calls, fn)
t = struct('id', id, 'group', group, 'title', title, 'source', source, 'calls', {calls}, 'fn', fn, 'status0', '', 'detail', '');
end

function t = ext(id, group, title, source, detail, status)
t = struct('id', id, 'group', group, 'title', title, 'source', source, 'calls', {{}}, 'fn', [], 'status0', status, 'detail', detail);
end

function r = row(labels, expected, actual, tol, detail)
if nargin < 5, detail = ''; end
r = struct('labels', {labels}, 'expected', expected(:)', 'actual', actual(:)', 'tol', tol, 'detail', detail);
end

function T = registry()
G1 = 'G1 Analytic';
G2 = 'G2 Independent numerical reference';
G3 = 'G3 ISO/TR 17534-3:2015 (ISO 9613-2:1996 compatibility mode)';
G4 = 'G4 ISO 9613-2:2024 validation';
G5 = 'G5 DAmd 1 DRAFT-AMENDMENT regression';
G6 = 'G6 Integration and UI';
T = {};
f = nb_bands();

% ------------------------------------------------------------------------ G1 analytic
T{end+1} = mk('G1-adiv', G1, 'A_div at 100 m = 51 dB', 'ISO 9613-2:2024 Formula (8), printed p. 8: 20 lg(100/1) + 11', {'nb_adiv'}, ...
    @() row({'A_div(100 m)'}, 51, nb_adiv(100), 1e-9));
T{end+1} = mk('G1-energysum', G1, 'Energy sum of 50 dB and 60 dB (not the arithmetic mean)', 'hand: 10 lg(10^5 + 10^6) = 60.4139', {'nb_energy_sum'}, ...
    @() row({'L sum'}, 60.41392685, nb_energy_sum([50 60]), 1e-7));
T{end+1} = mk('G1-centres', G1, 'Exact base-10 octave centre frequencies', 'ISO 9613-2:2024 cl. 7.2 (printed p. 9): f = 1000 * 10^(0.3 n); values by hand', {'nb_bands'}, ...
    @() row(arrayfun(@(x) sprintf('%d Hz', x), f.f, 'UniformOutput', false), [63.0957 125.8925 251.1886 501.1872 1000 1995.2623 3981.0717 7943.2823], f.fexact, 1e-3));
T{end+1} = mk('G1-agr-hard', G1, 'A_gr far-field limit over hard ground = -6 dB, never clamped to 0', 'Table 3 with G = 0: A_s = A_r = -1.5, A_m = -3q, q -> 1, K_geo -> 1 (printed p. 10-11)', {'nb_agr'}, ...
    @() row({'A_gr 63..8000 Hz, dp = 1e7 m'}, -6*ones(1,8), nb_agr(0,0,0,1,1,1e7).Agr, 1e-3));
T{end+1} = mk('G1-agr-porous', G1, 'A_gr = 0 at 2-8 kHz over fully porous ground (G = 1)', 'Table 3: -1.5(1 - G) = 0 for A_s, A_r and A_m (printed p. 11)', {'nb_agr'}, ...
    @() row({'2000','4000','8000'}, [0 0 0], nb_agr(1,1,1,2,1.5,200).Agr(6:8), 1e-12));
T{end+1} = mk('G1-kgeo', G1, 'K_geo for dp = 200 m, hs = 2 m, hr = 1.5 m', 'Formula (13), printed p. 10: (dp^2+(hs-hr)^2)/(dp^2+(hs+hr)^2) = 40000.25/40012.25', {'nb_agr'}, ...
    @() row({'K_geo'}, 40000.25/40012.25, nb_agr(1,0.5,1,2,1.5,200).Kgeo, 1e-12));
T{end+1} = mk('G1-dz-hand', G1, 'D_z, single edge, z = 0.5 m, 1 kHz, K_met = 1', 'Formulae (18)-(20), printed p. 16: 10 lg[1 + (2 + (20/0.34)*0.5)] = 10 lg 32.4118', {'nb_dz'}, ...
    @() row({'D_z 1000 Hz'}, 10*log10(32.411764706), nb_dz(0.5,1e-9,1e-9,1e-9,0,'iso2024',false).Dz(5), 1e-6));
T{end+1} = mk('G1-dz-caps', G1, 'D_z capped at 20 dB (single) and 25 dB (multiple diffraction)', 'ISO 9613-2:2024 cl. 7.4.4, printed p. 20 (top path only)', {'nb_dz'}, ...
    @() row({'single','multiple'}, [20 25], [max(nb_dz(1e4,1,1,1,0,'iso2024',false).Dz) max(nb_dz(1e4,1,1,1,5,'iso2024',false).Dz)], 1e-12));
T{end+1} = mk('G1-dz-continuous', G1, 'D_z is 0 dB, real and continuous at z_min (published form)', 'Formula (19): z_min = -2 lambda/(C2 C3); bracket of (18) = 1 at z_min', {'nb_dz'}, ...
    @() row({'D_z(z_min + 1e-9), 1 kHz'}, 0, nb_dz(-2*0.34/20+1e-9,100,120,200,0,'iso2024',false).Dz(5), 1e-6));
T{end+1} = mk('G1-abar-two', G1, 'Two equal 10 dB paths combine to 6.99 dB', 'Formula (25), printed p. 20: -10 lg(2 * 10^-1)', {'nb_abar'}, ...
    @() row({'A_bar'}, 10 - 10*log10(2), nb_abar(10*ones(1,8), 10*ones(1,8), [], zeros(1,8)).Abar(1), 1e-9));
T{end+1} = mk('G1-abar-agr', G1, 'A_bar = D_z - A_gr only when A_gr > 0 (top path)', 'Formulae (16), (17), printed p. 14', {'nb_abar'}, ...
    @() row({'A_gr=+3','A_gr=-2','A_gr=0'}, [7 10 10], [nb_abar(10*ones(1,8),[],[],3*ones(1,8)).Abar(1) nb_abar(10*ones(1,8),[],[],-2*ones(1,8)).Abar(1) nb_abar(10*ones(1,8),[],[],zeros(1,8)).Abar(1)], 1e-9));
T{end+1} = mk('G1-cmet', G1, 'C_met per Formulae (31), (32)', 'ISO 9613-2:2024 cl. 8, printed p. 24', {'nb_cmet'}, ...
    @() row({'dp <= 10(hs+hr)','dp = 40'}, [0 2*(1-20/40)], [nb_cmet(2,1,1,20) nb_cmet(2,1,1,40)], 1e-12));
T{end+1} = mk('G1-massLaw', G1, 'Mass law, 10 kg/m^2 at 1 kHz', 'TL = 20 lg(pi f m /(rho0 c)), rho0 c = 415 Pa s/m: 80 - 20 lg(415/pi)', {'nb_material'}, ...
    @() row({'TL'}, 80 - 20*log10(415/pi), nb_material('massLaw', 10, 1000, 'normal'), 1e-9));
T{end+1} = mk('G1-massLaw-slope', G1, 'Mass-law slope is 6.02 dB per doubling of frequency', 'hand: 20 lg 2', {'nb_material'}, ...
    @() row({'TL(2f)-TL(f)'}, 20*log10(2), diff(nb_material('massLaw', 5, [1000 2000], 'normal')), 1e-9));
T{end+1} = mk('G1-effTL', G1, 'Effective TL with 50 % open area, TL = 30 dB', 'hand: -10 lg(0.5 + 0.5 * 10^-3) = 3.0058', {'nb_material'}, ...
    @() row({'TL_eff'}, -10*log10(0.5005), nb_material('effectiveTL', 30, 0.5), 1e-9));
T{end+1} = mk('G1-enclosure', G1, 'Enclosure: L_W,out = L_W,in + 10 lg(4/A) - TL + 10 lg S - 6', 'hand arithmetic for S = 6 m2, A = 8 m2, TL = 20 dB, L_W,in = 100 dB (diffuse-field model, rough estimate)', {'nb_enclosure'}, ...
    @() row({'L_W,out'}, 100 + 10*log10(4/8) - 20 + 10*log10(6) - 6, nb_enclosure(100*ones(1,8), struct('S_total',6,'A_in',8,'mat',struct('TL',20*ones(1,8)))).Lw_out(1), 1e-9));
T{end+1} = mk('G1-background', G1, 'Background subtraction in the energy domain', 'hand: 10 lg(10^6 - 10^5) = 59.5424 dB', {'nb_background_subtract'}, ...
    @() row({'L corrected'}, 10*log10(1e6-1e5), nb_background_subtract(60*ones(1,8), 50*ones(1,8)).Lcorr(1), 1e-9));
T{end+1} = mk('G1-geom-ridge', G1, 'Taut-string path over a ridge, path length difference z', 'hand Pythagoras: S=(0,2), crest (100,10), R=(200,1.5): z = dss + dsr - d (Formula 22)', {'nb_geom2d'}, ...
    @() ridgeCase());
T{end+1} = mk('G1-geom-flat', G1, 'Flat terrain with collinear vertices creates no edge', 'ISO 9613-2:2024 cl. 7.4.1 (no edge, no diffraction)', {'nb_geom2d'}, ...
    @() row({'edges found'}, 0, size(nb_geom2d(0:20:200, zeros(1,11), [0 2], [200 1.5]).edges, 1), 0));
T{end+1} = mk('G1-geom-neg', G1, 'Negative z (clear line of sight over a real crest)', 'text under Formula (22), printed p. 17: z negative when LOS passes above the edge', {'nb_geom2d'}, ...
    @() row({'z'}, -(2*hypot(100,4) - 200), nb_geom2d([0 100 200],[0 1 0],[0 5],[200 5]).z, 1e-9));
T{end+1} = mk('G1-compliance', G1, 'One exceeded band fails the point although dB(A) passes', 'brief: per-band PASS/FAIL logic', {'nb_compliance'}, ...
    @() complianceCase());
T{end+1} = mk('G1-octave-tone', G1, 'Octave filter bank reads a 1 kHz tone of 0.1 rms at -20 dB re 1 unit', 'hand: 20 lg(0.1); tolerance 0.15 dB from the custom Butterworth bank (NOT verified for IEC 61260-1)', {'nb_octave_spl'}, ...
    @() toneCase());
T{end+1} = mk('G1-butter-sos', G1, 'Butterworth band-pass design (no toolbox): -3.0103 dB at both edges, 0 dB at the centre, stable', 'analytic: |H|^2 = 1/2 at the -3 dB edges, 10 lg(1/2) = -3.0103 dB; unity gain at the warped-axis centre; also compared with butter() and scipy offline', {'nb_butter_sos'}, ...
    @() butterCase());
T{end+1} = mk('G1-factor8', G1, 'Lateral path beyond 8x the vertical support distance is neglected (2024 mode)', 'ISO 9613-2:2024 7.4.3, printed p. 19 (long wall, edges 100 m off the line)', {'nb_receiver_3d','nb_lateral'}, ...
    @() factor8Case());

% ------------------------------------------------------------------------ G2 independent reference
% ISO 9613-1:1993 Table 1(a), air temperature -20 deg C, 101.325 kPa, alpha in dB/km, printed p. 5 (PDF p. 8).
% Table frequencies are preferred 1/3-octave frequencies; values were computed at the EXACT mid-band frequencies.
rh = [10 15 20 30 40 50 60 70 80 90 100];
tab = struct();
tab.f63  = [7.56e-1 7.04e-1 6.02e-1 4.21e-1 3.08e-1 2.41e-1 2.00e-1 1.73e-1 1.55e-1 1.42e-1 1.33e-1];
tab.f125 = [1.20    1.43    1.49    1.28    9.98e-1 7.76e-1 6.22e-1 5.14e-1 4.39e-1 3.84e-1 3.44e-1];
tab.f250 = [1.43    1.95    2.42    2.93    2.83    2.46    2.06    1.73    1.46    1.26    1.09];
tab.f315 = [1.46    2.05    2.63    3.49    3.70    3.43    3.00    2.57    2.20    1.90    1.65];
fx = struct('f63', 1000*10^(-1.2), 'f125', 1000*10^(-0.9), 'f250', 1000*10^(-0.6), 'f315', 1000*10^(-0.5));
names = fieldnames(tab);
for q = 1:numel(names)
    nm = names{q};
    T{end+1} = mk(['G2-atm-' nm], G2, sprintf('A_atm coefficient at %s Hz (third-octave %.2f Hz exact), -20 deg C, RH 10-100 %%', nm(2:end), fx.(nm)), ...
        'ISO 9613-1:1993 Table 1(a), printed p. 5; tolerance = rounding of the 3 significant digits printed (0.8 %)', {'nb_aatm'}, ...
        @() atmRow(rh, tab.(nm), fx.(nm))); %#ok<AGROW>
end

% ------------------------------------------------------------------------ G3 ISO/TR 17534-3
ids = nb_bench_cases();
for k = 1:numel(ids)
    c = nb_bench_cases(ids{k});
    T{end+1} = mk(['G3-' ids{k}], G3, [ids{k} ' ' c.title], ['ISO/TR 17534-3:2015 ' c.ref], {'nb_receiver_3d','run_acoustic_case','nb_bench_run'}, @() benchRow(ids{k})); %#ok<AGROW>
    if strcmp(c.status, 'blocked'), T{end}.status0 = 'BLOCKED'; end
end

% ------------------------------------------------------------------------ G4 ISO 9613-2:2024
T{end+1} = mk('G4-table3-s', G4, 'Table 3 functions a'', b'', c'', d'' for the source region (hs = 1 m, dp = 194.16 m, G = 1)', ...
    'Values printed in ISO/TR 17534-3 Table 15 (T06) for the ISO 9613-2 Table 3 expressions; the 2024 Table 3 expressions (printed p. 11) are identical', {'nb_agr'}, ...
    @() row({'a''','b''','c''','d'''}, [2.45 9.20 10.16 3.49], nb_agr(1,1,1,1,4,194.16).As(2:5) + 1.5, 0.006));
T{end+1} = mk('G4-table3-r', G4, 'Table 3 functions for the receiver region (hr = 4 m, dp = 194.16 m, G = 1)', ...
    'ISO/TR 17534-3 Table 15 (T06), a''..d'' for r: 4.24 3.50 1.51 1.50', {'nb_agr'}, ...
    @() row({'a''','b''','c''','d'''}, [4.24 3.50 1.51 1.50], nb_agr(1,1,1,1,4,194.16).Ar(2:5) + 1.5, 0.006));
T{end+1} = mk('G4-agr-1996-vs-2024', G4, 'A_gr 2024 (with K_geo) differs from the plain sum by < 0.01 dB for T01 geometry', 'Formulae (11)-(13), printed p. 10; K_geo = 0.9996 here (hand)', {'nb_agr'}, ...
    @() row({'max |A_gr2024 - A_gr1996|'}, 0, max(abs(nb_agr(0.5,0.5,0.5,1,4,194.16).Agr - nb_agr(0.5,0.5,0.5,1,4,194.16,'iso1996').Agr)), 0.01));
T{end+1} = ext('G4-chain-2024', G4, 'Complete ISO 9613-2:2024 chain against authoritative benchmark values', 'none exist', ...
    'Independent benchmark unavailable: ISO/TR 17534-3 targets ISO 9613-2:1996 and no published reference results for the 2024 edition were supplied. Full-standard conformance is NOT asserted.', 'SKIP');

% ------------------------------------------------------------------------ G5 DRAFT
src5 = 'DAmd 1 screenshot (eqs. 18 and 21 only); DRAFT-AMENDMENT, not an official amendment';
T{end+1} = mk('G5-eq18-positive', G5, 'DRAFT eq. (18) for z > 0: 10 lg[3 + (C2/lambda) C3 z K_met], z = 0.5, 1 kHz', src5, {'nb_dz'}, ...
    @() row({'D_z'}, 10*log10(3 + (20/0.34)*0.5), nb_dz(0.5,1e-9,1e-9,1e-9,0,'draft2026',false).Dz(5), 1e-6));
T{end+1} = mk('G5-eq18-zmin', G5, 'DRAFT: D_z continuous at z_min (3 - 2 = 1 -> 0 dB) and zero below', src5, {'nb_dz'}, ...
    @() row({'z_min + 1e-9','z_min - 1e-3'}, [0 0], [nb_dz(-2*0.34/20+1e-9,1e-9,1e-9,1e-9,0,'draft2026',false).Dz(5) nb_dz(-2*0.34/20-1e-3,100,100,200,0,'draft2026',false).Dz(5)], 1e-6));
T{end+1} = mk('G5-eq21-kmet', G5, 'DRAFT eq. (21): K_met = exp[-(1/2000) sqrt(dss dsr d/(2z))] for z > 0, 1 for z <= 0', src5, {'nb_dz'}, ...
    @() row({'z = 0.4','z = -0.01'}, [exp(-(1/2000)*sqrt(100*120*200/(2*0.4))) 1], [nb_dz(0.4,100,120,200,0,'draft2026',false).Kmet(5) nb_dz(-0.01,100,120,200,0,'draft2026',false).Kmet(5)], 1e-12));
T{end+1} = mk('G5-lateral', G5, 'DRAFT: lateral paths keep K_met = 1 and no top-path cap', src5, {'nb_dz'}, ...
    @() row({'K_met lateral'}, 1, nb_dz(0.5,500,500,1000,0,'draft2026',true).Kmet(5), 0));
T{end+1} = mk('G5-differs', G5, 'DRAFT and published equations give different D_z (they are never mixed)', 'DAmd 1 screenshot vs ISO 9613-2:2024 eqs. (18), (21)', {'nb_dz'}, ...
    @() row({'|D_z draft - D_z published|, dB'}, 1, double(abs(nb_dz(0.5,50,50,100,0,'draft2026',false).Dz(5) - nb_dz(0.5,50,50,100,0,'iso2024',false).Dz(5)) > 1e-3), 0));

% ------------------------------------------------------------------------ G6 integration
G6list = { ...
  'MATLAB hot reload: an edited .m file changes the next result and invalidates the cache', 'tests/test_hot_reload.py'; ...
  'Flat, 2D, 3D, obstacle and screen scenarios through the API with real MATLAB', 'tests/test_api*.py, test_field2d.py, test_dem3d.py, test_obstacles3d.py, test_screens.py'; ...
  'DEM import (ESRI ASCII, XYZ, GeoTIFF), CRS and unit handling', 'tests/test_dem_import.py'; ...
  'Audio: WAV upload, interval, calibration, background, L_W estimate', 'tests/test_audio.py, test_api_audio.py'; ...
  'Projects, cases, persistence, duplicate, Excel export (one sheet per case)', 'tests/test_projects.py'; ...
  'Per-band compliance logic including no-data handling', 'tests/test_compliance.py'};
for k = 1:size(G6list,1)
    T{end+1} = ext(sprintf('G6-%d', k), G6, G6list{k,1}, G6list{k,2}, ...
        'Executed by the repository pytest suite (python -m pytest tests). Not re-run inside this screen; see the validation report for the recorded outcome.', 'EXTERNAL'); %#ok<AGROW>
end
end

% ----------------------------------------------------------------------------- helpers
function r = ridgeCase()
dss = hypot(100, 8);  dsr = hypot(100, 8.5);  d = hypot(200, 0.5);
g = nb_geom2d([0 100 200], [0 10 0], [0 2], [200 1.5]);
r = row({'dss','dsr','z'}, [dss dsr dss+dsr-d], [g.dss g.dsr g.z], 1e-9);
end

function r = complianceCase()
lp = 40*ones(1,8);  lp(4) = 46;
c = nb_compliance(lp, 20*ones(1,8), struct('bands', 45*ones(1,8), 'weighting', 'Z', 'overallA', 60));
r = row({'code (0 = FAIL)','worst band index','margin 500 Hz'}, [0 4 1], [c.code c.worstBand c.margin(4)], 1e-12);
end

function r = toneCase()
fs = 44100;  t = (0:fs*10-1)'/fs;
x = 0.1*sqrt(2)*sin(2*pi*1000*t);
s = nb_octave_spl(x, fs, 2*fs, 9*fs, []);
r = row({'L 1000 Hz band'}, 20*log10(0.1), s.L(5), 0.15);
end

function r = butterCase()
fs = 48000;  f1 = 707.1;  f2 = 1414.2;
S = nb_butter_sos(3, [f1 f2]/(fs/2));
dB = @(f) 20*log10(abs(sosResp(S, 2*pi*f/fs)));
fo = atan(sqrt(tan(pi*f1/fs)*tan(pi*f2/fs)))*fs/pi;      % centre on the bilinear-warped axis
rad = 0;  for k = 1:size(S,1), rad = max(rad, max(abs(roots(S(k,4:6))))); end
r = row({'edge f1 (dB)', 'edge f2 (dB)', 'centre (dB)', 'max pole radius < 1'}, [10*log10(0.5), 10*log10(0.5), 0, 1], [dB(f1), dB(f2), dB(fo), 1 + (rad >= 1)], 0.001);
end

function H = sosResp(S, w)
H = 1;  e = exp(-1j*w);
for k = 1:size(S,1), H = H * (S(k,1) + S(k,2)*e + S(k,3)*e^2) / (S(k,4) + S(k,5)*e + S(k,6)*e^2); end
end

function r = factor8Case()
dem = struct('x0', 0, 'y0', 0, 'cs', 10, 'Z', zeros(41, 41));
obs = {struct('x', [200; 200], 'y', [100; 300], 'top', 5)};
base = struct('Lw', 100*ones(1,8), 'G', struct('Gs',0.5,'Gm',0.5,'Gr',0.5), 'atm', struct('T_C',10,'RH',70,'p_kPa',101.325), 'mode', 'iso2024', 'skipFingerprint', true);
q = nb_receiver_3d(dem, obs, [100 200], 2, [300 200], 1.5, base);
r = row({'left path used','right path used'}, [0 0], [q.geom.lateral.left.valid q.geom.lateral.right.valid], 0);
end

function r = atmRow(rh, ref, f)
act = zeros(size(ref));
for i = 1:numel(rh)
    [~, a] = nb_aatm(1000, -20, rh(i), 101.325, f);
    act(i) = a;
end
lab = arrayfun(@(x) sprintf('RH %d %%', x), rh, 'UniformOutput', false);
r = row(lab, ref, act, 0.008*max(ref));                                 % scalar tol replaced per row below
r.tol = 0.008*ref + 0.0006;
end

function r = benchRow(id)
b = nb_bench_run(id);
lab = cell(1, numel(b.qname));
for i = 1:numel(b.qname)
    if b.band(i) > 0, lab{i} = sprintf('%s %g Hz', b.qname{i}, b.band(i)); else, lab{i} = b.qname{i}; end
end
r = struct('labels', {lab}, 'expected', b.expected(:)', 'actual', b.actual(:)', 'tol', b.tols(:)', 'detail', [b.notes ' ' b.blockedReason]);
if strcmp(b.status, 'BLOCKED'), r.status = 'BLOCKED'; end
end
