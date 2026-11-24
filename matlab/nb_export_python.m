function ok = nb_export_python(varargin)
%NB_EXPORT_PYTHON Translate the MATLAB core (matlab/core/*.m) into Python and prove the result is identical.
%
%   nb_export_python                      translate + test + install
%   nb_export_python('parity', false)     translate + install, skip the MATLAB-vs-Python comparison
%   nb_export_python('force', true)       install even if some test case differs (not recommended)
%   nb_export_python('core', 'D:\my\core')  use another folder of .m files
%   ok = nb_export_python(...)            true when the new Python core was installed
%
%   WHAT IT DOES
%     1. Reads every .m file of matlab/core and writes one Python module per file to noisebox/core_py_new/.
%        Function names, input names / order and output names / order are kept. The MATLAB help text becomes
%        the Python docstring and each MATLAB line is kept as a comment above its Python translation.
%     2. Runs the test calls of nb_parity_cases.m in MATLAB (with YOUR .m files) and in the new Python, and
%        compares every output number, text, struct field and error identifier.
%     3. If everything agrees, the new modules replace noisebox/core_py/ and the ArcGIS tools use them from
%        the next run on (no restart needed). Otherwise the old Python core stays in place.
%
%   RUN IT AGAIN whenever you change, add, rename or delete anything in matlab/core. Add a test call to
%   nb_parity_cases.m for each new function so that it is compared too (the report lists functions
%   without a test).
%
%   Needs: ArcGIS Pro's Python (found automatically; or set the environment variable NOISEBOX_PYTHON).
%   From a terminal:   matlab -batch "cd('<project>\matlab'); nb_export_python"
ok = false;
p = inputParser;
addParameter(p, 'core', '');
addParameter(p, 'parity', true);
addParameter(p, 'force', false);
addParameter(p, 'savecases', '');
parse(p, varargin{:});

here    = fileparts(mfilename('fullpath'));
project = fileparts(here);
core    = p.Results.core;
if isempty(core), core = fullfile(here, 'core'); end
if ~isfolder(core), error('nb:export:core', 'MATLAB core folder not found: %s', core); end
pkgDir  = fullfile(project, 'noisebox');
newDir  = fullfile(pkgDir, 'core_py_new');
curDir  = fullfile(pkgDir, 'core_py');
py      = find_python();
fprintf('NoiseBox export: MATLAB %s, Python %s\n  core folder : %s\n  Python      : %s\n\n', ...
    version, 'translator', core, py);

% required = the functions the ArcGIS tools call (a failure here stops the export)
req = '';
fid = fopen(fullfile(here, 'required_functions.txt'), 'r');
if fid > 0
    txt = textscan(fid, '%s', 'CommentStyle', '#');  fclose(fid);
    req = strjoin(txt{1}, ',');
end

% ---- 1. translate
cmd = sprintf('"%s" -I "%s" --core "%s" --out "%s" --overrides "%s" --accel "%s" --require "%s"', py, ...
    fullfile(project, 'm2py', 'export.py'), core, newDir, fullfile(here, 'python_overrides'), ...
    fullfile(here, 'python_accel'), req);
env_setenv_core(core);
[st, out] = system(cmd);
fprintf('%s\n', out);
if st ~= 0
    error('nb:export:translate', ['The translation stopped (see the lines above). The existing Python core was ' ...
        'NOT changed. Fix the construct named above, or add a hand-written Python version to ' ...
        'matlab/python_overrides/<function>.py.']);
end

% ---- 2. compare MATLAB with the new Python
allSame = true;
if p.Results.parity
    fprintf('Running the test calls in MATLAB ...\n');
    addpath(core);  addpath(here);
    cleanup = onCleanup(@() rmpath_quiet(core, here));
    clear functions                                         %#ok<CLFUNC> pick up edited .m files
    cases = nb_parity_cases();
    res = cell(size(cases));
    for k = 1:numel(cases)
        c = cases{k};
        n = max(1, c.nargout);
        try
            o = cell(1, n);
            [o{1:n}] = feval(c.fn, c.args{:});
            res{k} = struct('ok', true, 'out', {o}, 'id', '', 'msg', '');
        catch ME
            res{k} = struct('ok', false, 'out', {{}}, 'id', ME.identifier, 'msg', ME.message);
        end
    end
    matfile = p.Results.savecases;
    if isempty(matfile), matfile = [tempname '_nb_parity.mat']; end
    save(matfile, 'cases', 'res', '-v7');
    fprintf('%d test calls run in MATLAB; comparing with Python ...\n', numel(cases));
    cmd = sprintf('"%s" -I "%s" "%s" --pkg noisebox.core_py_new', py, fullfile(project, 'tests', 'parity_check.py'), matfile);
    [st, out] = system(cmd);
    fprintf('%s\n', out);
    if isempty(p.Results.savecases), delete(matfile); end
    allSame = (st == 0);
end

% ---- 3. install
if allSame || p.Results.force
    cmd = sprintf('"%s" -I "%s" --promote "%s" "%s"', py, fullfile(project, 'm2py', 'export.py'), newDir, curDir);
    [st, out] = system(cmd);
    fprintf('%s\n', out);
    if st ~= 0, error('nb:export:install', 'Could not install the new Python core: %s', out); end
    ok = true;
    fprintf('DONE. The ArcGIS tools use the new Python core from their next run.\n');
else
    fprintf(['NOT INSTALLED: at least one test call gives a different result in Python. The old Python core is still ' ...
        'in place.\nThe new code is in %s for inspection. Fix the .m file (or the translator limitation named ' ...
        'above) and run nb_export_python again.\n'], newDir);
end
end

function py = find_python()
cand = {getenv('NOISEBOX_PYTHON'), ...
    'C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe'};
try
    d = winqueryreg('HKEY_LOCAL_MACHINE', 'SOFTWARE\ESRI\ArcGISPro', 'InstallDir');
    cand{end+1} = fullfile(d, 'bin', 'Python', 'envs', 'arcgispro-py3', 'python.exe');
catch
end
for i = 1:numel(cand)
    if ~isempty(cand{i}) && isfile(cand{i}), py = cand{i}; return; end
end
error('nb:export:python', ['ArcGIS Pro''s Python was not found. Set the environment variable NOISEBOX_PYTHON to the ' ...
    'python.exe of an environment with numpy and scipy.']);
end

function env_setenv_core(core)
setenv('NOISEBOX_CORE_DIR', core);
end

function rmpath_quiet(a, b)
warning('off', 'MATLAB:rmpath:DirNotFound');
rmpath(a);  rmpath(b);
end
