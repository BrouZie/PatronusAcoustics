# Realism Assessment

What the simulation captures faithfully, where it simplifies, and when to trust the results.

## What IS Realistic

- **Absolute Pa-referenced calibration (v5)** — In the default mode every source and noise term carries physical pressure: the drone is scaled to its dB SPL @ 1 m, wind noise follows dynamic-pressure scaling (Strasberg 1988), ambient/traffic/bird levels are literal dB SPL, mic self-noise is the absolute EIN floor, and the sensor converts Pa → digital full scale via the datasheet sensitivity (AOP ≈ 1.0 FS). SNR and detection-range numbers are now physically meaningful, with anchors pinned in `tests/test_physics_validation.py`.

- **Ground reflection via image source** — Standard acoustics technique. Phase inversion (pressure-release boundary), time delay, and `R/d_image` attenuation are physically correct (a pre-v5 amplitude bug that made the reflection ~d_direct× too strong was fixed in schema v5; see [environment.md](environment.md)). Cross-validated against pyroomacoustics (`tests/test_crossval_pyroomacoustics.py`) for arrival-time gap and direct/reflected level ratio. **Convention note**: we invert the reflected pressure (−R, the grazing-incidence/soft-ground limit); pyroomacoustics' rigid wall uses +R — this difference is deliberate and pinned by a test.

- **Per-rotor source synthesis (v5)** — Each of `num_rotors` gets its own RPM offset (`rpm_spread_pct`) and slow Ornstein-Uhlenbeck RPM wander (`rpm_jitter_pct`), so near-coincident BPF lines beat against each other — the amplitude modulation signature of real multirotors. Optional motor whine tone at the pole-pass order (`motor_whine_db`).

- **Retarded-time Doppler with windowed-sinc delays (v5)** — Moving-source propagation solves the emission-time equation t_e = t − d(t_e)/c (three fixed-point iterations) and reads the source through a 16-tap Kaiser-windowed sinc. An analytic test pins the received tone of a 20 m/s approach to f·c/(c−v) within 0.1 %, and a 6 kHz tone keeps its amplitude within 0.5 dB (the old 2-tap linear interpolator lost ~0.7 dB and missed the (v/c)² Doppler term). The C++ extension is bit-mirrored (parity test at 1e-10).

- **Frequency-dependent ground impedance (Delany-Bazley)** — The reflection coefficient varies with frequency and incidence angle via the Delany-Bazley porous ground model. The incidence angle is computed per-microphone from the image-source geometry (grazing vs. normal), not hardcoded to normal incidence. Configurable flow resistivity (σ = 200 kPa·s/m² for grass, 20 MPa·s/m² for asphalt, 30 kPa·s/m² for snow).

- **ISO 9613-1 atmospheric absorption** — Frequency-dependent air absorption α(f, T, RH, P) per ISO 9613-1 / ANSI S1.26-1995, validated against published table anchors (~0.03 dB/100 m at 125 Hz, ~0.5 dB/100 m at 1 kHz, ~2.3 dB/100 m at 4 kHz; 20 °C, 70 % RH). Applied in the frequency-domain propagation pipeline and in the EIN SNR budget. This is the dominant range-limiting physics beyond ~100 m.

- **Atmospheric refraction (effective sound speed)** — Logarithmic wind profile + linear temperature lapse rate → effective sound speed gradient. Upward refraction (daytime, downwind) creates shadow zones with excess attenuation up to ~6 dB. Downward refraction (nighttime, upwind) returns 0 dB excess. Modeled via curvature radius and shadow boundary calculation, then applied as a frequency-dependent pressure filter in the propagation pipeline alongside absorption.

- **Directional noise sources** — Real wind, traffic, and birds arrive from specific directions, not isotropically. Modeling them as point sources (or a Corcos distributed field for wind) creates spatially-correlated mic signals that stress the beamformer realistically.

