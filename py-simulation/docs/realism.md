# Realism Assessment

What the simulation captures faithfully, where it simplifies, and when to trust the results.

## What IS Realistic

- **Ground reflection via image source** — Standard acoustics technique. Phase inversion (pressure-release boundary), time delay, and 1/r attenuation are physically correct. Mast-mounted arrays on hard surfaces genuinely experience this comb-filter effect.

- **Directional noise sources** — Real wind, traffic, and birds arrive from specific directions, not isotropically. Modeling them as point sources (or a Corcos distributed field for wind) creates spatially-correlated mic signals that stress the beamformer realistically.

- **Corcos wind coherence** — The frequency-dependent spatial correlation of wind turbulence at the microphone array is well-modeled by the Corcos formulation for atmospheric surface-layer turbulence. The Cholesky decomposition correctly generates a random field with the prescribed coherence matrix.

- **EIN-based SNR** — Microphone self-noise is a physical floor. The ICS-52000's 29 dBA EIN sets the minimum detectable signal. Using `94 − snr_dba` to derive noise power is the standard electroacoustic approach.

- **Detection rate < 100% is correct behavior** — Only frames with a dominant SRP peak should pass the gate. The red-shaded regions in DOA tracking plots faithfully represent suppressed frames.

- **Atmospheric turbulence (OU process)** — The Ornstein-Uhlenbeck delay jitter captures random phase perturbations from temperature gradients and eddies. The 15 μs RMS / 50 ms correlation time are realistic for outdoor acoustic propagation at 10–50 m range.

- **HPF @ 75 Hz** — MEMS microphones like the ICS-52000 genuinely have a built-in high-pass filter for wind noise suppression. The 75 Hz cutoff and 6 dB/octave rolloff match the datasheet.

- **AOP soft-clipping** — Real MEMS microphones exhibit nonlinear distortion near the acoustic overload point. The tanh model is a reasonable approximation of the saturation curve.

## What is NOT Realistic or Missing

1. **Static noise sources** — Traffic is fixed at a single position and does not move. Real vehicles have Doppler shift and evolving spectral signatures.

2. **No wind-induced structural vibration** — Mast vibration from wind couples into microphones as low-frequency correlated noise (typically < 50 Hz). Not modeled.

3. **No precipitation** — Rain, hail, and snow produce broadband impulsive noise that dominates the acoustic environment during weather events. Not modeled.

4. **Single ground type, constant coefficient** — The reflection coefficient is frequency-independent and invariant. Real ground impedance varies with frequency, incidence angle, and soil moisture. A Delany-Bazley impedance model would be more accurate but adds complexity.

5. **No atmospheric refraction** — Long-range propagation (>100 m) includes upward/downward refraction from temperature gradients and wind shear. Not modeled (all sources are within 50 m).

6. **No microphone phase/magnitude mismatch** — All 16 mics are perfectly matched in phase and magnitude response. Real arrays have channel-to-channel variation that degrades beamforming.

7. **Simplified bird calls** — Chirps are linear FM sweeps. Real birds have species-specific calls with harmonics, trills, and amplitude modulation.

8. **Limited BPF harmonics** — Only 6 blade-passage harmonics are modeled (1st through 6th). Real drone spectra extend higher, though at diminishing amplitude.

9. **No Doppler shift** — The moving-path delay interpolation provides time-varying delays but does not apply Doppler frequency shifting to the source signal.

10. **No electronic noise** — ADC quantization noise, preamp noise, and cable pickup are not modeled beyond the per-channel AWGN derived from the microphone EIN.

## Key Findings Summary

| Effect | P2M Impact | Detection Impact |
|---|---|---|
| Ground reflection (coeff=0.05) | −0.9 dB | 96% → 1% |
| ICS-52000 HPF @ 75 Hz | −0.8 dB | ~99% → ~95% (no ground) |
| EIN-derived SNR (17.5 vs 25 dB) | −0.2 dB | ~96% → ~95% (no ground) |
| Wind 10 m/s | −0.2 dB | Negligible |
| Turbulence 15 μs | −0.1 dB | Negligible |
| Traffic "light" | −0.1 dB | Negligible |
| Birds 0.10 | −0.1 dB | Negligible |

**The dominant effect is ground reflection.** All other noise sources combined contribute less than ground reflection alone. The sharp detection cliff arises because the comb-filter nulls align with the drone's BPF harmonics, and PHAT whitening cannot suppress a correlated reflected copy of the signal.

## When to Trust the Results

| Scenario | Trust Level | Reason |
|---|---|---|
| Ground-free, high SNR | High | Well-understood physics, array gain dominates |
| Moderate ground (coeff ≤ 0.05) | Medium | Physics is correct but real ground varies |
| Strong ground (coeff ≥ 0.10) | Low | Detection collapse is real, but the exact coefficient is site-dependent |
| Wind noise | High | Corcos model is well-validated for outdoor arrays |
| Traffic / birds | Medium | Directional propagation is correct; real sources are more complex |
| Long range (> 50 m) | Low | Missing refraction and atmospheric absorption |
| Precipitation | None | Not modeled at all |
