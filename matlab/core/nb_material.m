function varargout = nb_material(action, varargin)
%NB_MATERIAL Transmission-loss helpers for screens and enclosures.
%   m = nb_material('surfaceMass', rho_vol, thickness, solid)
%       surface mass density in kg/m^2 from VOLUME density (kg/m^3) times
%       thickness (m). Only valid for a homogeneous solid layer: solid must
%       be true, otherwise this errors (a fabric's bulk density is not its
%       surface mass).
%   TL = nb_material('massLaw', m, f, model)
%       model 'normal': TL = 20 log10(pi f m /(rho0 c)) = 20 log10(f m) - 42.4,
%                       rho0 c = 415 Pa s/m (normal incidence, limp mass law)
%       model 'field' : normal-incidence value minus 5 dB (rough field-
%                       incidence estimate)
%       ROUGH ENGINEERING ESTIMATE. Not valid for porous or flexible
%       textiles, below panel resonance or near coincidence. Floored at 0.
%   TLeff = nb_material('effectiveTL', TL, openness)
%       area-weighted transmission with an open fraction (porosity,
%       gaps): TLeff = -10 log10(open + (1-open) 10^(-TL/10)).
%   r = nb_material('resolve', mat)
%       mat: struct, any of surface_mass, volume_density, thickness, solid,
%       TL (1x8 measured), openness, tl_model. Returns r.TL (1x8), r.TLeff
%       (1x8), r.source ('measured' | 'mass-law'), r.confidence and
%       r.warnings (cellstr).
b = nb_bands();
switch action
    case 'surfaceMass'
        [rho, t, solid] = deal(varargin{1}, varargin{2}, varargin{3});
        if ~solid
            error('nb:material:surfaceMass', ...
                'Volume density x thickness is only a surface mass for a homogeneous solid layer; give surface_mass (kg/m^2) for fabrics or composites.');
        end
        if rho <= 0 || t <= 0, error('nb:material:positive', 'density and thickness must be > 0.'); end
        varargout{1} = rho * t;
    case 'massLaw'
        [m, f, model] = deal(varargin{1}, varargin{2}, varargin{3});
        if m <= 0, error('nb:material:mass', 'surface mass must be > 0 kg/m^2.'); end
        TL = 20*log10(f .* m) - 20*log10(415/pi);
        if strcmp(model, 'field'), TL = TL - 5;
        elseif ~strcmp(model, 'normal'), error('nb:material:model', 'model must be normal or field'); end
        varargout{1} = max(TL, 0);
    case 'effectiveTL'
        [TL, open] = deal(varargin{1}, varargin{2});
        if open < 0 || open > 1, error('nb:material:open', 'openness must be in [0,1].'); end
        varargout{1} = -10*log10(open + (1-open) * 10.^(-TL/10));
    case 'resolve'
        varargout{1} = resolve(varargin{1}, b);
    otherwise
        error('nb:material:action', 'unknown action');
end
end

function r = resolve(mat, b)
w = {};
openness = 0;  if isfield(mat,'openness') && ~isempty(mat.openness), openness = mat.openness; end
model = 'normal';  if isfield(mat,'tl_model') && ~isempty(mat.tl_model), model = mat.tl_model; end
m = [];
if isfield(mat,'surface_mass') && ~isempty(mat.surface_mass)
    m = mat.surface_mass;
elseif isfield(mat,'volume_density') && ~isempty(mat.volume_density)
    if ~isfield(mat,'thickness') || isempty(mat.thickness), error('nb:material:thickness', 'volume_density needs a thickness.'); end
    solid = isfield(mat,'solid') && ~isempty(mat.solid) && mat.solid;
    m = nb_material('surfaceMass', mat.volume_density, mat.thickness, solid);
end
r.surface_mass = m;
if isfield(mat,'TL') && ~isempty(mat.TL)
    validateattributes(mat.TL, {'numeric'}, {'vector','numel',8,'finite','real','nonnegative'});
    r.TL = mat.TL(:)';  r.source = 'measured';  r.confidence = 'measured TL(f) supplied';
elseif ~isempty(m)
    r.TL = nb_material('massLaw', m, b.f, model);
    r.source = ['mass-law (' model ' incidence)'];
    r.confidence = 'rough estimate';
    w{end+1} = 'Mass-law TL is a rough engineering estimate; flexible or porous textiles can violate its assumptions. Use measured TL(f) when available.';
else
    error('nb:material:none', 'Give measured TL (8 octave bands) or a surface mass (or volume density + thickness + solid).');
end
if ~isempty(m) && m < 10
    w{end+1} = sprintf('Surface mass %.2f kg/m^2 is below the 10 kg/m^2 minimum for a screening object in ISO 9613-2:2024 7.4.1; ISO barrier formulas are used only as an opaque-screen estimate.', m);
end
r.TLeff = nb_material('effectiveTL', r.TL, openness);
r.openness = openness;
r.warnings = w;
end
