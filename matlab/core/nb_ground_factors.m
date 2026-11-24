function gf = nb_ground_factors(areas, G0, Sxy, Rxy, hs, hr)
%NB_GROUND_FACTORS Ground factors of source, middle and receiver region.
%   gf = NB_GROUND_FACTORS(areas, G0, Sxy, Rxy, hs, hr)
%     areas  cell array of structs x, y (plan polygon vertices), G (0..1);
%            areas must not overlap
%     G0     ground factor of ground not covered by any area
%     hs,hr  source / receiver height above local ground, m
%   The path S-R is projected on the horizontal plane (length dp). Regions
%   (ISO 9613-2:2024 cl. 7.3.1, printed p. 9-10; Figure 3):
%     source region   [0, min(30 hs, dp)]
%     receiver region [dp - min(30 hr, dp), dp]
%     middle region   in between (empty when dp <= 30(hs+hr); Gm = 0)
%   Each region's factor is the length-weighted mean of the ground
%   factors along it, Formula (10): G = sum(G_n d_n) / sum(d_n).
%   Returns gf.Gs, gf.Gm, gf.Gr, gf.dp and the pieces (a, b, G) used.
dp = hypot(Rxy(1)-Sxy(1), Rxy(2)-Sxy(2));
if dp <= 0, error('nb:ground:dp', 'Source and receiver coincide in plan.'); end
bp = [0, dp];
for k = 1:numel(areas)
    a = areas{k};
    if any(a.G < 0) || any(a.G > 1), error('nb:ground:G', 'Area %d: G must lie in [0,1].', k); end
    iv = nb_obstacles('intervals', {struct('x', a.x(:), 'y', a.y(:), 'top', 0)}, Sxy, Rxy);
    bp = [bp, reshape(iv(:,1:2)'*dp, 1, [])]; %#ok<AGROW>
end
bp = unique(min(max(bp(:)', 0), dp));
Gp = zeros(1, numel(bp)-1);
for i = 1:numel(bp)-1
    m = (bp(i) + bp(i+1)) / 2;
    P = Sxy + (m/dp)*(Rxy - Sxy);
    Gp(i) = G0;
    for k = 1:numel(areas)
        if inpolygon(P(1), P(2), areas{k}.x(:), areas{k}.y(:)), Gp(i) = areas{k}.G; break; end
    end
end
sEnd = min(30*hs, dp);  rStart = max(dp - 30*hr, 0);
gf.Gs = regionMean(bp, Gp, 0, sEnd, G0);
gf.Gr = regionMean(bp, Gp, rStart, dp, G0);
if dp > 30*(hs + hr)
    gf.Gm = regionMean(bp, Gp, sEnd, rStart, G0);
else
    gf.Gm = 0;
end
gf.dp = dp;  gf.breaks = bp;  gf.pieceG = Gp;
gf.lengths = struct('s', sEnd, 'r', dp - rStart, 'm', max(rStart - sEnd, 0));
end

function G = regionMean(bp, Gp, r0, r1, G0)
if r1 <= r0, G = G0; return; end
num = 0;  den = 0;
for i = 1:numel(Gp)
    lo = max(bp(i), r0);  hi = min(bp(i+1), r1);
    if hi > lo, num = num + Gp(i)*(hi - lo);  den = den + (hi - lo); end
end
if den == 0, G = G0; else, G = num/den; end
end
