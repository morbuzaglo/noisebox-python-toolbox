function C = nb_cmet(C0, hs, hr, dp)
%NB_CMET Long-term meteorological correction, ISO 9613-2:2024 cl. 8.
%   C = NB_CMET(C0, hs, hr, dp), dB, scalar for all bands.
%   Formula (31): C = 0 if dp <= 10(hs+hr)
%   Formula (32): C = C0*[1 - 10(hs+hr)/dp] otherwise.   (printed p. 24)
%   C0 depends on local wind and temperature-gradient statistics; the
%   standard says practical values range from 0 to about +5 dB. It is NOT
%   applied by default anywhere in this code base; the caller must request
%   a long-term level explicitly (L_AT(LT) = L_AT(DW) - C_met, Formula 7).
if C0 < 0, error('nb:cmet:C0', 'C0 must be >= 0 dB.'); end
if dp <= 10*(hs + hr)
    C = 0;
else
    C = C0 * (1 - 10*(hs + hr)/dp);
end
end
