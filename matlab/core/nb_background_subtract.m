function r = nb_background_subtract(Ls, Lb)
%NB_BACKGROUND_SUBTRACT Remove background noise band by band (energy domain).
%   r = NB_BACKGROUND_SUBTRACT(Ls, Lb)  with 1x8 levels in dB (same
%   reference and weighting): signal+background Ls, background alone Lb.
%     Lcorr = 10 lg(10^(Ls/10) - 10^(Lb/10))
%   Validity per band, from DeltaL = Ls - Lb:
%     DeltaL <= 3 dB : INVALID (NaN) - background too high to subtract
%     3 < DeltaL < 6 : corrected, flagged 'marginal'
%     6 <= DeltaL < 10: corrected, flagged 'ok'
%     DeltaL >= 10   : corrected (correction < 0.46 dB), flagged 'ok'
%   Levels are never averaged in dB.
dL = Ls - Lb;
Lc = nan(1,8);  status = repmat({'invalid'}, 1, 8);
ok = dL > 3;
Lc(ok) = 10*log10(10.^(Ls(ok)/10) - 10.^(Lb(ok)/10));
for k = 1:8
    if isnan(dL(k)), status{k} = 'invalid'; continue; end
    if dL(k) <= 3, status{k} = 'invalid';
    elseif dL(k) < 6, status{k} = 'marginal';
    else, status{k} = 'ok'; end
end
r.Lcorr = Lc;  r.deltaL = dL;  r.status = status;
r.correction = Lc - Ls;
r.warnings = {};
if any(strcmp(status, 'invalid')), r.warnings{end+1} = 'Bands with signal less than 3 dB above background are invalid (NaN) and cannot be used for L_W or predictions.'; end
if any(strcmp(status, 'marginal')), r.warnings{end+1} = 'Bands 3 to 6 dB above background are marginal; uncertainty is large.'; end
end
