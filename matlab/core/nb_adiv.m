function A = nb_adiv(d)
%NB_ADIV Geometrical divergence, point source, free field.
%   A = NB_ADIV(d) = 20*log10(d/d0) + 11 dB, d0 = 1 m, d in metres, where
%   d is the TRUE 3D source-to-receiver distance. Same value in all bands.
%   Source: ISO 9613-2:2024 cl. 7.1, Formula (8) (printed p. 8).
%   The +11 dB corresponds to radiation into a full sphere relative to
%   L_W; a ground reflection is handled by A_gr and must not add +3 dB.
if any(d(:) <= 0) || any(~isfinite(d(:)))
    error('nb:adiv:distance', 'Distance must be finite and > 0 m.');
end
A = 20*log10(d/1) + 11;
end
