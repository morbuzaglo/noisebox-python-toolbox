function lat = nb_lateral(obs, blockIdx, Sxyz, Rxyz, dem)
%NB_LATERAL Laterally diffracted paths around the vertical edges of obstacles.
%   lat = NB_LATERAL(obs, blockIdx, Sxyz, Rxyz, dem), ISO 9613-2:2024 7.4.3.
%     obs       cell array of ALL obstacles (see nb_obstacles)
%     blockIdx  indices of obstacles that block the direct line of sight
%     Sxyz,Rxyz [x y z] with ABSOLUTE elevation, metres
%   Construction (printed p. 19; ISO/TR 17534-3 cl. 5.2): in the LATERAL
%   plane through S and R perpendicular to the vertical plane a rubber-band
%   polygon is pulled around the cross-sections of the obstacles in that
%   plane. Coordinates in the plane: u along S->R (3D), v along the
%   horizontal normal n.
%   * The plane rises (or falls) from S to R, so it only cuts an obstacle
%     where the plane height is below the roof: the plan footprint is
%     CLIPPED to the half-plane where plane height <= top. The supporting
%     points are the vertices of the clipped footprint, including the new
%     points where the plane crosses the roof level (reproduces the ray
%     geometry of ISO/TR 17534-3 T12 and T15).
%   * The path starts with the obstacles that block the direct ray. Any
%     other obstacle that the taut string would cut through is added and the
%     string is pulled again, until the path is free (reproduces T17: a
%     building beside the direct ray still bends the left path).
%   Two paths: v > 0 (left) and v < 0 (right). Returns lat.side(1:2) with
%   valid, z, dss, dsr, e, edges (3D points), maxv, nObstacles. z is
%   POSITIVE for lateral paths (note under Fig. 12). Relevance rules
%   (factor 8, elevated ground) are applied by the caller.
%   Limitation: hull-based; exact for convex cross-sections, and for
%   several obstacles where the left/right passage is the shortest path.
%   Concave footprints with courtyards are not handled.
d3 = Rxyz - Sxyz;  d = norm(d3);
pd = d3(1:2);  npd = norm(pd);
empty = struct('valid', false, 'z', [], 'dss', [], 'dsr', [], 'e', 0, 'edges', zeros(0,3), 'maxv', 0, 'nObstacles', 0);
lat.side = [empty, empty];
if npd < 1e-9 || isempty(blockIdx), return; end
e3 = d3 / d;
n3 = [-pd(2), pd(1), 0] / npd;
Sxy = Sxyz(1:2);
tplane = @(P) Sxyz(3) + (((P(:,1)-Sxy(1))*pd(1) + (P(:,2)-Sxy(2))*pd(2)) / (npd^2)) * (Rxyz(3) - Sxyz(3));

% cross-section of every obstacle in the lateral plane: rows [u v x y t]
N = numel(obs);
XS = cell(1, N);
for k = 1:N
    o = obs{k};
    V = clipToRoof([o.x(:), o.y(:)], o.top, tplane, numel(o.x) == 2);
    rows = zeros(0,5);
    for q = 1:size(V,1)
        x = V(q,1);  y = V(q,2);  t = tplane([x y]);
        g = nb_dem_sample(dem, x, y);  if isnan(g), g = -Inf; end
        if t < g - 1e-9, continue; end                % plane below the ground there
        rel = [x y t] - Sxyz;
        rows(end+1,:) = [dot(rel, e3), dot(rel, n3), x, y, t]; %#ok<AGROW>
    end
    XS{k} = rows;
end

