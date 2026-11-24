function out = run_acoustic_case(c)
%RUN_ACOUSTIC_CASE Single-source, single-receiver prediction (stable entry point).
%   out = RUN_ACOUSTIC_CASE(c) with struct c:
%     c.Lw        1x8 sound power level L_W, dB re 1 pW, UNWEIGHTED, bands 63..8000
%     c.Dc        1x8 directivity correction, dB (default zeros)
%     c.hs, c.hr  source / receiver height above LOCAL ground, m
%     c.dp        source-receiver distance projected on the ground plane, m
%     c.dh        ground elevation difference (receiver ground minus source
%                 ground), m, default 0. True 3D distance is
%                 d = sqrt(dp^2 + (hr - hs + dh)^2).
%     c.G         struct Gs, Gm, Gr (0..1)
%     c.atm       struct T_C, RH, p_kPa
%     c.mode      'iso2024' (default), 'draft2026' (DRAFT) or 'iso1996'
%                 (ISO 9613-2:1996 compatibility, benchmarks only)
%     c.groundMethod  'general' (default) or 'simplified' (A-weighted, cl. 7.3.2; c.hm optional)
%     c.barrier   [] or struct with fields z, dss, dsr, e (top path) and
%                 optional side1, side2 structs with the same fields
%                 (geometry supplied by the caller; see geometry modules)
%     c.C0        [] (default, no long-term correction) or scalar dB
%   Returns out with every intermediate term as 1x8 vectors, broadband
%   values, and a code fingerprint (see nb_fingerprint).
%
%   Flat/sloped ground only here: Agr uses the general method with
%   heights above local ground. Reflections and Amisc are NOT implemented
%   and are reported as zeros with out.notImplemented listing them.
if ~isfield(c,'Dc') || isempty(c.Dc), c.Dc = zeros(1,8); end
if ~isfield(c,'dh') || isempty(c.dh), c.dh = 0; end
if ~isfield(c,'mode') || isempty(c.mode), c.mode = 'iso2024'; end
if ~isfield(c,'barrier'), c.barrier = []; end
if ~isfield(c,'C0'), c.C0 = []; end
validateattributes(c.Lw, {'numeric'}, {'vector','numel',8,'finite','real'});
validateattributes(c.Dc, {'numeric'}, {'vector','numel',8,'finite','real'});
% Optional enclosure around the source (a source-side material, NOT a diffraction barrier)
enclosureInfo = [];
if isfield(c, 'enclosure') && ~isempty(c.enclosure)
    enclosureInfo = nb_enclosure(c.Lw, c.enclosure);
    c.Lw = enclosureInfo.Lw_out;
end

b  = nb_bands();
% True 3D distance. Absolute heights: source z = zs, receiver z = zs + dh + (hr-hs).
dz3 = (c.hr - c.hs) + c.dh;
d   = sqrt(c.dp^2 + dz3^2);

out.mode  = c.mode;
out.f     = b.f;
out.d     = d;
out.dp    = c.dp;
out.Adiv  = nb_adiv(d) * ones(1,8);
if strcmp(c.mode, 'iso1996')
    out.Aatm = nb_aatm_1996(d, c.atm.T_C, c.atm.RH);       % ISO 9613-2:1996 Table 2 (benchmark compatibility)
else
    out.Aatm = nb_aatm(d, c.atm.T_C, c.atm.RH, c.atm.p_kPa);
end
groundMode = 'iso2024';  if strcmp(c.mode, 'iso1996'), groundMode = 'iso1996'; end
g = nb_agr(c.G.Gs, c.G.Gm, c.G.Gr, c.hs, c.hr, c.dp, groundMode);
out.Agr   = g.Agr;  out.As = g.As;  out.Ar = g.Ar;  out.Am = g.Am;
out.Kgeo  = g.Kgeo; out.q  = g.q;
out.groundMethod = 'general';
if isfield(c, 'groundMethod') && strcmp(c.groundMethod, 'simplified')
    % Alternative method for A-WEIGHTED levels (cl. 7.3.2): one A_gr for all bands, D_Omega added to D_c.
    hm = (c.hs + c.hr)/2;
    if isfield(c, 'hm') && ~isempty(c.hm), hm = c.hm; end
    sg = nb_agr_simplified(hm, d, c.dp, c.hs, c.hr);
    out.Agr = sg.Agr * ones(1,8);  out.groundMethod = 'simplified';  out.hm = hm;  out.DOmega = sg.DOmega;
    c.Dc = c.Dc + sg.DOmega;
end

