function out = run_audio_analysis(c)
%RUN_AUDIO_ANALYSIS Recording interval -> octave-band SPL -> optional background
%   subtraction -> apparent L_W. Stable entry point for the backend.
%   c.file       path of a WAV file (written by the backend under a random name)
%   c.channel    1-based channel (default 1)
%   c.start, c.stop   interval, seconds
%   c.paPerUnit  calibration [Pa per digital unit] or [] (uncalibrated)
%   c.background optional struct file, channel, start, stop (same calibration)
%   c.estimate   optional struct geometry g (hs, hm, dp, dh), G, atm, Dc, srcDim
%   Without calibration the levels are relative: no L_W is estimated and
%   out.absolute = false (absolute claims are blocked, not approximated).
if ~isfield(c,'channel') || isempty(c.channel), c.channel = 1; end
if ~isfield(c,'paPerUnit'), c.paPerUnit = []; end
[x, fs] = audioread(c.file);
if c.channel > size(x,2), error('nb:audio:channel', 'Channel %d does not exist (file has %d).', c.channel, size(x,2)); end
x = x(:, c.channel);
i0 = max(1, round(c.start*fs) + 1);  i1 = min(numel(x), round(c.stop*fs));
calInfo = [];
if isfield(c, 'calibrator') && ~isempty(c.calibrator)
    cal = c.calibrator;
    [xc, fsc] = audioread(cal.file);
    if fsc ~= fs, error('nb:audio:fs', 'Calibrator and signal recordings must have the same sample rate.'); end
    xc = xc(:, 1);
    calInfo = nb_calibrate(xc, fsc, max(1, round(cal.start*fsc) + 1), min(numel(xc), round(cal.stop*fsc)), cal.level, cal.freq);
    c.paPerUnit = calInfo.paPerUnit;
end
sig = nb_octave_spl(x, fs, i0, i1, c.paPerUnit);
if ~isempty(calInfo), out.calibration = calInfo; end
out.signal = sig;
out.paPerUnit = c.paPerUnit;
out.absolute = sig.absolute;
out.L = sig.L;
out.warnings = sig.warnings;
out.fingerprint = nb_fingerprint();
Lused = sig.L;
if isfield(c, 'background') && ~isempty(c.background)
    bg = c.background;
    if ~isfield(bg,'channel') || isempty(bg.channel), bg.channel = 1; end
    [xb, fsb] = audioread(bg.file);
    if fsb ~= fs, error('nb:audio:fs', 'Background and signal recordings must have the same sample rate.'); end
    xb = xb(:, bg.channel);
    j0 = max(1, round(bg.start*fs) + 1);  j1 = min(numel(xb), round(bg.stop*fs));
    bgr = nb_octave_spl(xb, fs, j0, j1, c.paPerUnit);
    sub = nb_background_subtract(sig.L, bgr.L);
    out.background = bgr;  out.subtraction = sub;
    out.warnings = [out.warnings, sub.warnings];
    Lused = sub.Lcorr;
end
out.Lused = Lused;
if isfield(c, 'estimate') && ~isempty(c.estimate)
    if ~sig.absolute
        error('nb:audio:uncalibrated', ['No calibration: absolute SPL and L_W cannot be derived from this recording. ' ...
            'Provide a calibrator recording or a Pa-per-unit sensitivity, or enter L_W manually.']);
    end
    e = c.estimate;
    if ~isfield(e,'Dc'), e.Dc = []; end
    if ~isfield(e,'srcDim'), e.srcDim = []; end
    out.lw = nb_estimate_lw(Lused, e.g, e.G, e.atm, e.Dc, e.srcDim);
end
end
