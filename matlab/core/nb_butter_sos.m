function sos = nb_butter_sos(n, Wn)
%NB_BUTTER_SOS Digital Butterworth band-pass as second-order sections, base MATLAB only.
%   sos = NB_BUTTER_SOS(n, [w1 w2])
%     n        prototype order; the band-pass has order 2n and n sections
%     w1, w2   band edges (-3 dB points) normalised to Nyquist, 0 < w1 < w2 < 1
%   sos is n-by-6, rows [b0 b1 b2 1 a1 a2], to be applied in cascade with filter().
%   Replaces butter()+zp2sos() of the Signal Processing Toolbox so the solver
%   needs no toolbox. Same construction as the textbook/butter() route:
%     1. analogue low-pass prototype poles p_k = exp(j pi (2k+n-1)/(2n)), k = 1..n
%     2. pre-warp the edges: U = 4 tan(pi W/2) (sample rate normalised to 2)
%     3. low-pass to band-pass: each pole p -> s = p Bw/2 +- sqrt((p Bw/2)^2 - Wo^2),
%        Bw = U2 - U1, Wo = sqrt(U1 U2); n zeros at s = 0; gain Bw^n
%     4. bilinear transform z = (4 + s)/(4 - s): zeros at s = 0 map to z = +1, the
%        n missing zeros sit at z = -1; gain from the exact bilinear gain formula
%     5. each conjugate pole pair with one zero at +1 and one at -1 is a section
%        b = g [1 0 -1], a = [1 -2 Re(p) |p|^2]; the total gain is split evenly.
%   Verified against scipy.signal.butter (see tests/test_audio.py) and by the
%   analytic Butterworth properties: |H| = -3.0103 dB at both edges, 0 dB at
%   sqrt(f1 f2) (arithmetic mean on the warped axis).
if ~isscalar(n) || n < 1 || n ~= round(n), error('nb:butter:order', 'Order must be a positive integer.'); end
if numel(Wn) ~= 2 || ~(Wn(1) > 0 && Wn(2) > Wn(1) && Wn(2) < 1), error('nb:butter:edges', 'Band edges must satisfy 0 < w1 < w2 < 1 (Nyquist = 1).'); end
k  = 1:n;
pa = exp(1j*pi*(2*k + n - 1)/(2*n));                 % analogue low-pass poles (left half plane)
U  = 4*tan(pi*Wn/2);                                  % pre-warped edges, sample rate normalised to 2
Bw = U(2) - U(1);  Wo = sqrt(U(1)*U(2));
h  = pa*Bw/2;
d  = sqrt(h.^2 - Wo^2);
ps = [h + d, h - d];                                  % 2n analogue band-pass poles
kz = Bw^n * real(4^n / prod(4 - ps));                 % bilinear gain (zeros at s = 0 contribute 4^n)
pz = (4 + ps)./(4 - ps);                              % digital poles
pz = pz(imag(pz) > 0);                                % one of each conjugate pair; n of them
[~, idx] = sort(abs(pz));                             % least resonant first: better numerical balance
pz = pz(idx);
g  = kz^(1/n);
sos = zeros(n, 6);
for s = 1:n
    sos(s,:) = [g 0 -g, 1, -2*real(pz(s)), abs(pz(s))^2];
end
end
