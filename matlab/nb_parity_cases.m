function cases = nb_parity_cases()
%NB_PARITY_CASES Test calls used to prove that the generated Python gives the SAME results as MATLAB.
%   cases = NB_PARITY_CASES() returns a cell array; each entry is a struct
%       fn       name of a function in matlab/core
%       args     cell array with the input arguments
%       nargout  number of outputs to compare (default 1)
%   nb_export_python.m runs every case in MATLAB and in the generated Python and compares all outputs.
%
%   HOW TO ADD A TEST for a function you changed or added:
%       add(struct('fn', 'my_function', 'args', {{ 1, 'text', [1 2 3] }}, 'nargout', 2));
%   Inputs must be numbers, strings, structs, cell arrays (no function handles / objects).
%   A call that is supposed to fail is fine: both languages must then raise the same error identifier.
cases = {};

% ---------------------------------------------------------------- scalar building blocks
for T = [0 15 20 35], for RH = [20 70 100]
    add('nb_aatm', {100, T, RH, 101.325}, 2);
    add('nb_aatm', {[50 500 2000], T, RH, 98}, 2);
end, end
add('nb_aatm', {1000, 20, 70, 101.325, [63 1000 8000]}, 2);
add('nb_aatm', {100, 20, 0, 101.325}, 1);                    % error: RH
add('nb_aatm_1996', {250, 20, 70}, 2);
add('nb_aatm_1996', {250, 10, 70}, 1);                       % error: only 20 C / 70 %
add('nb_adiv', {[1 10 100 1000]}, 1);
add('nb_adiv', {0}, 1);                                      % error
for mode = {'iso2024', 'iso1996'}
    for G = [0 0.3 1]
        for hh = [0.5 2 8]
            add('nb_agr', {G, G, G, hh, 1.5, 120, mode{1}}, 1);
            add('nb_agr', {G, 0.5, 1 - G, hh, hh, 20, mode{1}}, 1);
        end
    end
end
add('nb_agr', {1.5, 0, 0, 1, 1, 100}, 1);                    % error
add('nb_agr_simplified', {1.2, 80, 79.9, 1, 1.5}, 1);
add('nb_cmet', {2, 1, 1.5, 200}, 1);
add('nb_cmet', {2, 1, 1.5, 5}, 1);
add('nb_cmet', {-1, 1, 1.5, 5}, 1);                          % error
add('nb_energy_sum', {[50 60]}, 1);
add('nb_energy_sum', {[50 60; 55 55; 40 70], 2}, 1);
add('nb_energy_sum', {[50 60; 55 55; 40 70], 1}, 1);
add('nb_bands', {}, 1);
for mode = {'iso2024', 'draft2026', 'iso1996'}
    for z = [-0.2 0.001 0.4 3 25]
        add('nb_dz', {z, 12, 30, 41, 0, mode{1}, false}, 1);
        add('nb_dz', {z, 12, 30, 41, 7, mode{1}, false}, 1);
        add('nb_dz', {z, 12, 30, 41, 3, mode{1}, true}, 1);
    end
end
add('nb_dz', {0.5, 10, 10, 20, 0, 'bogus', false}, 1);       % error
add('nb_abar', {[5 6 7 8 9 10 11 12], [], [], [1 1 1 -1 0 0 0 0]}, 1);
add('nb_abar', {[5 6 7 8 9 10 11 12], [3 3 3 3 3 3 3 3], [4 4 4 4 4 4 4 4], zeros(1,8)}, 1);
add('nb_abar', {[], [], [], zeros(1,8)}, 1);
add('nb_abar', {[5 6 7 8 9 10 11 12], [], [], zeros(1,8), [2 2 2 2 2 2 2 2; 9 9 9 9 9 9 9 9]}, 1);

