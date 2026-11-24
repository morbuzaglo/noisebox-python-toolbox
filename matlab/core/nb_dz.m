function r = nb_dz(z, dss, dsr, d, e, mode, isLateral)
%NB_DZ Barrier attenuation D_z for one diffraction path, all 8 octave bands.
%   r = NB_DZ(z, dss, dsr, d, e, mode, isLateral)
%     z    path length difference, m (scalar). Negative when the line of
%          sight passes above a single top edge (Formula 22 text).
%     dss  source-to-first-edge path length, m
%     dsr  last-edge-to-receiver path length, m
%     d    straight source-receiver distance, m
%     e    path length between first and last edge, m (0 for single edge)
%     mode 'iso2024'  : published ISO 9613-2:2024 Formulae (18)-(21)
%          'draft2026': experimental DAmd 1 replacements of (18) and (21)
%                       (DRAFT, not a published amendment)
%          'iso1996'  : ISO 9613-2:1996 Formula (14)/(15) as recommended by
%                       ISO/TR 17534-3 (5.3, 5.4): identical expressions to
%                       'draft2026'; used for benchmark comparison only
%     isLateral  true for a laterally diffracted path (K_met = 1, no cap
%                of the top-path kind; see below)
%   Returns struct with 1x8 fields: lambda, C3, zmin, Kmet, Dz, Dz_uncapped
%   and flags.
%
%   Sources (PDF pages of standard_iso_9613-2_2024.pdf):
%     (18)-(21) printed p. 16 (PDF 24); caps 20/25 dB printed p. 20 (PDF 28)
%     DAmd 1 text: screenshot "ISO 9613-2 2024 DAmd 1.PNG" (eqs. 18, 21 only)
%   lambda = 340/f at the NOMINAL band centre frequency (printed p. 14).
%   The 20 dB / 25 dB limits are stated for the top path in the vertical
%   plane; they are applied here only when isLateral is false.
if nargin < 7, isLateral = false; end
if ~any(strcmp(mode, {'iso2024','draft2026','iso1996'}))
    error('nb:dz:mode', 'Unknown mode "%s".', mode);
end
b  = nb_bands();
fl = b.f;
if strcmp(mode, 'iso1996')
    % The ISO/TR 17534-3 reference values (T16: C3,top = 1.76 at e = 37.07 m) only reproduce with
    % lambda = 340/62.5 m for the 63 Hz band, not 340/63. Used in the 1996 compatibility mode only.
    fl(1) = 62.5;
end
lam = 340 ./ fl;
C2 = 20;
if e > 0
    t  = (5*lam/e).^2;
    C3 = (1 + t) ./ (1/3 + t);                       % Formula (20)
else
    C3 = ones(1,8);                                  % single diffraction
end
zmin = -2*lam ./ (C2*C3);                            % Formula (19)

Kmet = ones(1,8);
if ~isLateral
    switch mode
        case 'iso2024'                               % Formula (21)
            ok = z > zmin;
            Kmet(ok) = exp(-(1/2000) * sqrt((max(dss,dsr)+e) * min(dss,dsr) * d ./ (2*(z - zmin(ok)))));
        case {'draft2026','iso1996'}                 % DAmd 1 replacement of (21) = 1996 K_met
            if z > 0
                Kmet(:) = exp(-(1/2000) * sqrt(dss*dsr*d / (2*z)));
            end
    end
end

Dz = zeros(1,8);
ok = z > zmin;
switch mode
    case 'iso2024'                                   % Formula (18): 1 + (2 + (C2/lam) C3 z) Kmet
        Dz(ok) = 10*log10(1 + (2 + (C2./lam(ok)) .* C3(ok) * z) .* Kmet(ok));
    case {'draft2026','iso1996'}                     % DAmd 1 eq. (18) = ISO 9613-2:1996 Formula (14) with
        % the stepwise form recommended in ISO/TR 17534-3 cl. 5.4: Dz = 0 for z <= zmin
        Dz(ok) = 10*log10(3 + (C2./lam(ok)) .* C3(ok) * z .* Kmet(ok));
end
r.Dz_uncapped = Dz;
if ~isLateral
    if e > 0, cap = 25; else, cap = 20; end
    Dz = min(Dz, cap);
    r.cap = cap;
else
    r.cap = Inf;
end
r.Dz = Dz;  r.lambda = lam;  r.C3 = C3;  r.zmin = zmin;  r.Kmet = Kmet;
r.mode = mode;  r.isLateral = isLateral;
end
