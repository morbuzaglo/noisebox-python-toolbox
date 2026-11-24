function g = nb_geom2d(xp, zp, S, R)
%NB_GEOM2D Diffraction geometry in a vertical X-Z plane, ISO 9613-2:2024 cl. 7.4.1.
%   g = NB_GEOM2D(xp, zp, S, R)
%     xp, zp  terrain profile vertices, metres, xp strictly increasing
%             (piecewise linear terrain; elevation zp is ABSOLUTE)
%     S, R    [x z] of source and receiver, ABSOLUTE elevation, S(1) < R(1)
%   Output struct g:
%     kind    'none'         no relevant edge (flat or open terrain)
%             'blocked'      line of sight blocked: taut-string path over
%                            the upper convex hull, z > 0   (Formula 22)
%             'clear_crest'  line of sight clear but real crests lie below
%                            it: z = max(z_n) < 0           (Formula 23)
%     edges   nx2 diffracting edges used (empty for 'none')
%     path    mx2 polyline S -> edges -> R (for plotting)
%     z, dss, dsr, e, d   metres (empty z for 'none')
%     hs, hr  heights above LOCAL ground, m ; dp horizontal distance, m
%     dh      ground elevation difference receiver - source, m
%   Rules implemented:
%     - Edges are real terrain corners only. Collinear vertices (flat or
%       constant-slope ground) never create an edge.
%     - When blocked, the path is the shortest path above the terrain
%       (upper convex hull of S, intermediate terrain vertices, R); the
%       first and last hull vertices give dss and dsr, e is the length
%       between them.
%     - When clear, each convex terrain corner (slope decreases) below the
%       line of sight gives z_n = -(|SE|+|ER|-d) (negative sign, printed
%       p. 17) and z is the maximum z_n; e = 0 (single edge), per the
%       text under Formula (23).
%   Not handled here: ground reflections on terrain slopes beyond A_gr,
%   lateral paths (3D module), obstacle footprints.
xp = xp(:)'; zp = zp(:)';
if numel(xp) ~= numel(zp) || numel(xp) < 2 || any(diff(xp) <= 0)
    error('nb:geom2d:profile', 'Profile needs >= 2 vertices with strictly increasing x.');
end
if ~(S(1) < R(1)), error('nb:geom2d:order', 'Source must be left of receiver (S(1) < R(1)).'); end
if S(1) < xp(1) || R(1) > xp(end)
    error('nb:geom2d:domain', 'Source or receiver lies outside the terrain profile.');
end
tol = 1e-9;
gS = interp1(xp, zp, S(1));  gR = interp1(xp, zp, R(1));
if S(2) < gS - tol || R(2) < gR - tol
    error('nb:geom2d:underground', 'Source or receiver is below the terrain surface.');
end
d = hypot(R(1)-S(1), R(2)-S(2));
if d <= 0, error('nb:geom2d:coincident', 'Source and receiver coincide.'); end

g.hs = S(2) - gS;  g.hr = R(2) - gR;  g.dp = R(1) - S(1);  g.dh = gR - gS;  g.d = d;
g.kind = 'none';  g.edges = zeros(0,2);  g.path = [S; R];
g.z = [];  g.dss = [];  g.dsr = [];  g.e = 0;  g.zn = [];

inside = xp > S(1) + tol & xp < R(1) - tol;
V = [xp(inside)', zp(inside)'];                % terrain vertices strictly between S and R

% ---- upper convex hull of S, V, R (shortest path above terrain)
P = [S; V; R];
hull = zeros(0,2);
for i = 1:size(P,1)
    while size(hull,1) >= 2 && cross2(hull(end-1,:), hull(end,:), P(i,:)) >= -tol
        hull(end,:) = [];
    end
    hull(end+1,:) = P(i,:); %#ok<AGROW>
end
inner = hull(2:end-1,:);

if ~isempty(inner)
    g.kind = 'blocked';
    g.edges = inner;  g.path = hull;
    g.dss = hypot(inner(1,1)-S(1), inner(1,2)-S(2));
    g.dsr = hypot(R(1)-inner(end,1), R(2)-inner(end,2));
    if size(inner,1) > 1
        g.e = sum(hypot(diff(inner(:,1)), diff(inner(:,2))));
    end
    g.z = g.dss + g.dsr + g.e - d;                                    % Formula (22)
    return
end

% ---- line of sight clear: convex terrain corners below it
k = find(inside);
best = -Inf; bi = 0;
for j = k
    if j <= 1 || j >= numel(xp), continue; end
    sl = (zp(j) - zp(j-1)) / (xp(j) - xp(j-1));
    sr = (zp(j+1) - zp(j)) / (xp(j+1) - xp(j));
    if sl - sr > tol                           % real convex corner (crest)
        E = [xp(j) zp(j)];
        % z_n is the NEGATIVE path length difference (printed p. 17): the
        % detour over the edge is never shorter than d, so the sign is flipped.
        zn = -(hypot(E(1)-S(1), E(2)-S(2)) + hypot(R(1)-E(1), R(2)-E(2)) - d);
        if zn > best, best = zn; bi = j; end
    end
end
if bi > 0
    E = [xp(bi) zp(bi)];
    g.kind = 'clear_crest';  g.edges = E;  g.path = [S; E; R];
    g.dss = hypot(E(1)-S(1), E(2)-S(2));  g.dsr = hypot(R(1)-E(1), R(2)-E(2));
    g.z = best;                                                       % Formula (23), e = 0
end
end

function c = cross2(a, b, p)
c = (b(1)-a(1))*(p(2)-a(2)) - (b(2)-a(2))*(p(1)-a(1));
end
