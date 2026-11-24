function s = nb_bench_scene(id)
%NB_BENCH_SCENE Plain scene description of an ISO/TR 17534-3 case, for loading it as an editable case.
%   s = NB_BENCH_SCENE('T08'). Only cases that are real 3D scenes (type 'dem') can be loaded; cases whose
%   geometry is given as tabulated heights (T06, T07) or that are blocked cannot.
c = nb_bench_cases(id);
s = struct('id', id, 'title', c.title, 'loadable', false, 'reason', '');
if strcmp(c.status, 'blocked'), s.reason = ['blocked: ' c.blocked]; return; end
if ~strcmp(c.type, 'dem'), s.reason = 'geometry is tabulated (heights, elevation difference) rather than a terrain scene'; return; end
s.loadable = true;  s.S = c.S;  s.R = c.R;  s.G = c.G;  s.G0 = c.G0;  s.mode = c.mode;  s.groundMethod = c.groundMethod;
s.areas = c.areas;  s.obstacles = c.obstacles;  s.Lw = c.Lw;  s.atm = c.atm;
end
