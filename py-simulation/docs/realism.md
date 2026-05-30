# Realism Assessment

What the simulation captures faithfully, where it simplifies, and when to trust the results.

## What IS Realistic

- **Ground reflection via image source** — Standard acoustics technique. Phase inversion (pressure-release boundary), time delay, and 1/r attenuation are physically correct. Mast-mounted arrays on hard surfaces genuinely experience this comb-filter effect.

- **Frequency-dependent ground impedance (Delany-Bazley)** — The reflection coefficient now varies with frequency and incidence angle via the Delany-Bazley porous ground model. Configurable flow resistivity (σ = 200 kPa·s/m² for grass, 20 MPa·s/m² for asphalt, 30 kPa·s/m² for snow). This replaces the old constant-coefficient approximation and captures realistic frequency-dependent comb filtering.

- **ISO 9613-1 atmospheric absorption** — Frequency-dependent air absorption α(f, T, RH, P) per ISO 9613-1 / ANSI S1.26-1995. Applied in the frequency-domain propagation pipeline. Attenuates high-frequency drone harmonics preferentially (~0.6 dB/100m at 1 kHz, ~3 dB/100m at 8 kHz, 20°C, 50% RH). This is the dominant range-limiting physics for acoustic detection beyond ~50 m.

- **Atmospheric refraction (effective sound speed)** — Logarithmic wind profile + linear temperature lapse rate → effective sound speed gradient. Upward refraction (daytime, downwind) creates shadow zones with excess attenuation up to ~6 dB. Downward refraction (nighttime, upwind) returns 0 dB excess. Modeled via curvature radius and shadow boundary calculation.

- **Directional noise sources** — Real wind, traffic, and birds arrive from specific directions, not isotropically. Modeling them as point sources (or a Corcos distributed field for wind) creates spatially-correlated mic signals that stress the beamformer realistically.

- **Corcos wind coherence** — The frequency-dependent spatial correlation of wind turbulence at the microphone array is well-modeled by the Corcos formulation for atmospheric surface-layer turbulence. The Cholesky decomposition correctly generates a random field with the prescribed coherence matrix.

- **EIN-based SNR** — Microphone self-noise is a physical floor. The ICS-52000's 29 dBA EIN sets the minimum detectable signal. Using `94 − snr_dba` to derive noise power is the standard electroacoustic approach.

- **Detection rate < 100% is correct behavior** — Only frames with a dominant SRP peak should pass the gate. The red-shaded regions in DOA tracking plots faithfully represent suppressed frames.

- **Atmospheric turbulence (OU process + amplitude scintillation)** — Ornstein-Uhlenbeck delay jitter captures random phase perturbations from temperature gradients and eddies (15 μs RMS / 50 ms correlation time). Log-normal amplitude scintillation models turbulence-induced signal fading. Both are configurable.

- **HPF @ 75 Hz** — MEMS microphones like the ICS-52000 genuinely have a built-in high-pass filter for wind noise suppression. The 75 Hz cutoff and 6 dB/octave rolloff match the datasheet.

- **AOP soft-clipping** — Real MEMS microphones exhibit nonlinear distortion near the acoustic overload point. The tanh model is a reasonable approximation of the saturation curve.

- **Configurable BPF harmonics** — The number of blade-passage harmonics (1st through Nth) is user-configurable via `drone.bpf_harmonics`. Defaults to 6; can be increased to model higher-frequency content.

## What is NOT Realistic or Missing

1. **Static noise sources** — Traffic is fixed at a single position and does not move. Real vehicles have Doppler shift and evolving spectral signatures.

2. **No wind-induced structural vibration** — Mast vibration from wind couples into microphones as low-frequency correlated noise (typically < 50 Hz). Not modeled.

3. **No precipitation** — Rain, hail, and snow produce broadband impulsive noise that dominates the acoustic environment during weather events. Not modeled.

4. **No microphone phase/magnitude mismatch** — All 16 mics are perfectly matched in phase and magnitude response. Real arrays have channel-to-channel variation that degrades beamforming.

5. **Simplified bird calls** — Chirps are linear FM sweeps. Real birds have species-specific calls with harmonics, trills, and amplitude modulation.

6. **No Doppler shift** — The moving-path OLA block processing provides time-varying delays but does not apply Doppler frequency shifting to the source signal.

7. **No electronic noise** — ADC quantization noise, preamp noise, and cable pickup are not modeled beyond the per-channel AWGN derived from the microphone EIN.

8. **Simplified vegetation/barrier attenuation** — No foliage or terrain shadowing. Propagation is over open ground with no obstacles.

## Key Findings Summary

| Effect | P2M Impact | Detection Impact |
|---|---|---|
| Ground reflection (coeff=0.05) | −0.9 dB | 96% → 1% |
| ICS-52000 HPF @ 75 Hz | −0.8 dB | ~99% → ~95% (no ground) |
| EIN-derived SNR (17.5 vs 25 dB) | −0.2 dB | ~96% → ~95% (no ground) |
| ISO 9613-1 absorption (20°C, 50% RH, 100m) | Frequency-dependent | Suppresses high harmonics at range |
| Refraction shadow zone (upwind, 200m) | 1–6 dB excess loss | Reduces detection at long range |
| Delany-Bazley ground vs constant coeff | Varies with θ, f | More nuanced than sharp cliff |
| Wind 10 m/s | −0.2 dB | Negligible |
| Turbulence 15 μs | −0.1 dB | Negligible |
| Amplitude scintillation | −0.1 dB | Negligible |
| Traffic "light" | −0.1 dB | Negligible |
| Birds 0.10 | −0.1 dB | Negligible |

**The dominant effect at short range (<50m) is ground reflection.** At longer ranges, atmospheric absorption becomes the primary range-limiting factor, preferentially attenuating higher BPF harmonics and narrowing the usable bandwidth for beamforming.

## When to Trust the Results

| Scenario | Trust Level | Reason |
|---|---|---|
| Ground-free, high SNR | High | Well-understood physics, array gain dominates |
| Moderate ground (coeff ≤ 0.05) | Medium | Physics is correct but real ground varies |
| Strong ground (coeff ≥ 0.10) | Low | Detection collapse is real, but the exact coefficient is site-dependent |
| Delany-Bazley ground | Medium | Frequency-dependent impedance is more accurate; flow resistivity is an estimate |
| Wind noise | High | Corcos model is well-validated for outdoor arrays |
| Traffic / birds | Medium | Directional propagation is correct; real sources are more complex |
| Short-to-medium range (< 200 m) | Medium-High | Absorption + refraction + turbulence modeled per standards |
| Long range (200–500 m) | Medium | Absorption and refraction are correct; terrain/obstacles not modeled |
| Precipitation | None | Not modeled at all |
