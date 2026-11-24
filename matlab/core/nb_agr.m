function r = nb_agr(Gs, Gm, Gr, hs, hr, dp, mode)
%NB_AGR Ground attenuation, general method.
%   r = NB_AGR(Gs, Gm, Gr, hs, hr, dp [, mode])
%     Gs, Gm, Gr  ground factors of source, middle, receiver region, 0..1
%     hs, hr      source / receiver height ABOVE LOCAL GROUND, m
%     dp          source-receiver distance projected on the ground plane, m
%     mode        'iso2024' (default) or 'iso1996'
%   Returns struct with 1x8 fields As, Ar, Am, Agr and scalar Kgeo, q.
%
%   iso2024 (cl. 7.3.1, PDF pages of standard_iso_9613-2_2024.pdf):
%     Formula (11), (12), (13) : printed p. 10 (PDF p. 18)
%     Table 3, a'..d', q        : printed p. 11 (PDF p. 19)
%     A_gr = -10 lg[1 + (10^(-A'/10) - 1) K_geo]
%   iso1996 (ISO 9613-2:1996, as used by the ISO/TR 17534-3 benchmarks):
%     A_gr = A_s + A_r + A_m (no K_geo factor), same Table 3 expressions.
%   Agr may be NEGATIVE; it is never clamped to zero here.
%   Combination of several ground sections (Formula 10) is done by
%   nb_ground_factors.
if nargin < 7, mode = 'iso2024'; end
if ~any(strcmp(mode, {'iso2024','iso1996'}))
    error('nb:agr:mode', 'mode must be iso2024 or iso1996.');
end
if any([Gs Gm Gr] < 0) || any([Gs Gm Gr] > 1)
    error('nb:agr:G', 'Ground factors must lie in [0,1].');
end
if hs < 0 || hr < 0, error('nb:agr:h', 'Heights above ground must be >= 0.'); end
if dp <= 0,          error('nb:agr:dp', 'dp must be > 0.'); end

r.As = regionTerm(Gs, hs, dp);
r.Ar = regionTerm(Gr, hr, dp);

if dp <= 30*(hs + hr)
    q = 0;
else
    q = 1 - 30*(hs + hr)/dp;
end
r.q  = q;
r.Am = [-3*q, -3*q*(1 - Gm)*ones(1,7)];

Aprime = r.As + r.Ar + r.Am;                                   % Formula (12)
r.Kgeo = (dp^2 + (hs - hr)^2) / (dp^2 + (hs + hr)^2);          % Formula (13)
if strcmp(mode, 'iso1996')
    r.Agr = Aprime;
else
    r.Agr = -10*log10(1 + (10.^(-Aprime/10) - 1) * r.Kgeo);    % Formula (11)
end
r.mode = mode;
end

function A = regionTerm(G, h, dp)
% Table 3, columns A_S or A_R (nominal 63..8000 Hz).
e50 = 1 - exp(-dp/50);
a = 1.5 + 3.0*exp(-0.12*(h-5)^2)*e50 + 5.7*exp(-0.09*h^2)*(1 - exp(-2.8e-6*dp^2));
b = 1.5 + 8.6*exp(-0.09*h^2)*e50;
c = 1.5 + 14.0*exp(-0.46*h^2)*e50;
d = 1.5 + 5.0*exp(-0.9*h^2)*e50;
A = [-1.5, -1.5 + G*a, -1.5 + G*b, -1.5 + G*c, -1.5 + G*d, ...
     -1.5*(1-G)*ones(1,3)];
end
