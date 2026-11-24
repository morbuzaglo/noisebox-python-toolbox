function r = nb_agr_simplified(hm, d, dp, hs, hr)
%NB_AGR_SIMPLIFIED Alternative A-weighted ground method, ISO 9613-2:2024 cl. 7.3.2.
%   r = NB_AGR_SIMPLIFIED(hm, d, dp, hs, hr)
%     hm  mean height of the propagation path above the ground, m
%         (hm = F/dp, Figure 5 printed p. 13; for flat ground (hs+hr)/2)
%     d   source-receiver distance, m
%     dp, hs, hr  for the directivity term D_Omega
%   Returns r.Agr (dB, one value for ALL bands, negative values replaced by
%   zero as the standard requires for this method) and r.DOmega, dB.
%     A_gr = 4.8 - (2 hm / d) (17 + 300/d)   >= 0           Formula (14)
%     D_Omega = 10 lg(1 + K_geo)                             Formula (15)
%   Source: printed pp. 12-13 (PDF pp. 20-21); the same expressions were
%   Formulae (10) and (11) in ISO 9613-2:1996. The method is defined for
%   A-WEIGHTED levels: it is not frequency dependent.
if hm < 0 || d <= 0, error('nb:agrsimp:input', 'hm must be >= 0 and d > 0.'); end
Agr = 4.8 - (2*hm/d) * (17 + 300/d);
r.Agr = max(Agr, 0);
r.AgrRaw = Agr;
r.Kgeo = (dp^2 + (hs - hr)^2) / (dp^2 + (hs + hr)^2);
r.DOmega = 10*log10(1 + r.Kgeo);
end
