function r = nb_abar(Dz_top, Dz_side1, Dz_side2, Agr, extra)
%NB_ABAR Combine top and lateral diffraction into A_bar, ISO 9613-2:2024.
%   r = NB_ABAR(Dz_top, Dz_side1, Dz_side2, Agr)
%     Dz_top, Dz_side1, Dz_side2 : 1x8 D_z of each path, or [] if the path
%       is not relevant (its summand is then 0).
%     Agr : 1x8 ground attenuation WITHOUT the barrier (cl. 7.3.1).
%   Per path (printed p. 14, Formulae 16 and 17):
%     top path, Agr > 0 : A = Dz - Agr    (16)
%     top path, Agr <= 0: A = Dz          (17)
%     lateral paths     : A = Dz          (17)
%   Each A is then floored at 0 (the ">0" in 16/17). Paths are combined
%   with Formula (25) (printed p. 20): A_bar = -10 lg(sum 10^(-0.1 A_i)),
%   floored at 0. NOTE: with all three paths present a path with A = 0
%   contributes a summand of 1, so the combined value is less than the
%   smallest single path, as the standard intends.
%   Lateral-path relevance (factor-8 rule, elevated-ground exclusion) is
%   decided by the geometry code, not here.
%   extra (optional, Mx8): additional diffraction paths that ISO 9613-2
%   does NOT prescribe (e.g. the path under a hanging screen). Each row is
%   combined like a lateral path (A = Dz, floored at 0). ENGINEERING
%   EXTENSION, reported separately by the caller.
if nargin < 5, extra = []; end
Atop = [];  As1 = [];  As2 = [];
if ~isempty(Dz_top)
    Atop = Dz_top;
    pos = Agr > 0;
    Atop(pos) = Dz_top(pos) - Agr(pos);
    Atop = max(Atop, 0);
end
if ~isempty(Dz_side1), As1 = max(Dz_side1, 0); end
if ~isempty(Dz_side2), As2 = max(Dz_side2, 0); end
S = zeros(1,8);
if ~isempty(Atop), S = S + 10.^(-0.1*Atop); end
if ~isempty(As1),  S = S + 10.^(-0.1*As1);  end
if ~isempty(As2),  S = S + 10.^(-0.1*As2);  end
for q = 1:size(extra, 1), S = S + 10.^(-0.1*max(extra(q,:), 0)); end
if isempty(Atop) && isempty(As1) && isempty(As2) && isempty(extra)
    Abar = zeros(1,8);
else
    Abar = max(-10*log10(S), 0);
end
r.Abar = Abar;  r.Abar_extra = extra;  r.Abar_top = Atop;  r.Abar_side1 = As1;  r.Abar_side2 = As2;
end
