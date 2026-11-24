function r = nb_octave_spl(x, fs, i0, i1, paPerUnit)
%NB_OCTAVE_SPL Octave-band RMS levels of a recording interval.
%   r = NB_OCTAVE_SPL(x, fs, i0, i1, paPerUnit)
%     x          mono samples (digital units), the WHOLE recording so the
%                filters have settled before the interval (pre-roll)
%     fs         sample rate, Hz
%     i0, i1     first / last sample of the analysed interval (1-based)
%     paPerUnit  calibration: pascals per digital unit, or [] if unknown
%   Levels:
%     calibrated   L = 20 log10(p_rms / 20e-6), dB re 20 uPa (UNWEIGHTED)
%     uncalibrated L = 20 log10(rms) in dB re one digital RMS unit
%                  (relative only; r.absolute = false)
%   FILTER BANK: 6th-order Butterworth band-pass designed by nb_butter_sos
%   (base MATLAB, no toolbox), exact base-10 centre frequencies
%   fm = 1000*10^(0.3 n), edges fm*10^(+-0.15), causal sosfilt, 1 s
%   pre-roll. This is a CUSTOM filter bank: it has NOT been verified for
%   IEC 61260-1 class 1 or 2 conformance. Bands whose upper edge exceeds
%   Nyquist are NaN.
%   RMS is the plain mean-square over the interval (linear energy mean,
%   not an average of dB values).
b = nb_bands();
x = x(:);
n = numel(x);
if i0 < 1 || i1 > n || i1 <= i0, error('nb:octave:interval', 'Invalid analysis interval.'); end
r.fs = fs;  r.i0 = i0;  r.i1 = i1;  r.duration = (i1 - i0 + 1)/fs;
r.absolute = ~isempty(paPerUnit);
clipped = any(abs(x(i0:i1)) >= 0.9999);               % check digital samples before any scaling
if r.absolute
    if paPerUnit <= 0 || ~isfinite(paPerUnit), error('nb:octave:cal', 'paPerUnit must be > 0.'); end
    x = x * paPerUnit;  pref = 20e-6;  r.unit = 'dB re 20 uPa';
else
    pref = 1;  r.unit = 'dB re 1 digital RMS unit (UNCALIBRATED, relative only)';
end
pre = min(i0 - 1, round(1.0*fs));
seg = x(i0 - pre : i1);
r.preRollSeconds = pre/fs;
L = nan(1,8);  rms = nan(1,8);
w = {};
if r.duration < 1.0, w{end+1} = 'Interval shorter than 1 s: 63 Hz band level is unreliable.'; end
if pre < round(0.5*fs), w{end+1} = 'Less than 0.5 s of audio before the interval: filter start-up transient may bias low bands.'; end
if clipped, w{end+1} = 'Samples at digital full scale in the interval: possible clipping, levels are unreliable.'; end
for k = 1:8
    fm = b.fexact(k);  f1 = fm*10^(-0.15);  f2 = fm*10^(0.15);
    if f2 >= fs/2*0.98
        w{end+1} = sprintf('%d Hz band skipped: upper edge %.0f Hz is too close to Nyquist (%.0f Hz).', b.f(k), f2, fs/2); %#ok<AGROW>
        continue
    end
    sos = nb_butter_sos(3, [f1 f2]/(fs/2));
    y = sosfilt_(sos, seg);
    yy = y(pre+1:end);
    rms(k) = sqrt(mean(yy.^2));
    L(k) = 20*log10(rms(k)/pref);
end
r.L = L;  r.rms = rms;  r.f = b.f;  r.fexact = b.fexact;
r.broadband = nb_energy_sum(L(~isnan(L)));            % of the analysed bands only
r.bandsUsed = ~isnan(L);
r.filter = 'Butterworth 6th-order band-pass (custom, not IEC 61260-1 verified), exact base-10 centres';
r.warnings = w;
r.noteBroadband = 'Broadband is the energy sum of the analysed octave bands only (not the full audio spectrum).';
end

function y = sosfilt_(sos, x)
% cascade of second-order sections (direct form II transposed via filter)
g = 1;  y = x;
for s = 1:size(sos,1)
    y = filter(sos(s,1:3), sos(s,4:6), y);
end
y = y * g;
end
