function r = nb_enclosure_surfaces(Lw_in, surfaces, S_open)
%NB_ENCLOSURE_SURFACES Enclosure made of several surfaces (walls, roof), each with its own material and interior absorption.
%   r = NB_ENCLOSURE_SURFACES(Lw_in, surfaces, S_open)
%     Lw_in     1x8 sound power of the bare source, dB re 1 pW
%     surfaces  struct array, one element per radiating surface:
%                 name   char
%                 area   m^2 (> 0)
%                 mat    material struct, as nb_material('resolve', mat) (measured TL 1x8 or surface mass ...)
%                 alpha  1x8 interior absorption coefficient, 0..1 (NOT a dB value)
%     S_open    total area of openings, m^2 (default 0); it lies inside the surfaces' total area
%   Method (no new physics beyond area weighting; the enclosure equations are nb_enclosure.m, called unchanged):
%     S_total = sum(area_i)
%     A_in(f) = sum(alpha_i(f) * area_i)                     equivalent absorption area inside, per band
%     tau_c(f) = sum(area_i * 10^(-TL_i(f)/10)) / S_total
%     TL_c(f)  = -10 lg tau_c(f)                              composite panel TL, per band
%     then, for each band k, nb_enclosure(Lw_in, S_total, A_in(k), TL_c, S_open) and its band k is kept.
%   With ONE surface (or the same material and alpha on all of them) this equals nb_enclosure exactly.
%   ASSUMPTIONS (reported): those of nb_enclosure (diffuse interior field, no resonance / coincidence / near field)
%   and the floor is ground: it neither radiates nor absorbs in this model (conservative: less interior absorption).
n = numel(surfaces);
if n < 1, error('nb:enclosureSurfaces:none', 'An enclosure needs at least one surface.'); end
Sopen = 0;  if nargin >= 3 && ~isempty(S_open), Sopen = S_open; end
a = zeros(n,1);  TL = zeros(n,8);  al = zeros(n,8);  src = cell(n,1);  names = cell(n,1);  w = {};
for i = 1:n
    s = surfaces(i);
    names{i} = char(s.name);
    if ~(s.area > 0), error('nb:enclosureSurfaces:area', 'Surface "%s": area must be > 0 m^2.', names{i}); end
    a(i) = s.area;
    m = nb_material('resolve', s.mat);
    TL(i,:) = m.TL;  src{i} = m.source;
    for q = 1:numel(m.warnings), w{end+1} = sprintf('%s: %s', names{i}, m.warnings{q}); end %#ok<AGROW>
    validateattributes(s.alpha, {'numeric'}, {'vector','numel',8,'finite','real','>=',0,'<=',1});
    al(i,:) = s.alpha(:)';
end
S = sum(a);
TLc = -10*log10((a' * 10.^(-TL/10)) / S);          % 1x8
Ain = a' * al;                                      % 1x8
Lw_out = zeros(1,8);  Lp_in = zeros(1,8);  TLeff = zeros(1,8);  na = false(1,8);
for k = 1:8
    if Ain(k) <= 0
        error('nb:enclosureSurfaces:absorption', 'Interior absorption area is zero in band %d: give alpha > 0 on at least one surface.', k);
    end
    e = nb_enclosure(Lw_in, struct('S_total', S, 'A_in', Ain(k), 'mat', struct('TL', TLc), 'S_open', Sopen));
    Lw_out(k) = e.Lw_out(k);  Lp_in(k) = e.Lp_in(k);  TLeff(k) = e.TLeff(k);  na(k) = e.notApplicableBands(k);
end
r.Lw_in = Lw_in(:)';  r.Lw_out = Lw_out;  r.Lp_in = Lp_in;  r.TL = TLc;  r.TLeff = TLeff;
r.reduction = r.Lw_in - Lw_out;
r.notApplicableBands = na;
r.S_total = S;  r.A_in = Ain;  r.S_open = Sopen;
r.surfaceNames = names;  r.surfaceSource = src;  r.surfaceTL = TL;
if any(na)
    w{end+1} = 'In some bands L_W,out > L_W,in: interior absorption is too small for the diffuse-field model; result not applicable there.';
end
if Sopen > 0
    w{end+1} = sprintf('Openings (%.2f of %.2f m^2) limit the achievable reduction to about %.1f dB.', Sopen, S, -10*log10(Sopen/S));
end
w{end+1} = 'Rough engineering estimate: diffuse interior field, no resonance/coincidence/near-field effects; floor treated as ground.';
r.warnings = w;
r.model = 'EN ISO 15667-style diffuse-field enclosure model (nb_enclosure), composite of surfaces';
end