% ---------------------------------------------------------------- materials, enclosures, limits
add('nb_material', {'massLaw', 12, [63 125 250 500 1000 2000 4000 8000], 'normal'}, 1);
add('nb_material', {'massLaw', 12, [63 125 250 500 1000 2000 4000 8000], 'field'}, 1);
add('nb_material', {'surfaceMass', 2400, 0.1, true}, 1);
add('nb_material', {'surfaceMass', 2400, 0.1, false}, 1);   % error
add('nb_material', {'effectiveTL', [20 22 25 28 31 34 37 40], 0.01}, 1);
add('nb_material', {'resolve', struct('surface_mass', 8)}, 1);
add('nb_material', {'resolve', struct('volume_density', 7800, 'thickness', 0.002, 'solid', true, 'tl_model', 'field')}, 1);
add('nb_material', {'resolve', struct('TL', [10 12 14 16 18 20 22 24], 'openness', 0.05)}, 1);
add('nb_material', {'resolve', struct()}, 1);                % error
mat1 = struct('surface_mass', 25);
add('nb_enclosure', {90*ones(1,8), struct('S_total', 20, 'A_in', 6, 'mat', mat1, 'S_open', 0.4)}, 1);
add('nb_enclosure', {90*ones(1,8), struct('S_total', 20, 'A_in', 6, 'mat', mat1)}, 1);
surf = struct('name', {'wall', 'roof'}, 'area', {12, 8}, 'mat', {struct('surface_mass', 25), struct('TL', 10:3:31)}, ...
    'alpha', {0.3*ones(1,8), 0.1*ones(1,8)});
add('nb_enclosure_surfaces', {95*ones(1,8), surf, 0.5}, 1);
add('nb_enclosure_surfaces', {95*ones(1,8), surf}, 1);
lim = struct('bands', [NaN NaN 50 50 50 NaN NaN NaN], 'weighting', 'Z', 'overallA', 40);
add('nb_compliance', {[40 45 52 49 51 40 30 20; 30 30 30 30 30 30 30 30; NaN(1,8)], ...
    [20 30 40 45 51 41 31 19; 10 15 20 25 30 31 29 20; NaN(1,8)], lim}, 1);
add('nb_compliance', {[40 45 52 49 51 40 30 20], [20 30 40 45 51 41 31 19], struct('weighting', 'A', 'bands', 50*ones(1,8))}, 1);
add('nb_compliance', {[40 45 52 49 51 40 30 20], [20 30 40 45 51 41 31 19], struct()}, 1);
add('nb_compliance', {[40 45 52], [20 30 40], struct()}, 1);   % error

% ---------------------------------------------------------------- geometry
xp = [0 20 40 60 80 100 120];
zp = [0 0 4 9 6 2 0];
add('nb_geom2d', {xp, zp, [0 1.5], [120 1.5]}, 1);
add('nb_geom2d', {xp, zp, [0 12], [120 10]}, 1);
add('nb_geom2d', {[0 50 100], [0 0 0], [0 1], [100 1]}, 1);
add('nb_geom2d', {xp, zp, [130 1.5], [120 1.5]}, 1);          % error
dem = nb_parity_dem();
add('nb_dem_sample', {dem, [0 15 123.4 -5 395], [0 22.5 80.1 3 395]}, 1);
add('nb_dem_sample', {dem, 55.5, 66.6}, 1);
add('nb_profile_dem', {dem, [10 10], [300 250]}, 3);
add('nb_profile_dem', {dem, [10 10], [10 10]}, 3);
obsA = {struct('x', [140 160 160 140], 'y', [100 100 140 140], 'h', 9), ...
        struct('x', [200 200], 'y', [60 160], 'top', 30), ...
        struct('x', [60 80 80 60], 'y', [150 150 170 170], 'h', 5, 'gap', 2, 'mat', struct('surface_mass', 1.2))};
add('nb_obstacles', {'resolve', dem, obsA}, 1);
obsR = nb_obstacles('resolve', dem, obsA);
add('nb_obstacles', {'intervals', obsR, [100 120], [260 120]}, 1);
add('nb_obstacles', {'profile', dem, obsR, [100 120], [260 120]}, 4);
add('nb_ground_factors', {{struct('x', [0 100 100 0], 'y', [-50 -50 50 50], 'G', 0.2), ...
    struct('x', [100 300 300 100], 'y', [-50 -50 50 50], 'G', 0.9)}, 0.5, [10 0], [250 0], 1, 1.5}, 1);
add('nb_lateral', {obsR, 1, [100 120 6], [260 120 5], dem}, 1);
add('nb_lateral', {obsR, [1 2], [100 120 6], [260 120 5], dem}, 1);

