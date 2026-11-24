function r = nb_estimate_lw(Lp, g, G, atm, Dc, srcDim)
%NB_ESTIMATE_LW Apparent sound power level from ONE microphone measurement.
%   r = NB_ESTIMATE_LW(Lp, g, G, atm, Dc, srcDim)
%     Lp   1x8 CALIBRATED unweighted octave-band SPL at the microphone, dB
%          re 20 uPa (NaN bands stay NaN)
%     g    hs, hm (heights above local ground, m), dp (horizontal source-
%          microphone distance, m), dh (ground elevation difference, m)
%     G    Gs, Gm, Gr ground factors   atm  T_C, RH, p_kPa
%     Dc   1x8 directivity correction toward the microphone (default 0)
%     srcDim largest source dimension, m (optional, for the near-field check)
%   Inverts ISO 9613-2:2024 Formula (3):  L_W = L_p - D_c + A, with
%   A = A_div + A_atm + A_gr from the same modules as the forward model.
%   The result is an APPARENT L_W: one microphone in one direction cannot
%   separate source power from directivity or from the ground / reflection
%   conditions of the measurement site.
if nargin < 5 || isempty(Dc), Dc = zeros(1,8); end
if nargin < 6, srcDim = []; end
d3 = (g.hm - g.hs) + g.dh;
d  = sqrt(g.dp^2 + d3^2);
Adiv = nb_adiv(d) * ones(1,8);
Aatm = nb_aatm(d, atm.T_C, atm.RH, atm.p_kPa);
gg = nb_agr(G.Gs, G.Gm, G.Gr, g.hs, g.hm, g.dp);
A = Adiv + Aatm + gg.Agr;
r.Lw = Lp - Dc + A;
r.A = A;  r.Adiv = Adiv;  r.Aatm = Aatm;  r.Agr = gg.Agr;  r.d = d;
w = {};
w{end+1} = 'Apparent L_W from one microphone in one direction: true sound power and directivity cannot be separated. Multi-microphone characterization (e.g. ISO 3744 surface) is recommended.';
if ~isempty(srcDim) && d < 2*srcDim
    w{end+1} = sprintf('Microphone distance %.1f m is less than 2 x the largest source dimension (%.1f m): near-field, the point-source model is not valid.', d, srcDim);
end
if g.dp < 3*(g.hs + g.hm)
    w{end+1} = 'Short distance relative to heights: the ground term A_gr is sensitive to the assumed ground factors.';
end
if any(isnan(Lp)), w{end+1} = 'Some bands have no valid level (background or filter limits); their L_W is NaN.'; end
r.warnings = w;
r.model = 'ISO 9613-2:2024 Formula (3) inverted, omnidirectional point source above ground';
end
