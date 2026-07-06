# Environmental Simulation

The environment model adds four noise types and a ground-reflection multipath model. All sound sources (directional noise + drone) propagate through the same delay-and-attenuation pipeline, creating spatially-correlated microphone signals that reflect real acoustic environments.

When the environment is enabled, the **speed of sound follows Cramer (1993)** from the configured temperature, humidity, and pressure (`speed_of_sound(T, humidity_pct, pressure_kPa)` in `src/constants.py`; anchors pinned in `tests/test_physics_validation.py`) and is injected everywhere — steering, propagation, image sources, noise sources — so all delays agree. With the environment disabled, the 343 m/s reference is used.

**Units**: in the default calibrated mode (`signal.snr_db: null`, see [snr.md](snr.md)) every noise source below emits calibrated pressure in Pa (dB SPL levels as stated). With the legacy `snr_db` override the pre-v5 empirical scale factors are used instead.

## Ground Reflection

```yaml
environment:
  ground:
    height_m: 5.0            # array mast height above ground (m)
    tilt_deg: 15.0           # boresight tilt from horizontal
    reflection_coefficient: 0.9   # ground |R| (0-1); 0.9 ≈ grassland at LF
```

- **Model**: Image-source. The drone's position is mirrored below the ground plane; both direct and reflected paths propagate to every mic. The reflected pressure is `−R/d_image` (phase-inverted, pressure-release convention) against the direct path's `1/d_direct` — validated against pyroomacoustics in `tests/test_crossval_pyroomacoustics.py`.
- **Effect**: Creates a frequency-dependent comb filter. Frequencies where the path-length difference Δd = (2n+1)·λ/2 cancel; those where Δd = n·λ reinforce. The drone's BPF harmonics (200, 400, 600, …, 1200 Hz) are particularly susceptible because they're narrowband and strongly tonal.
- **Key finding**: This is the **single dominant degradation** in the simulation — the reflected arrival is nearly as strong as the direct one (`R·d_direct/d_image` ≈ 0.9 for elevated geometries), the comb nulls track the fixed mast/tilt geometry, and PHAT whitening cannot suppress a perfectly correlated copy of the signal.

> **v5 amplitude fix**: pre-v5 code scaled the reflected path by `R·d_direct/d_image` applied to the *unattenuated* source — a ~`d_direct`× (often 20–30×) overshoot. Old configs compensated with unphysically small `reflection_coefficient` values (0.03–0.05); those numbers produced roughly the right direct/reflected *ratio* for ~30 m scenarios but broke as soon as distance changed. With the corrected `R/d_image` scaling, use physical values (grass ≈ 0.9 at LF, or the `delany_bazley` model). Results cached before schema v5 are ignored automatically. The pre-v5 detection-rate anchors quoted in older reports were measured with the compensated coefficients and remain qualitatively valid at their original geometry.

### Why Ground Reflection is So Effective

The sharp detection cliff exists because the comb-filter null frequencies depend on the mast height, tilt angle, and drone elevation — parameters that are fixed or slowly varying. The nulls align with the BPF harmonics and stay aligned, causing sustained amplitude reduction in the frequencies the SRP-PHAT processor relies on. Unlike uncorrelated noise (which PHAT whitening suppresses), the reflected signal is perfectly correlated with the direct signal, so beamforming cannot separate them.

## Wind Noise (Corcos Model)

```yaml
noise:
  wind_speed_ms: 1.5        # wind speed (m/s)
  wind_direction_deg: 0.0   # azimuth: 0=front, 90=right
```

- **Model**: Corcos turbulence coherence — `γ_ij(f) = exp(-α · f · d_ij / U)`. The streamwise/cross-stream decay constants are configurable (`noise.corcos_alpha_xi` = 0.15, `noise.corcos_alpha_eta` = 0.75 by default).
- **Generation**: Cholesky decomposition of the coherence matrix at each positive frequency bin produces a correlated random field at the microphone positions, transformed to time domain via IFFT.
- **Spectral envelope**: Brown noise (1/f²) with single-pole LPF @ 500 Hz.
- **Level (calibrated mode)**: dynamic-pressure scaling `p_rms = Ct·(½ρU²)·10^(−IL/20)` with `Ct ≈ 0.1` for a bare mic (Strasberg 1988; Raspet et al. 2006) — 5 m/s bare ≈ 97 dB SPL, pinned in `tests/test_physics_validation.py`. `noise.windscreen_il_db` (default.yaml: 20 dB foam screen) models the windscreen insertion loss; bare-mic wind noise at even moderate speeds otherwise dominates every other term in the budget, which is physically accurate and why real deployments need windscreens.
- **Correlation**: ~0.06 at 1 m/s (adjacent mics nearly decorrelated), ~0.4 at 5 m/s, ~0.8 at 20 m/s. Correlation decreases with mic separation (physically correct).
- **P2M impact**: < 0.2 dB even at 10 m/s. The drone's narrowband BPF harmonics dominate the PHAT-weighted SRP map, while wind noise is broadband and distributed. This is realistic — wind noise is readily suppressed by frequency-domain PHAT normalization.

