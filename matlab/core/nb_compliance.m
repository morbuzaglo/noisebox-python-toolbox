function r = nb_compliance(Lp, LpA, lim)
%NB_COMPLIANCE Per-band and overall limit check for N points.
%   r = NB_COMPLIANCE(Lp, LpA, lim)
%     Lp   Nx8 unweighted octave-band predictions, dB
%     LpA  Nx8 A-weighted octave-band predictions, dB(A)
%     lim  struct:
%        lim.bands      1x8 permitted levels; NaN = no limit for that band
%        lim.weighting  'Z' (limits compare to unweighted Lp) or 'A'
%        lim.overallA   scalar broadband dB(A) limit, NaN/[] = none
%   A point is PASS only if EVERY band that has a limit is <= its limit
%   and the optional overall dB(A) limit is met. Broadband dBA passing
%   never turns a point green when a band fails.
%   code: 1 PASS, 0 FAIL, NaN NO DATA (a NaN prediction anywhere that
%   matters), -1 NO LIMITS defined.
%   margin = predicted - permitted, dB (positive = exceedance).
if ~isfield(lim,'bands') || isempty(lim.bands), lim.bands = nan(1,8); end
if ~isfield(lim,'weighting') || isempty(lim.weighting), lim.weighting = 'Z'; end
if ~isfield(lim,'overallA') || isempty(lim.overallA), lim.overallA = NaN; end
if ~any(strcmp(lim.weighting, {'Z','A'}))
    error('nb:compliance:weighting', 'lim.weighting must be ''Z'' or ''A''.');
end
validateattributes(lim.bands, {'numeric'}, {'vector','numel',8});
N = size(Lp, 1);
if size(Lp,2) ~= 8 || ~isequal(size(Lp), size(LpA))
    error('nb:compliance:size', 'Lp and LpA must both be Nx8.');
end
pred = Lp;  if lim.weighting == 'A', pred = LpA; end
active = ~isnan(lim.bands(:)');
tol = 1e-9;

margin  = pred - lim.bands;                    % NaN where no limit
exceed  = margin > tol;                        % NaN compares false
exceed(:, ~active) = false;

LpA_bb = 10*log10(sum(10.^(LpA/10), 2));       % broadband dB(A), 8 modelled bands
hasOverall = ~isnan(lim.overallA);
overallMargin = nan(N,1);
if hasOverall, overallMargin = LpA_bb - lim.overallA; end
overallExceed = hasOverall & overallMargin > tol;

nodata = any(isnan(pred(:, active)), 2);
if hasOverall, nodata = nodata | isnan(LpA_bb); end
nolimits = ~any(active) && ~hasOverall;

fail = any(exceed, 2) | overallExceed;
code = double(~fail);
code(nodata & ~fail) = NaN;                    % a failing band is a FAIL even if another is missing
code(nolimits) = -1;

m = margin;  m(:, ~active) = -Inf;
[worstMargin, worstBand] = max(m, [], 2);
worstBand(~any(exceed,2)) = 0;                 % 0 = no exceeding band
r.code = code;  r.margin = margin;  r.exceed = exceed;
r.worstBand = worstBand;  r.worstMargin = worstMargin;
r.overallMargin = overallMargin;  r.overallExceed = overallExceed;
r.LpA_broadband = LpA_bb;  r.activeBands = active;
r.status = cell(N,1);
for i = 1:N
    switch code(i)
        case 1,  r.status{i} = 'PASS';
        case 0,  r.status{i} = 'FAIL';
        case -1, r.status{i} = 'NO LIMITS';
        otherwise, r.status{i} = 'NO DATA';
    end
end
end
