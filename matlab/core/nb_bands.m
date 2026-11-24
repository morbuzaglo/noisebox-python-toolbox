function b = nb_bands()
%NB_BANDS Octave-band centre frequencies and A-weighting corrections.
%   b.f      [1x8] NOMINAL centre frequencies, Hz (all frequency-dependent
%            terms except atmospheric absorption)
%   b.fexact [1x8] EXACT base-10 centre frequencies, Hz = 1000*10^(0.3*n),
%            n = -4..3. ISO 9613-2:2024 cl. 7.2 requires these for the
%            ISO 9613-1 absorption coefficient (printed p. 9).
%   b.wA     [1x8] A-weighting corrections, dB (add to unweighted level).
%            PROVISIONAL: values supplied in the project brief; confirm
%            against ISO 9613-2:2024 / IEC 61672-1 before claiming
%            conformance (not yet located in the scan).
b.f      = [63 125 250 500 1000 2000 4000 8000];
b.fexact = 1000 * 10.^(0.3*(-4:3));
b.wA     = [-26.2 -16.1 -8.6 -3.2 0 1.2 1.0 -1.1];
end