## Traffic Noise

```yaml
noise:
  traffic_density: "light"      # none / light / moderate / heavy
  traffic_direction_deg: 90.0   # azimuth of road from array
```

- **Model**: Bandpass-filtered white noise (200–2000 Hz) at 0.1 Hz amplitude modulation (simulating varying engine load).
- **Position**: Point source at `noise.traffic_distance_m` (default 50 m) in the given azimuth direction. Propagates via FFT-based delay-and-attenuation (same as drone).
- **Level (calibrated mode)**: density → Leq at 10 m of {light 55, moderate 65, heavy 72} dB SPL (FHWA TNM / CNOSSOS-EU order of magnitude), emitted as the equivalent Pa RMS at 1 m so the shared 1/r propagation reproduces the class level at 10 m.
- **Reality note**: Traffic is static in this model — a real car has Doppler shift and evolving spectrum.

## Bird Chirps

```yaml
noise:
  bird_activity: 0.10       # chirp density (0-1)
```

- **Model**: Poisson-distributed FM chirps, linearly sweeping from random start (2–4 kHz) to random end (4–8 kHz), duration 100–250 ms.
- **Envelope**: Raised-cosine (sinusoidal) amplitude per chirp.
- **Level (calibrated mode)**: `noise.bird_spl_db` source level at 1 m (default 90 dB SPL — songbird order of magnitude, Brackenbury 1979).
- **Position**: `noise.bird_distance_m` (default 10 m) from the array at random azimuth within ±60° and elevation 50–80°.
- **Reality note**: Real bird calls are species-specific (not just linear sweeps). For detection-system testing this approximation is adequate.

## Ambient Noise

```yaml
noise:
  ambient_db: 30.0          # broadband floor in dB SPL (calibrated mode)
```

- **Model**: Per-channel uncorrelated pink noise (1/f spectrum). Diffuse — equivalent to infinite uncorrelated directions.
- **Level (calibrated mode)**: `ambient_db` is literally the broadband RMS in dB SPL (quiet rural night ≈ 25–35, suburban ≈ 45, urban ≈ 55+). Legacy mode keeps the old arbitrary 0–30 scale.

## Atmospheric Turbulence (Propagation Delay Jitter)

Real acoustic propagation includes random delay perturbations from temperature gradients and turbulent eddies. Modeled as an **Ornstein-Uhlenbeck process** per microphone channel:

```
dτ_m = −θ · τ_m · dt + σ · dW_m
```

- `turbulence.phase_jitter_std_us` (default 15 µs — RMS delay perturbation ≈ 0.7 samples at 48 kHz)
- `turbulence.phase_jitter_corr_ms` (default 50 ms — correlation time; scintillation has its own `scintillation_corr_ms`)
- **Stationary paths**: constant per-mic perturbation (FFT domain, computed once)
- **Moving paths**: time-varying per-sample perturbation (AR(1) via `scipy.signal.lfilter`, ~68 ms for 4s × 16 mics)
- **P2M impact**: ~0.1 dB — negligible for loud drones but would increase for quieter sources.

## Directional vs. Diffuse

| Source | Type | Spatial Correlation |
|---|---|---|
| Drone | Point source (FFT-propagated) | Full (same waveform, shifted) |
| Traffic | Point source (FFT-propagated) | Full |
| Birds | Point source (FFT-propagated) | Full |
| Wind | Distributed field (Cholesky) | Corcos coherence |
| Ambient | Diffuse (per-channel) | None |

## Atmospheric Absorption (ISO 9613-1)

`src/absorption.py` implements the ISO 9613-1 / ANSI S1.26 attenuation coefficient α(f, T, RH, P), applied as a frequency-domain pressure filter in the propagation pipeline and in the EIN SNR budget.

Representative values at 20 °C, 70 % RH, 1 atm (validated against published table anchors in `tests/test_physics_validation.py`):

| Frequency | α |
|---|---|
| 125 Hz | ~0.3 dB/km |
| 1 kHz | ~4.7 dB/km |
| 4 kHz | ~23 dB/km |

> **History note**: before mid-2026 the implementation mixed up the ISO humidity units (molar concentration in percent vs fraction) and Celsius/Kelvin in the nitrogen relaxation term, overestimating low-frequency absorption ~10× and underestimating 4 kHz ~3×. Results cached before cache schema v4 predate the fix and are ignored automatically.

Absorption is the dominant range-limiting physics beyond ~100 m, preferentially removing the higher BPF harmonics.

## Disabling the Environment

Set `environment.enabled: false`. The simulation will still generate per-mic sensor noise (derived from the mic's EIN — see [snr.md](snr.md)) but no ground reflection, environmental noise, absorption, or refraction.
