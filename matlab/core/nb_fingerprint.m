function fp = nb_fingerprint()
%NB_FINGERPRINT MD5 and mtime of every .m file in this folder.
%   Returns a SCALAR struct (the Engine API cannot return struct arrays):
%     fp.file     1xN cell of file names
%     fp.md5      1xN cell of lower-case hex MD5 of the file bytes
%     fp.modified 1xN double MATLAB datenum of last modification
%   Attached to every result so a saved case records exactly which code
%   produced it.
here = fileparts(mfilename('fullpath'));
L = dir(fullfile(here, '*.m'));
n = numel(L);
fp.file = cell(1, n);  fp.md5 = cell(1, n);  fp.modified = zeros(1, n);
md = java.security.MessageDigest.getInstance('MD5');
for i = 1:n
    p = fullfile(here, L(i).name);
    fid = fopen(p, 'r'); bytes = fread(fid, Inf, '*uint8'); fclose(fid);
    md.reset(); md.update(bytes);
    h = typecast(md.digest(), 'uint8');
    fp.file{i} = L(i).name;
    fp.md5{i}  = lower(reshape(dec2hex(h, 2)', 1, []));
    fp.modified(i) = L(i).datenum;
end
end
