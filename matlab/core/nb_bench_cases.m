function c = nb_bench_cases(id)
%NB_BENCH_CASES ISO/TR 17534-3:2015 test cases T01-T19 (inputs and reference results).
%   c = NB_BENCH_CASES()    -> cell array of all case ids
%   c = NB_BENCH_CASES('T08') -> struct describing the case
%
%   SOURCE OF EVERY NUMBER: ISO/TR 17534-3:2015(E), "Software for the
%   calculation of sound outdoors - Part 3: Recommendations for quality
%   assured implementation of ISO 9613-2 in software" (file
%   ISO_TR 17534-3_2015.pdf in the project folder), clause 6.2. The table
%   number and printed page of each reference result are in c.ref.
%   THESE REFERENCE VALUES TARGET ISO 9613-2:1996, not the 2024 edition, so
%   the cases are run in the explicitly labelled 'iso1996' compatibility
%   mode. A 2024-mode mismatch against them is NOT a conformance failure.
%   Tolerance: +-0.05 dB for band values and totals ("considered to be
%   correct if the deviation does not exceed +-0,05 dB", note a of each
%   spectral table), except where the table itself gives fewer decimals.
%
%   c.status: 'runnable' or 'blocked' (with c.blocked reason). A blocked
%   case keeps its reference values but is never reported as passed.
ids = arrayfun(@(k) sprintf('T%02d', k), 1:19, 'UniformOutput', false);
if nargin == 0, c = ids; return; end
if ~any(strcmp(id, ids)), error('nb:bench:id', 'Unknown case %s', id); end

Lw93 = 93*ones(1,8);
atm  = struct('T_C', 20, 'RH', 70, 'p_kPa', 101.325);
tol  = 0.05;
poly = @(x, y, top) struct('x', x(:), 'y', y(:), 'top', top);
areasT04 = {struct('x', [0 50 50 0],    'y', [60 60 -10 -10], 'G', 0.2), ...
            struct('x', [50 150 150 50], 'y', [60 60 -10 -10], 'G', 0.5), ...
            struct('x', [150 210 210 150], 'y', [60 60 -10 -10], 'G', 0.9)};
areasT06 = {struct('x', [0 50 50 0],    'y', [60 60 -10 -10], 'G', 0.9), ...
            struct('x', [50 150 150 50], 'y', [60 60 -10 -10], 'G', 0.5), ...
            struct('x', [150 210 210 150], 'y', [60 60 -10 -10], 'G', 0.2)};
bldgCube = poly([55 65 65 55], [5 5 15 15], 10);
bldg8 = poly([10.96 12.00 14.50 17.00 18.04 17.00 14.50 12.00], [15.50 13.00 11.96 13.00 15.50 18.00 19.04 18.00], 10);

c = struct('id', id, 'group', 'ISO/TR 17534-3:2015 (reference data target ISO 9613-2:1996)', 'mode', 'iso1996', ...
    'Lw', Lw93, 'atm', atm, 'tol', tol, 'status', 'runnable', 'blocked', '', 'notes', '', ...
    'S', [10 10 1], 'R', [200 50 4], 'G', 0, 'areas', {{}}, 'G0', 0, 'obstacles', {{}}, ...
    'groundMethod', 'general', 'type', 'dem', 'expected', struct(), 'ref', '');