- **Corcos wind coherence (directional)** — The frequency-dependent spatial correlation of wind turbulence is modeled via the full directional Corcos formulation: streamwise separation (α_ξ = 0.15), cross-stream separation (α_η = 0.75, ~5× larger decay), and a frozen-turbulence advection phase term exp(i·2π·f·ξ/U). The Cholesky decomposition correctly generates a random field with the prescribed complex coherence matrix. Mics aligned with the wind have higher coherence than mics perpendicular to it, matching real atmospheric surface-layer turbulence.

- **EIN-based SNR** — Microphone self-noise is a physical floor. The ICS-52000's 29 dBA EIN sets the minimum detectable signal. Using `94 − snr_dba` to derive noise power is the standard electroacoustic approach.

- **Hardware imperfections** — Per-mic gain mismatch, phase mismatch, PCB placement error, dead channels, and 24-bit quantization are modeled via `mic.imperfections` (`SensorModel`). Placement error is applied to the *true* positions while steering uses the *nominal* ones — the mismatch a fabricated array actually experiences. Since SRP-PHAT whitens channel magnitudes, phase/placement errors dominate; gain mismatch barely matters.

- **Cramer (1993) speed of sound** — One `c` from the configured temperature, humidity, and pressure (including the CO2 term) is shared by steering, propagation, and image-source paths, so a hot vs cold or humid vs dry day shifts all delays consistently. Published anchors pinned in tests; the legacy dry-air formula is kept bit-for-bit when the environment is disabled.

- **Detection rate < 100% is correct behavior** — Only frames with a dominant SRP peak should pass the gate. The red-shaded regions in DOA tracking plots faithfully represent suppressed frames.

- **Atmospheric turbulence (OU process + amplitude scintillation)** — Ornstein-Uhlenbeck delay jitter captures random phase perturbations from temperature gradients and eddies (15 μs RMS / 50 ms correlation time). Log-normal amplitude scintillation models turbulence-induced signal fading. Both are configurable.

- **Mic frequency response (v5)** — Per-mic 75 Hz 1st-order HPF with part-to-part corner spread (`hpf_corner_std_pct`) — which yields frequency-dependent gain *and* phase mismatch at LF — plus the ICS-52000's HF magnitude trace (rise to ~+3.5 dB at 20 kHz) as a minimum-phase filter. HF anchor values are approximate datasheet-plot reads; verify against the exact DS-000121 revision.

- **AOP soft-clipping** — Real MEMS microphones exhibit nonlinear distortion near the acoustic overload point. The tanh model is a reasonable approximation of the saturation curve.

- **Configurable BPF harmonics** — The number of blade-passage harmonics (1st through Nth) is user-configurable via `drone.bpf_harmonics`. Defaults to 6; can be increased to model higher-frequency content.

## What is NOT Realistic or Missing

1. **Static noise sources** — Traffic is fixed at a single position and does not move. Real vehicles have Doppler shift and evolving spectral signatures.

2. **No wind-induced structural vibration** — Mast vibration from wind couples into microphones as low-frequency correlated noise (typically < 50 Hz). Not modeled.

3. **No precipitation** — Rain, hail, and snow produce broadband impulsive noise that dominates the acoustic environment during weather events. Not modeled.

4. **Simplified bird calls** — Chirps are linear FM sweeps. Real birds have species-specific calls with harmonics, trills, and amplitude modulation.

5. **Simplified electronic noise** — EIN-derived AWGN (flat, not A-weighting-shaped) and ADC quantization are modeled; preamp 1/f noise and cable pickup are not.

6. **Simplified vegetation/barrier attenuation** — No foliage or terrain shadowing. Propagation is over open ground with no obstacles.

7. **No convective amplification** — Moving-source amplitude uses 1/d at emission time; the (1 − M·cosθ)⁻¹ convective factor (< 0.5 dB at drone speeds) is not modeled.

8. **Residual constant-phase mismatch** — The LF corner spread now provides frequency-dependent mismatch, but the additional `phase_std_deg` residual term remains frequency-independent.

