function [A, alpha] = nb_aatm_1996(d, T_C, RH)
%NB_AATM_1996 Atmospheric absorption as tabulated in ISO 9613-2:1996 Table 2.
%   [A, alpha] = NB_AATM_1996(d, T_C, RH)
%   ISO 9613-2:1996 gives alpha (dB/km) ROUNDED to one decimal at the NOMINAL
%   band centre frequencies for a few weather conditions. Only the
%   condition used by the ISO/TR 17534-3 benchmarks is tabulated here:
%       20 deg C, 70 % RH : 0.1 0.3 1.1 2.8 5.0 9.0 22.9 76.6
%   (the same values are printed as "-atm (20 deg, 70 %)" in ISO/TR 17534-3
%   Tables 4-67). Any other condition errors instead of being guessed; use
%   the 2024 mode (ISO 9613-1 formulas) for general weather.
%   A = alpha * d / 1000 dB.
if abs(T_C - 20) > 1e-9 || abs(RH - 70) > 1e-9
    error('nb:aatm1996:condition', ...
        'ISO 9613-2:1996 mode tabulates only 20 degC / 70 %% RH here (requested %.1f degC, %.0f %%).', T_C, RH);
end
alpha = [0.1 0.3 1.1 2.8 5.0 9.0 22.9 76.6];
A = alpha * d / 1000;
end
