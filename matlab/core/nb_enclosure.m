function r = nb_enclosure(Lw_in, enc)
%NB_ENCLOSURE Radiated sound power of a source inside a material enclosure.
%   r = NB_ENCLOSURE(Lw_in, enc)
%     Lw_in  1x8 sound power of the bare source, dB re 1 pW
%     enc    S_total   enclosure surface area, m^2
%            A_in      equivalent sound absorption area inside, m^2
%            mat       material struct (nb_material('resolve') input)
%            S_open    optional total area of openings, m^2 (tau = 1)
%   Diffuse-interior model (as in EN ISO 15667 / Bies & Hansen):
%     L_p,in  = L_W,in + 10 lg(4/A_in)                   reverberant field
%     TL_eff  = -10 lg[(S_open + (S - S_open) 10^(-TL/10)) / S]
%     L_W,out = L_p,in - TL_eff + 10 lg(S) - 6
%   ASSUMPTIONS (reported): diffuse field inside, uniform surface, no
%   panel resonance or coincidence, no near-field or flanking effects,
%   openings radiate with tau = 1. A free-standing enclosure that is
%   close to the source violates the diffuse-field assumption.
%   If L_W,out exceeds L_W,in in a band the model is not applicable
%   there (too little interior absorption): flagged, NOT clamped.
S = enc.S_total;  A = enc.A_in;
if S <= 0 || A <= 0, error('nb:enclosure:area', 'S_total and A_in must be > 0 m^2.'); end
Sopen = 0;  if isfield(enc,'S_open') && ~isempty(enc.S_open), Sopen = enc.S_open; end
if Sopen < 0 || Sopen > S, error('nb:enclosure:open', 'S_open must be in [0, S_total].'); end
m = nb_material('resolve', enc.mat);
TLfab = m.TL;                                   % openness inside mat is ignored here; use S_open
TLeff = -10*log10((Sopen + (S - Sopen) * 10.^(-TLfab/10)) / S);
Lp_in = Lw_in + 10*log10(4/A);
r.Lw_out = Lp_in - TLeff + 10*log10(S) - 6;
r.Lw_in = Lw_in;  r.Lp_in = Lp_in;  r.TL = TLfab;  r.TLeff = TLeff;
r.reduction = Lw_in - r.Lw_out;
r.notApplicableBands = r.Lw_out > Lw_in + 1e-9;
r.material = m;
r.warnings = m.warnings;
if any(r.notApplicableBands)
    r.warnings{end+1} = 'In some bands L_W,out > L_W,in: interior absorption is too small for the diffuse-field model; result not applicable there.';
end
if Sopen > 0
    r.warnings{end+1} = sprintf('Openings (%.2f of %.2f m^2) limit the achievable reduction to about %.1f dB.', Sopen, S, -10*log10(Sopen/S));
end
r.warnings{end+1} = 'Rough engineering estimate: diffuse interior field, no resonance/coincidence/near-field effects.';
r.model = 'EN ISO 15667-style diffuse-field enclosure model';
end