% ---------------------------------------------------------------- the complete chain
G = struct('Gs', 0.4, 'Gm', 0.5, 'Gr', 0.6);
atm = struct('T_C', 15, 'RH', 70, 'p_kPa', 101.325);
base = struct('Lw', [100 100 100 100 100 95 90 85], 'G', G, 'atm', atm, 'hs', 1, 'hr', 1.5, 'dp', 150, 'dh', 0.7);
add('run_acoustic_case', {base}, 1);
for mode = {'iso2024', 'draft2026', 'iso1996'}
    c = base;  c.mode = mode{1};
    if strcmp(mode{1}, 'iso1996'), c.atm = struct('T_C', 20, 'RH', 70, 'p_kPa', 101.325); end
    c.barrier = struct('z', 0.9, 'dss', 40, 'dsr', 112, 'e', 0);
    add('run_acoustic_case', {c}, 1);
    c.barrier = struct('z', 0.9, 'dss', 40, 'dsr', 112, 'e', 6, 'side1', struct('z', 0.3, 'dss', 41, 'dsr', 113, 'e', 0), ...
        'side2', struct('z', 0.5, 'dss', 42, 'dsr', 111, 'e', 2), 'mask', [0 0 1 1 1 1 1 1]);
    add('run_acoustic_case', {c}, 1);
end
c = base;  c.groundMethod = 'simplified';  c.C0 = 2;
add('run_acoustic_case', {c}, 1);
c = base;  c.screenTL = struct('TL', 15:3:36);  c.barrier = struct('z', 0.9, 'dss', 40, 'dsr', 112, 'e', 0);
c.limits = struct('bands', [NaN NaN 40 40 40 NaN NaN NaN], 'weighting', 'A', 'overallA', 35);
add('run_acoustic_case', {c}, 1);
c = base;  c.enclosure = struct('S_total', 20, 'A_in', 6, 'mat', mat1, 'S_open', 0.4);
add('run_acoustic_case', {c}, 1);
c = base;  c.Lw = [1 2 3];
add('run_acoustic_case', {c}, 1);                              % error

tp = struct('x', xp, 'z', zp);
c2 = struct('Lw', base.Lw, 'G', G, 'atm', atm, 'terrain', tp, 'source', struct('x', 5, 'h', 1), ...
    'receiver', struct('x', 115, 'h', 1.5));
add('run_case_2d', {c2}, 1);
cf = rmfield(c2, {'receiver'});  cf.receiver = struct('x', [60 90 110], 'h', 1.5);
add('run_field_2d', {cf}, 1);

% ---------------------------------------------------------------- terrain + obstacles (3D)
b3 = struct('Lw', base.Lw, 'G', G, 'atm', atm, 'mode', 'iso2024');
c3 = b3;  c3.dem = dem;  c3.source = struct('x', 100, 'y', 120, 'h', 2);  c3.obstacles = obsA;
c3.receiver = struct('x', 260, 'y', 120, 'h', 1.5);
add('run_case_3d', {c3}, 1);
c3.receiver = struct('x', 330, 'y', 300, 'h', 4);
add('run_case_3d', {c3}, 1);
c3.receiver = struct('x', 150, 'y', 120, 'h', 1.5);            % inside an obstacle
add('run_case_3d', {c3}, 1);
c3.mode = 'iso1996';  c3.atm = struct('T_C', 20, 'RH', 70, 'p_kPa', 101.325);  c3.receiver = struct('x', 250, 'y', 130, 'h', 1.5);
add('run_case_3d', {c3}, 1);
cg = b3;  cg.dem = dem;  cg.source = struct('x', 100, 'y', 120, 'h', 2);  cg.obstacles = obsA;
cg.grid = struct('x', 200:30:320, 'y', 80:30:200);  cg.hr = 1.5;
cg.limits = struct('bands', [NaN NaN 40 40 40 NaN NaN NaN], 'weighting', 'Z', 'overallA', 45);
add('run_field_3d', {cg}, 1);
cg2 = cg;  cg2 = rmfield(cg2, {'obstacles', 'limits'});
add('run_field_3d', {cg2}, 1);
cgs = b3;  cgs.dem = dem;  cgs.source = struct('x', 100, 'y', 120, 'h', 2);
cgs.obstacles = {struct('x', [180 190 190 180], 'y', [100 100 140 140], 'h', 6)};
cgs.grid = struct('x', 240:20:300, 'y', 100:20:160);  cgs.hr = 1.5;
cgs.groundAreas = {struct('x', [150 400 400 150], 'y', [0 0 400 400], 'G', 0.9)};
add('run_field_3d', {cgs}, 1);
add('nb_receiver_3d', {dem, obsR, [100 120], 2, [260 120], 1.5, b3}, 1);
add('nb_receiver_3d', {dem, obsR, [100 120], 2, [100 120], 1.5, b3}, 1);   % receiver at source

