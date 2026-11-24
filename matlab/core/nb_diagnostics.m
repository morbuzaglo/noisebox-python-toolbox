function d = nb_diagnostics()
%NB_DIAGNOSTICS MATLAB release, licensed toolboxes and library location, for the diagnostics screen.
v = ver('matlab');
d.release = regexprep(v(1).Release, '[()]', '');
d.version = v(1).Version;
d.libraryDir = fileparts(mfilename('fullpath'));
tb = {'signal_toolbox', 'Signal Processing Toolbox'; 'map_toolbox', 'Mapping Toolbox'; 'audio_toolbox', 'Audio Toolbox'; ...
      'optimization_toolbox', 'Optimization Toolbox'; 'distrib_computing_toolbox', 'Parallel Computing Toolbox'; 'image_toolbox', 'Image Processing Toolbox'};
d.toolboxes = cell(1, size(tb,1));  d.licensed = false(1, size(tb,1));
for i = 1:size(tb,1)
    d.toolboxes{i} = tb{i,2};
    d.licensed(i) = logical(license('test', tb{i,1}));
end
d.pool = false;
d.javaVersion = char(java.lang.System.getProperty('java.version'));
d.requiredForThisApp = struct('signal', 'octave-band filtering (butter, zp2sos) in audio analysis', 'audio', 'NOT required: octave filters are a custom Butterworth bank');
end
