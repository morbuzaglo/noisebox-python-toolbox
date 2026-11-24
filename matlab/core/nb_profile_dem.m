function [s, z, ok] = nb_profile_dem(dem, Sxy, Rxy)
%NB_PROFILE_DEM Terrain profile along the vertical plane through S and R.
%   [s, z, ok] = NB_PROFILE_DEM(dem, Sxy, Rxy)
%     Sxy, Rxy  [x y] map coordinates, metres
%   s  distance along the line from S, m (s(1) = 0, s(end) = |SR|)
%   z  DEM elevation at each sample
%   ok false if any sample is NaN / outside the grid (no valid profile).
%   VERIFIED sampling (ray-grid traversal): the sample set contains every
%   point where the line crosses a grid line x = x0 + k cs or y = y0 + k cs,
%   plus regular samples at most cs/2 apart. Along the line the bilinear
%   surface is smooth inside a cell and can only kink on cell edges, so
%   crests that sit on a grid line are hit exactly. No smoothing or gap
%   filling is applied.
L = hypot(Rxy(1)-Sxy(1), Rxy(2)-Sxy(2));
if L <= 0
    s = 0; z = nb_dem_sample(dem, Sxy(1), Sxy(2)); ok = ~isnan(z); return
end
dx = Rxy(1) - Sxy(1);  dy = Rxy(2) - Sxy(2);
t = linspace(0, 1, max(2, ceil(L / (dem.cs/2)) + 1));
if dx ~= 0
    kx = ceil((min(Sxy(1),Rxy(1)) - dem.x0)/dem.cs) : floor((max(Sxy(1),Rxy(1)) - dem.x0)/dem.cs);
    t = [t, ((dem.x0 + kx*dem.cs) - Sxy(1)) / dx];
end
if dy ~= 0
    ky = ceil((min(Sxy(2),Rxy(2)) - dem.y0)/dem.cs) : floor((max(Sxy(2),Rxy(2)) - dem.y0)/dem.cs);
    t = [t, ((dem.y0 + ky*dem.cs) - Sxy(2)) / dy];
end
t = t(t >= 0 & t <= 1);
t = unique(round(t, 12));
if t(1) > 0, t = [0, t]; end
if t(end) < 1, t = [t, 1]; end
s = t * L;
X = Sxy(1) + t*dx;
Y = Sxy(2) + t*dy;
z = nb_dem_sample(dem, X, Y);
ok = ~any(isnan(z));
end
