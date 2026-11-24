function z = nb_dem_sample(dem, X, Y)
%NB_DEM_SAMPLE Bilinear elevation from a regular DEM, NaN if unknown.
%   dem.x0, dem.y0   coordinates of the CENTRE of cell (1,1), metres
%   dem.cs           cell size, metres (square cells, projected CRS)
%   dem.Z            NY x NX elevations, Z(iy,ix), y increasing with iy
%                    (NaN = no data)
%   z = NB_DEM_SAMPLE(dem, X, Y) with X, Y same size. Points outside the
%   grid, or whose four surrounding cells include a NaN, return NaN: an
%   elevation is never invented.
[NY, NX] = size(dem.Z);
fx = (X - dem.x0) / dem.cs + 1;
fy = (Y - dem.y0) / dem.cs + 1;
z = nan(size(X));
inb = fx >= 1 & fx <= NX & fy >= 1 & fy <= NY;
ix = min(max(floor(fx), 1), NX-1);
iy = min(max(floor(fy), 1), NY-1);
tx = fx - ix;  ty = fy - iy;
idx = @(r, c) r + (c-1)*NY;
z00 = dem.Z(idx(iy,   ix  ));
z10 = dem.Z(idx(iy,   ix+1));
z01 = dem.Z(idx(iy+1, ix  ));
z11 = dem.Z(idx(iy+1, ix+1));
v = (1-tx).*(1-ty).*z00 + tx.*(1-ty).*z10 + (1-tx).*ty.*z01 + tx.*ty.*z11;
z(inb) = v(inb);
end