9. **Wind-noise spectrum shape** — Level is calibrated (dynamic-pressure scaling), but the spectral envelope remains the pre-v5 brown-noise + 500 Hz LPF shape rather than the f^(−7/3) inertial-range power law; windscreen insertion loss is frequency-flat.

## Key Findings Summary

> The P2M/detection anchors below were measured pre-v5 (compensated
> reflection coefficients, uncalibrated noise scales). They remain
> qualitatively correct — ground reflection dominates short range,
> absorption dominates long range — but re-run the sweeps on schema v5
> before quoting numbers.

| Effect | P2M Impact | Detection Impact |
|---|---|---|
| Ground reflection (pre-v5 coeff=0.05 ≈ physical R≈0.9) | −0.9 dB | 96% → 1% |
| ICS-52000 HPF @ 75 Hz | −0.8 dB | ~99% → ~95% (no ground) |
| EIN-derived SNR (17.5 vs 25 dB) | −0.2 dB | ~96% → ~95% (no ground) |
| Mic placement/phase error (severe: 20 mm / 45°) | PSR + error degrade measurably | Sets fabrication tolerance |
| Gain mismatch (any realistic level) | ~0 (PHAT-whitened) | Negligible |
| ISO 9613-1 absorption (20°C, 100 m) | ~0.5 dB at 1 kHz, ~2.3 dB at 4 kHz | Suppresses high harmonics at range |
| Refraction shadow zone (upwind, 200m) | 1–6 dB excess loss (now wired into signal chain) | Reduces detection at long range |
| Delany-Bazley ground vs constant coeff | Varies with θ, f | More nuanced than sharp cliff |
| Wind 10 m/s | −0.2 dB | Negligible |
| Turbulence 15 μs | −0.1 dB | Negligible |
| Amplitude scintillation | −0.1 dB | Negligible |
| Traffic "light" | −0.1 dB | Negligible |
| Birds 0.10 | −0.1 dB | Negligible |

**The dominant effect at short range (<50m) is ground reflection.** At longer ranges, atmospheric absorption becomes the primary range-limiting factor, preferentially attenuating higher BPF harmonics and narrowing the usable bandwidth for beamforming.

**Front/back rejection** (the reason for the dual-ring axial separation) is validated end-to-end: a planar ring shows ~0 dB mirror suppression and coin-flip confusion under noise, while 0.2 m spacing yields clear suppression and ~0 % confusion at high SNR. Quantify per candidate with `config/sweep/ring_spacing_frontback.yaml`.

A physics validation suite (`tests/test_physics_validation.py`) pins absorption to ISO table anchors, beamwidth to aperture scaling laws, steering to plane-wave geometry, and SRP-PHAT to exact known answers — refactors that silently change physics fail these tests.

## When to Trust the Results

| Scenario | Trust Level | Reason |
|---|---|---|
| Ground-free, high SNR | High | Well-understood physics, array gain dominates |
| Ground reflection (constant R, v5 scaling) | Medium-High | Amplitude cross-validated vs pyroomacoustics; the exact |R| is site-dependent |
| Delany-Bazley ground | Medium-High | Frequency-dependent impedance with per-mic incidence angle from image-source geometry; flow resistivity is an estimate |
| Wind noise (directional Corcos) | Medium-High | Streamwise/cross-stream coherence (α_ξ=0.15, α_η=0.75) with frozen-turbulence phase; Cholesky-generated random field is exact |
| Traffic / birds | Medium | Directional propagation is correct; real sources are more complex |
| Refraction shadow zone | Medium-High | ISO 9613-2 model wired into propagation pipeline alongside absorption; verified for consistency |
| Short-to-medium range (< 200 m) | Medium-High | Absorption + refraction + turbulence modeled per standards |
| Long range (200–500 m) | Medium | Absorption and refraction are correct; terrain/obstacles not modeled |
| Precipitation | None | Not modeled at all |
