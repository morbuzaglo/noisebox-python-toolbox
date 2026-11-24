function [A, alpha] = nb_aatm(d, T_C, RH, p_kPa, f)
%NB_AATM Atmospheric absorption per ISO 9613-2:2024 cl. 7.2, Formula (9).
%   [A, alpha] = NB_AATM(d, T_C, RH, p_kPa)        all 8 octave bands
%   [A, alpha] = NB_AATM(d, T_C, RH, p_kPa, f)     explicit frequencies, Hz
%     d      distance, m (true 3D source-receiver distance)
%     T_C    air temperature, deg C
%     RH     relative humidity, percent (0 < RH <= 100)
%     p_kPa  ambient pressure, kPa
%   alpha is in dB/km; A = alpha*d/1000 in dB.
%
%   Default frequencies are the EXACT base-10 centre frequencies, as
%   required by ISO 9613-2:2024 cl. 7.2 (ISO 9613-1:1993 Formula (6) with
%   exact centre frequencies). The coefficient uses the pure-tone
%   expressions of ISO 9613-1:1993 Formulae (2)-(5) (relaxation
%   frequencies of O2 and N2). Equation numbers: confirm on the 9613-1 scan.
if nargin < 5, b = nb_bands(); f = b.fexact; end
if RH <= 0 || RH > 100, error('nb:aatm:rh', 'RH must be in (0,100] percent.'); end
if p_kPa <= 0,          error('nb:aatm:p',  'Pressure must be > 0.'); end
if any(d(:) < 0),       error('nb:aatm:d',  'Distance must be >= 0.'); end
pr = 101.325;  T0 = 293.15;  T01 = 273.16;
T  = T_C + 273.15;
C  = -6.8346*(T01/T)^1.261 + 4.6151;
h  = RH * 10^C / (p_kPa/pr);          % molar concentration of water vapour, %
frO = (p_kPa/pr) * (24 + 4.04e4*h*(0.02+h)/(0.391+h));
frN = (p_kPa/pr) * (T/T0)^(-1/2) * (9 + 280*h*exp(-4.170*((T/T0)^(-1/3) - 1)));
alpha_m = 8.686 .* f.^2 .* ( 1.84e-11*(p_kPa/pr)^(-1)*(T/T0)^(1/2) ...
        + (T/T0)^(-5/2) .* ( 0.01275*exp(-2239.1/T) ./ (frO + f.^2./frO) ...
                           + 0.1068 *exp(-3352/T)   ./ (frN + f.^2./frN) ) );
alpha = alpha_m * 1000;               % dB/km
A = alpha .* d / 1000;
end