switch id
    case 'T01'
        c.title = 'Flat ground, reflecting (G = 0)';  c.G = 0;
        c.expected = ex([39.90 39.86 39.70 39.37 38.95 38.17 35.47 25.04], 47.46, [13.70 23.76 31.10 36.17 38.95 39.37 36.47 23.94], 44.29, []);
        c.ref = 'Table 4, p. 7 (inputs Tables 1-2, p. 6)';
    case 'T02'
        c.title = 'Flat ground, mixed (G = 0.5)';  c.G = 0.5;
        c.expected = ex([39.90 36.17 33.02 33.20 36.11 36.33 33.63 23.20], 44.61, [13.70 20.07 24.42 30.00 36.11 37.53 34.63 22.10], 41.53, []);
        c.ref = 'Table 5, p. 8';
    case 'T03'
        c.title = 'Flat ground, porous (G = 1)';  c.G = 1;
        c.expected = ex([39.90 32.48 26.33 27.03 33.27 34.49 31.79 21.36], 42.80, [13.70 16.38 17.73 23.83 33.27 35.69 32.79 20.26], 39.14, []);
        c.ref = 'Table 6, p. 9';
    case 'T04'
        c.title = 'Flat ground with spatially varying ground factor';
        c.areas = areasT04;  c.G0 = 0.5;
        c.expected = ex([39.90 36.24 35.23 36.04 36.95 36.57 33.87 23.45], 45.25, [13.70 20.14 26.63 32.84 36.95 37.77 34.87 22.35], 42.23, []);
        c.ref = 'Tables 7 and 9, pp. 10-11 (areas A1 G=0.2, A2 G=0.5, A3 G=0.9)';
        c.groundCheck = struct('Gs', 0.20, 'Gm', 0.43, 'Gr', 0.67);        % Table 8 (values re-derived from the area table, see notes)
    case 'T05'
        c.title = 'As T04, alternative A-weighted ground method (cl. 7.3.2)';
        c.areas = areasT04;  c.G0 = 0.5;  c.groundMethod = 'simplified';
        c.expected = ex([34.90 34.86 34.71 34.38 33.95 33.17 30.48 20.05], 42.46, [8.70 18.76 26.11 31.18 33.95 34.37 31.48 18.95], 39.30, []);
        c.ref = 'Table 10, p. 11';
    case 'T06'
        c.title = 'Spatially varying ground height and acoustic properties (geometry as tabulated)';
        c.type = 'direct';  c.areas = areasT06;  c.G0 = 0.5;
        c.direct = struct('hs', 1, 'hr', 4, 'dh', 10, 'dp', 194.16);        % Table 13/14: z_rel 1 and 4, ground 0 m at S and 10 m at R, dp 194.16 m
        c.expected = ex([39.88 35.65 29.70 29.24 34.82 35.83 33.13 22.68], 43.85, [13.68 19.55 21.10 26.04 34.82 37.03 34.13 21.58], 40.59, []);
        c.ref = 'Tables 11-15, pp. 13-14';
        c.notes = ['Ground surface from contour lines (Table 12) is NOT reconstructed: heights above ground, the 10 m ground-elevation difference and dp are taken from Tables 13-14. ' ...
                   'This verifies the attenuation chain (3D distance, ground regions, A_gr), not terrain construction.'];
    case 'T07'
        c.title = 'As T06, alternative A-weighted ground method';
        c.type = 'direct';  c.areas = areasT06;  c.G0 = 0.5;  c.groundMethod = 'simplified';
        c.direct = struct('hs', 1, 'hr', 4, 'dh', 10, 'dp', 194.16, 'hm', 4.99);   % Table 17: hm = 4.99 m
        c.expected = ex([35.36 35.32 35.16 34.83 34.40 33.62 30.92 20.47], 42.91, [9.16 19.22 26.56 31.63 34.40 34.82 31.92 19.37], 39.75, []);
        c.ref = 'Tables 16-18, p. 15';
        c.notes = 'hm = 4.99 m is taken from Table 17 (it follows from the contour-line terrain, which is not reconstructed).';
    case 'T08'
        c.title = 'Varying ground factor, long barrier';
        c.areas = areasT06;  c.G0 = 0.5;
        c.obstacles = {poly([100 265], [240 -180], 6)};
        c.expected = ex([34.86 30.85 29.72 29.01 27.26 26.01 21.04 8.02], 38.50, [8.66 14.75 21.12 25.81 27.26 27.21 22.04 6.92], 32.48, [5.04 4.81 0.00 0.26 7.58 9.84 12.12 14.71]);
        c.ref = 'Tables 19-21, pp. 17-18 (barrier edges S1 (100,240,6) S2 (265,-180,6))';
    case 'T09'
        c.title = 'Varying ground factor, short barrier';
        c.areas = areasT06;  c.G0 = 0.5;
        c.obstacles = {poly([175 190], [50 10], 6)};
        c.expected = ex([36.99 32.36 29.72 29.21 27.84 26.51 21.46 8.40], 39.86, [10.79 16.26 21.12 26.01 27.84 27.71 22.46 7.30], 32.93, [2.91 3.31 0.00 0.06 7.00 9.34 11.69 14.32]);
        c.ref = 'Tables 22-23, pp. 20-21 (barrier edges S1 (175,50,6) S2 (190,10,6))';
    case 'T10'
        c.title = 'Varying ground height and ground factor, short barrier (sloping top edge)';
        c.status = 'blocked';
        c.blocked = ['Needs the ground surface constructed from the contour-line rectangles of Table 12 and a barrier with a sloping top edge (17 m to 14 m, Table 25). ' ...
                     'Table 12 does not define how the surface between contours is built, so no unambiguous terrain exists to run on.'];
        c.expected = ex([36.3 31.2 28.2 25.8 24.1 22.1 16.6 4.0], 38.5, [10.14 15.12 19.58 22.64 24.12 23.34 17.59 2.86], 29.30, [3.54 4.42 1.52 3.41 10.69 13.69 16.54 18.72]);
        c.ref = 'Tables 24-27, pp. 22-24 (band levels L are tabulated with one decimal)';
    case 'T11'
        c.title = 'Cubic building, receiver at low height';
        c.S = [50 10 1];  c.R = [70 10 4];  c.G = 0.5;  c.obstacles = {bldgCube};
        c.expected = ex([50.09 44.62 39.20 35.75 34.77 33.79 32.78 31.28], 51.81, [23.89 28.52 30.60 32.55 34.77 34.99 33.78 30.18], 41.30, [8.79 12.24 16.53 20.12 22.18 23.41 24.14 24.55]);
        c.ref = 'Tables 28-31, pp. 25-27 (building Table 29)';
    case 'T12'
        c.title = 'Cubic building, receiver at large height';
        c.S = [50 10 1];  c.R = [70 10 15];  c.G = 0.5;  c.obstacles = {bldgCube};
        c.expected = ex([51.04 46.71 42.19 38.70 36.70 36.26 35.57 34.07], 53.28, [24.84 30.61 33.59 35.50 36.70 37.46 36.57 32.97], 43.81, [6.20 8.95 12.23 15.53 18.59 19.27 19.62 19.81]);
        c.ref = 'Tables 32-34, pp. 28-30';
    case 'T13'
        c.title = 'Polygonal building, receiver at low height';
        c.S = [0 10 1];  c.R = [30 20 6];  c.G = 0.6;  c.obstacles = {bldg8};
        c.expected = ex([51.17 46.66 42.86 39.28 37.00 34.02 31.22 27.93], 53.31, [24.97 30.56 34.26 36.08 37.00 35.22 32.22 26.83], 42.71, [3.72 5.54 7.89 11.24 15.36 18.78 21.14 22.71]);
        c.ref = 'Tables 35-39, pp. 31-33 (building Table 36)';
    case 'T14'
        c.title = 'Varying ground height and factor, polygonal building (30 m)';
        c.status = 'blocked';
        c.blocked = 'Needs the ground surface from the contour lines of Table 13 (same gap as T10) and a receiver 28.5 m above that ground; the surface construction is not defined.';
        c.expected = ex([34.93 30.42 25.18 21.55 20.14 17.41 12.00 -0.08], 36.87, [8.73 14.32 16.58 18.35 20.14 18.61 13.00 -1.18], 25.38, [4.20 6.50 8.21 11.02 15.34 18.28 20.96 22.51]);
        c.ref = 'Tables 40-45, pp. 34-36';
    case 'T15'
        c.title = 'Polygonal building, receiver at large height';
        c.S = [8 10 1];  c.R = [25 20 23];  c.G = 0.2;  c.obstacles = {bldg8};
        c.expected = ex([53.49 51.71 49.59 47.21 44.60 41.33 37.76 34.05], 57.53, [27.29 35.61 40.99 44.01 44.60 42.53 38.76 32.95], 49.92, [2.10 3.24 4.86 7.12 10.11 13.39 16.56 18.68]);
        c.ref = 'Tables 46-49, pp. 37-39';
    case {'T16', 'T17'}
        o1 = poly([55 65 65 55], [5 5 15 15], 8);
        o2 = poly([70 80 80], [14.50 10.17 20.17], 12);
        o3 = poly([90.11 93.27 87.27 84.11], [19.48 17.78 6.61 8.31], 10);
        c.G = 0.5;  c.obstacles = {o1, o2, o3};
        if strcmp(id, 'T16')
            c.title = 'Three buildings';  c.S = [50 10 1];  c.R = [100 15 5];
            c.expected = ex([41.03 34.28 29.33 26.64 26.45 25.68 24.22 21.07], 42.52, [14.83 18.18 20.73 23.44 26.45 26.88 25.22 19.97], 32.54, [9.91 14.04 17.29 19.87 22.11 23.32 24.08 24.51]);
            c.ref = 'Tables 50-54, pp. 40-42 (buildings Table 51)';
        else
            c.title = 'Three buildings, alternative source and receiver positions';  c.S = [50 19 1];  c.R = [98 3.5 5];
            c.expected = ex([41.54 35.28 30.55 27.18 26.39 25.63 24.17 21.02], 43.11, [15.34 19.18 21.95 23.98 26.39 26.83 25.17 19.92], 32.72, [9.37 13.01 16.03 19.28 22.12 23.33 24.09 24.52]);
            c.ref = 'Tables 55-57, pp. 43-45';
        end
    case 'T18'
        c.title = 'Complex building with backyard (source in the backyard)';
        c.status = 'blocked';
        c.blocked = ['The text layer of Table 59 (building footprint) is scrambled and the footprint cannot be read back unambiguously; ' ...
                     'the shortest paths around a concave footprint also need a visibility-graph path search that is not implemented (hull-based paths are only valid for convex clusters).'];
        c.expected = ex([41.21 37.89 33.67 29.49 27.74 27.45 26.81 24.56], 43.89, [15.01 21.79 25.07 26.29 27.74 28.65 27.81 23.46], 34.89, [11.47 14.79 18.97 23.08 24.74 24.87 24.93 24.97]);
        c.ref = 'Tables 58-63, pp. 46-49';
    case 'T19'
        c.title = 'As T06 with a reflecting barrier (image source)';
        c.status = 'blocked';
        c.blocked = 'Needs reflections from obstacle surfaces (ISO 9613-2 cl. 7.5, image sources with absorption), which are not implemented, plus the T06 contour-line terrain.';
        c.expected = ex([13.68 19.55 21.10 28.01 36.51 38.43 35.20 23.18], NaN, [13.68 19.55 21.10 28.01 36.51 38.43 35.20 23.18], 42.00, []);
        c.ref = 'Tables 64-68, pp. 50-52 (only A-weighted results are tabulated)';
end
end

function e = ex(L, Ltot, LA, LAtot, Abar)
e = struct('L', L, 'Ltot', Ltot, 'LA', LA, 'LAtot', LAtot, 'Abar', Abar);
end