out.Abar_top = zeros(1,8); out.Abar_side1 = zeros(1,8); out.Abar_side2 = zeros(1,8);
out.Abar = zeros(1,8);  out.Abar_extra = zeros(1,8);  out.barrierBandApplicable = true(1,8);
out.Dz_top = zeros(1,8);   out.zdiag = struct();
if ~isempty(c.barrier)
    B = c.barrier;
    t = nb_dz(B.z, B.dss, B.dsr, d, B.e, c.mode, false);
    s1 = []; s2 = [];
    if isfield(B,'side1') && ~isempty(B.side1)
        r1 = nb_dz(B.side1.z, B.side1.dss, B.side1.dsr, d, B.side1.e, c.mode, true); s1 = r1.Dz;
    end
    if isfield(B,'side2') && ~isempty(B.side2)
        r2 = nb_dz(B.side2.z, B.side2.dss, B.side2.dsr, d, B.side2.e, c.mode, true); s2 = r2.Dz;
    end
    % Per-band relevance (ISO 9613-2:2024 7.4.1: object width normal to S-R must exceed lambda)
    if isfield(B, 'mask') && ~isempty(B.mask)
        mk = logical(B.mask(:)');
        t.Dz(~mk) = 0;
        if ~isempty(s1), s1(~mk) = 0; end
        if ~isempty(s2), s2(~mk) = 0; end
        out.barrierBandApplicable = mk;
    else
        out.barrierBandApplicable = true(1,8);
    end
    extra = [];
    if isfield(B, 'extra') && ~isempty(B.extra)
        extra = B.extra;
        if isfield(B, 'mask') && ~isempty(B.mask), extra(:, ~logical(B.mask(:)')) = 0; end
    end
    ab = nb_abar(t.Dz, s1, s2, out.Agr, extra);
    out.Abar = ab.Abar;
    out.Abar_extra = zeros(1,8);
    if ~isempty(extra), out.Abar_extra = max(extra(1,:), 0); end
    if ~isempty(ab.Abar_top),   out.Abar_top   = ab.Abar_top;   end
    if ~isempty(ab.Abar_side1), out.Abar_side1 = ab.Abar_side1; end
    if ~isempty(ab.Abar_side2), out.Abar_side2 = ab.Abar_side2; end
    out.Dz_top = t.Dz;  out.zdiag = struct('z',B.z,'dss',B.dss,'dsr',B.dsr,'e',B.e, ...
        'zmin',t.zmin,'C3',t.C3,'Kmet',t.Kmet,'cap',t.cap,'Dz_uncapped',t.Dz_uncapped);
end

% Transmissive screen (optional): c.screenTL = struct TL (1x8 total transmission loss of
% every fabric crossed by the direct ray, dB). ENGINEERING APPROXIMATION, not ISO 9613-2:
% A_eff = -10 lg(10^(-A_bar/10) + 10^(-TL/10)) where the opaque A_bar > 0.
out.screenApplied = false;
if isfield(c, 'screenTL') && ~isempty(c.screenTL)
    TLs = c.screenTL.TL(:)';
    Abar_iso = out.Abar;
    Aeff = Abar_iso;
    act = Abar_iso > 0;
    Aeff(act) = -10*log10(10.^(-Abar_iso(act)/10) + 10.^(-TLs(act)/10));
    free = c.Lw + c.Dc - (out.Adiv + out.Aatm + out.Agr);
    out.screen = struct('Abar_opaque', Abar_iso, 'TL', TLs, 'A_eff', Aeff, ...
        'L_diffracted', free - Abar_iso, 'L_transmitted', free - TLs, ...
        'rule_of_thumb_TL_minus_Abar', TLs - Abar_iso, ...
        'opaqueAssumptionOK', all(TLs(act) - Abar_iso(act) >= 10), ...
        'method', 'energy sum of the diffracted (ISO 9613-2 A_bar) and transmitted (TL) paths; engineering approximation, NOT prescribed by ISO 9613-2');
    if isfield(c.screenTL, 'info'), out.screen.info = c.screenTL.info; end
    out.Abar_opaque = Abar_iso;
    out.Abar = Aeff;
    out.screenApplied = true;
end

out.Amisc = zeros(1,8);
out.Dc    = c.Dc;
out.Cmet  = 0;
if ~isempty(c.C0), out.Cmet = nb_cmet(c.C0, c.hs, c.hr, c.dp); end

out.Atotal = out.Adiv + out.Aatm + out.Agr + out.Abar + out.Amisc;    % Formula (5)
out.Lw   = c.Lw;
if ~isempty(enclosureInfo), out.enclosure = enclosureInfo; end
out.Lp   = c.Lw + c.Dc - out.Atotal;                                   % Formula (3)
out.Lp_longterm_applied = ~isempty(c.C0);
out.LpA_bands = out.Lp + b.wA;
if out.Lp_longterm_applied, out.LpA_bands = out.LpA_bands - out.Cmet; end  % Formula (7), A-weighted only
out.Lp_broadband  = nb_energy_sum(out.Lp);        % 63-8000 Hz bands only, unweighted
out.LpA_broadband = nb_energy_sum(out.LpA_bands); % dBA from the 8 modelled bands
if isfield(c, 'limits') && ~isempty(c.limits)
    lim = c.limits;
    if isfield(lim, 'bands') && ~isempty(lim.bands), lim.bands = double(lim.bands); end
    out.compliance = nb_compliance(out.Lp, out.LpA_bands, lim);
end
out.notImplemented = {'A_misc (foliage, industrial site, housing)', ...
    'reflections from obstacles (cl. 7.5)', 'simplified A-weighted ground method (7.3.2)'};
if isfield(c, 'skipFingerprint') && c.skipFingerprint
    out.fingerprint = struct('file', {{}}, 'md5', {{}}, 'modified', []);   % grid runs record it once at the top level
else
    out.fingerprint = nb_fingerprint();
end
end