sgn = [1, -1];
for si = 1:2
    inc = false(1, N);  inc(blockIdx) = true;
    for iter = 1:N + 1
        Q = zeros(0,5);
        for k = find(inc)
            r = XS{k};
            if isempty(r), continue; end
            Q = [Q; r(r(:,1) > 1e-9 & r(:,1) < d - 1e-9 & sgn(si)*r(:,2) > 1e-9, :)]; %#ok<AGROW>
        end
        if isempty(Q), break; end
        [~, ord] = sort(Q(:,1));  Q = Q(ord,:);
        pts = [0 0; Q(:,1), sgn(si)*Q(:,2); d 0];
        hull = zeros(0,2);  keep = zeros(0,1);  idx = (1:size(pts,1))';
        for i = 1:size(pts,1)
            while size(hull,1) >= 2 && cr(hull(end-1,:), hull(end,:), pts(i,:)) >= -1e-9
                hull(end,:) = [];  keep(end) = [];
            end
            hull(end+1,:) = pts(i,:);  keep(end+1,1) = idx(i); %#ok<AGROW>
        end
        % is the string free? otherwise add the obstacle it cuts through and pull again
        added = false;
        for k = find(~inc)
            r = XS{k};
            if size(r,1) < 1, continue; end
            if pathHitsSection(hull, [r(:,1), sgn(si)*r(:,2)])
                inc(k) = true;  added = true;
            end
        end
        if ~added, break; end
    end
    if isempty(Q) || size(hull,1) < 3, continue; end
    inner = hull(2:end-1,:);  innerIdx = keep(2:end-1) - 1;   % rows of Q
    dss = hypot(inner(1,1), inner(1,2));
    dsr = hypot(d - inner(end,1), inner(end,2));
    ee = 0;
    if size(inner,1) > 1, ee = sum(hypot(diff(inner(:,1)), diff(inner(:,2)))); end
    lat.side(si).valid = true;
    lat.side(si).dss = dss;  lat.side(si).dsr = dsr;  lat.side(si).e = ee;
    lat.side(si).z = dss + dsr + ee - d;
    lat.side(si).edges = Q(innerIdx, 3:5);
    lat.side(si).maxv = max(abs(inner(:,2)));
    lat.side(si).nObstacles = sum(inc);
end
end

function tf = pathHitsSection(path, C)
% true if the polyline `path` (Nx2) crosses the cross-section C (Mx2 polygon or segment) or
% passes through its interior. Touching at a path vertex (a support point) does not count.
tf = false;
M = size(C,1);
if M == 1, return; end
nE = M;  if M == 2, nE = 1; end
for i = 1:size(path,1)-1
    a = path(i,:);  b = path(i+1,:);
    for j = 1:nE
        c = C(j,:);  dd = C(mod(j,M)+1,:);
        if segCross(a, b, c, dd), tf = true; return; end
    end
    if M >= 3
        m = (a + b)/2;
        if inpolygon(m(1), m(2), C(:,1), C(:,2)) && ~onBoundary(m, C), tf = true; return; end
    end
end
end

function tf = segCross(a, b, c, d)
% proper intersection (excluding shared end points within tolerance)
tol = 1e-9;
o1 = cr(a, b, c);  o2 = cr(a, b, d);  o3 = cr(c, d, a);  o4 = cr(c, d, b);
tf = (o1*o2 < -tol) && (o3*o4 < -tol);
end

function tf = onBoundary(p, C)
tf = false;  M = size(C,1);
for j = 1:M
    c = C(j,:);  d = C(mod(j,M)+1,:);
    if abs(cr(c, d, p)) < 1e-9 * max(1, norm(d - c)) && dot(p - c, p - d) <= 1e-9, tf = true; return; end
end
end

function V = clipToRoof(V, top, tplane, isSegment)
% Keep the part of the footprint where the lateral plane is not above the roof:
% h(P) = top - plane height(P) >= 0 (Sutherland-Hodgman against a linear function).
h = @(Pm) top - tplane(Pm);
if isSegment
    h1 = h(V(1,:));  h2 = h(V(2,:));
    if h1 >= 0 && h2 >= 0, return; end
    if h1 < 0 && h2 < 0, V = zeros(0,2); return; end
    a = h1/(h1 - h2);  X = V(1,:) + a*(V(2,:) - V(1,:));
    if h1 >= 0, V = [V(1,:); X]; else, V = [X; V(2,:)]; end
    return
end
out = zeros(0,2);
n = size(V,1);
for i = 1:n
    A = V(i,:);  B = V(mod(i,n)+1,:);
    hA = h(A);  hB = h(B);
    if hA >= 0
        out(end+1,:) = A; %#ok<AGROW>
        if hB < 0, out(end+1,:) = A + (hA/(hA-hB))*(B-A); end %#ok<AGROW>
    elseif hB >= 0
        out(end+1,:) = A + (hA/(hA-hB))*(B-A); %#ok<AGROW>
    end
end
V = out;
end

function c = cr(a, b, p)
c = (b(1)-a(1))*(p(2)-a(2)) - (b(2)-a(2))*(p(1)-a(1));
end
