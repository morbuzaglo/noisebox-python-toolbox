function r = nb_calibrate(x, fs, i0, i1, level_dB, f_cal)
%NB_CALIBRATE Pascals per digital unit from a recorded acoustic calibrator.
%   r = NB_CALIBRATE(x, fs, i0, i1, level_dB, f_cal)
%     x, fs      mono calibrator recording (digital units) and sample rate
%     i0, i1     interval containing the steady calibrator tone
%     level_dB   calibrator level, dB re 20 uPa (e.g. 94 or 114)
%     f_cal      calibrator frequency, Hz (1000 typical, 250 for some)
%   The tone RMS is measured after a narrow band-pass (+-10 % around f_cal)
%   to reject room noise, then paPerUnit = p_cal / rms_tone with
%   p_cal = 20e-6 * 10^(level/20). The recording must contain ONLY the
%   calibrator tone at the microphone used for the measurement, with the
%   same gain settings. Checks: tone-to-total SNR and clipping.
x = x(:);
if i0 < 1 || i1 > numel(x) || i1 - i0 < round(0.5*fs), error('nb:calibrate:interval', 'Calibrator interval must be at least 0.5 s.'); end
if f_cal >= fs/2*0.9, error('nb:calibrate:fcal', 'Calibrator frequency too close to Nyquist.'); end
seg = x(i0:i1);
sos = nb_butter_sos(2, [0.9 1.1]*f_cal/(fs/2));
y = seg;
for s = 1:size(sos,1), y = filter(sos(s,1:3), sos(s,4:6), y); end
y = y(round(0.2*numel(y)):end);                          % drop filter start-up
rmsTone = sqrt(mean(y.^2));
rmsAll = sqrt(mean(seg.^2));
if rmsTone <= 0, error('nb:calibrate:silent', 'No calibrator tone found at %.0f Hz.', f_cal); end
pcal = 20e-6 * 10^(level_dB/20);
r.paPerUnit = pcal / rmsTone;
r.rmsTone = rmsTone;  r.rmsTotal = rmsAll;
r.toneToTotal_dB = 20*log10(rmsTone / rmsAll);
r.warnings = {};
if r.toneToTotal_dB < -3, r.warnings{end+1} = 'The recording is dominated by something other than the calibrator tone; the calibration may be wrong.'; end
if any(abs(seg) >= 0.9999), r.warnings{end+1} = 'Calibrator recording clips.'; end
r.note = sprintf('Calibrated from a %.1f dB tone at %.0f Hz. Valid only for the same microphone and gain settings.', level_dB, f_cal);
end
