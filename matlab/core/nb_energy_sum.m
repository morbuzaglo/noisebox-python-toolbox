function L = nb_energy_sum(levels_dB, dim)
%NB_ENERGY_SUM Logarithmic (energy) sum of levels in dB.
%   L = NB_ENERGY_SUM(levels_dB) sums along the first non-singleton
%   dimension. NaN entries are NOT ignored: a NaN band yields NaN, so a
%   missing band can never be silently dropped from a broadband value.
%   -Inf entries contribute zero energy.
if nargin < 2
    L = 10*log10(sum(10.^(levels_dB/10)));
else
    L = 10*log10(sum(10.^(levels_dB/10), dim));
end
end