% ---------------------------------------------------------------- many random geometries (deterministic seed)
rng(11, 'twister');
for k = 1:40
    n  = 6 + floor(rand*40);
    xq = cumsum(0.5 + 3*rand(1, n));  xq = xq - xq(1);
    zq = 8*rand*sin(xq/(5 + 20*rand)) + 4*rand(1, n) + 0.05*xq;
    if mod(k, 5) == 0, zq(:) = 0; end                 % flat
    if mod(k, 7) == 0, zq = linspace(0, 6, n); end    % straight slope (collinear points)
    sxx = xq(1) + 0.2*rand*(xq(end) - xq(1));  rxx = xq(end) - 0.2*rand*(xq(end) - xq(1));
    gS = interp1(xq, zq, sxx);  gR = interp1(xq, zq, rxx);
    add('nb_geom2d', {xq, zq, [sxx, gS + 0.3 + 4*rand], [rxx, gR + 0.3 + 4*rand]}, 1);
end
add('nb_geom2d', {[0 1], [0 0], [0 1], [1 1]}, 1);
add('nb_geom2d', {[0 10 10], [0 0 0], [1 1], [8 1]}, 1);                % error: not increasing
add('nb_geom2d', {xp, zp, [10 -3], [100 2]}, 1);                         % error: below terrain
add('nb_geom2d', {xp, zp, [100 3], [10 3]}, 1);                          % error: order

rng(5, 'twister');
for k = 1:60
    Sp = [20 + 340*rand, 20 + 340*rand];  Rp = [20 + 340*rand, 20 + 340*rand];
    add('nb_obstacles', {'intervals', obsR, Sp, Rp}, 1);
    add('nb_obstacles', {'profile', dem, obsR, Sp, Rp}, 4);
    add('nb_profile_dem', {dem, Sp, Rp}, 3);
    add('nb_dem_sample', {dem, Sp(1), Sp(2)}, 1);
end
add('nb_obstacles', {'intervals', {}, [10 10], [100 100]}, 1);
add('nb_obstacles', {'profile', dem, {}, [10 10], [100 100]}, 4);
add('nb_obstacles', {'profile', dem, obsR, [100 100], [100 100]}, 4);
add('nb_obstacles', {'profile', dem, obsR, [-50 -50], [100 100]}, 4);    % outside the DEM
add('nb_obstacles', {'resolve', dem, {struct('x', [1 2 3], 'y', [1 1 1], 'h', -1)}}, 1);   % error
add('nb_obstacles', {'bogus'}, 1);                                       % error
add('nb_dem_sample', {dem, [10 20; 30 40], [10 20; 30 40]}, 1);
add('nb_dem_sample', {dem, 390, 390}, 1);
add('nb_dem_sample', {dem, 389.99, 0}, 1);
add('nb_dem_sample', {dem, NaN, 5}, 1);

rng(3, 'twister');
for k = 1:30
    Rp = [20 + 340*rand, 20 + 340*rand];
    c = b3;  if mod(k, 3) == 0, c.mode = 'iso1996'; c.atm = struct('T_C', 20, 'RH', 70, 'p_kPa', 101.325); end
    add('nb_receiver_3d', {dem, obsR, [100 120], 2, Rp, 1.5 + 3*rand, c}, 1);
    add('nb_receiver_3d', {dem, {}, [100 120], 2, Rp, 1.5, c}, 1);
end
cg3 = b3;  cg3.dem = dem;  cg3.source = struct('x', 105, 'y', 110, 'h', 1);  cg3.obstacles = obsA;
cg3.grid = struct('x', 20:25:380, 'y', 20:25:380);  cg3.hr = 2;
add('run_field_3d', {cg3}, 1);

% ---------------------------------------------------------------- ISO/TR 17534-3 benchmark (T01..T19), whole pipeline
for k = 1:19
    add('nb_bench_run', {sprintf('T%02d', k)}, 1);
end

    function add(fn, args, nout)
        cases{end+1} = struct('fn', fn, 'args', {args}, 'nargout', nout); %#ok<AGROW>
    end
end

function dem = nb_parity_dem()
% 40 x 40 cells of 10 m with a ridge and a hill (analytic, no random numbers)
[X, Y] = meshgrid(0:39, 0:39);
Z = 6*exp(-((X-20).^2 + (Y-14).^2)/30) + 3*sin(X/6).*cos(Y/9) + 0.02*X;
dem = struct('x0', 0, 'y0', 0, 'cs', 10, 'Z', Z);
end
