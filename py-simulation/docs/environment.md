# Environmental Simulation

The environment model adds four noise types and a ground-reflection multipath model. All sound sources (directional noise + drone) propagate through the same delay-and-attenuation pipeline, creating spatially-correlated microphone signals that reflect real acoustic environments.

## Ground Reflection

```yaml
environment:
  ground:
    height_m: 5.0            # array mast height above ground (m)
    tilt_deg: 15.0           # boresight tilt from horizontal
    reflection_coefficient: 0.03  # ground reflectivity (0-1)
```

- **Model**: Image-source. The drone's position is mirrored below the ground plane; both direct and reflected paths propagate to every mic. The reflection is phase-inverted (pressure-release boundary) and scaled by `coeff` × `1/r` attenuation.
- **Effect**: Creates a frequency-dependent comb filter. Frequencies where the path-length difference Δd = (2n+1)·λ/2 cancel; those where Δd = n·λ reinforce. The drone's BPF harmonics (200, 400, 600, …, 1200 Hz) are particularly susceptible because they're narrowband and strongly tonal.
- **Key finding**: This is the **single dominant degradation** in the simulation. At coeff=0.05 with EIN-derived SNR (17.5 dB at 15m) + ICS-52000 HPF @ 75 Hz:
  - coeff=0.00: P2M=5.3 dB, 96% detection
  - coeff=0.05: P2M=4.4 dB, 1% detection (below 5 dB threshold)
  - coeff=0.03: ~50% detection across oscillating trajectory (natural switching)
  - coeff=0.10: 0% detection (complete collapse)

### Why Ground Reflection is So Effective

The sharp detection cliff exists because the comb-filter null frequencies depend on the mast height, tilt angle, and drone elevation — parameters that are fixed or slowly varying. The nulls align with the BPF harmonics and stay aligned, causing sustained amplitude reduction in the frequencies the SRP-PHAT processor relies on. Unlike uncorrelated noise (which PHAT whitening suppresses), the reflected signal is perfectly correlated with the direct signal, so beamforming cannot separate them.

## Wind Noise (Corcos Model)

```yaml
noise:
  wind_speed_ms: 1.5        # wind speed (m/s)
  wind_direction_deg: 0.0   # azimuth: 0=front, 90=right
```

- **Model**: Corcos turbulence coherence — `γ_ij(f) = exp(-α · f · d_ij / U)` where α=0.15, d_ij is inter-mic distance, U is wind speed.
- **Generation**: Cholesky decomposition of the coherence matrix at each positive frequency bin produces a correlated random field at the microphone positions, transformed to time domain via IFFT.
- **Spectral envelope**: Brown noise (1/f²) with single-pole LPF @ 500 Hz.
- **Correlation**: ~0.06 at 1 m/s (adjacent mics nearly decorrelated), ~0.4 at 5 m/s, ~0.8 at 20 m/s. Correlation decreases with mic separation (physically correct).
- **P2M impact**: < 0.2 dB even at 10 m/s. The drone's narrowband BPF harmonics dominate the PHAT-weighted SRP map, while wind noise is broadband and distributed. This is realistic — wind noise is readily suppressed by frequency-domain PHAT normalization.

## Traffic Noise

```yaml
noise:
  traffic_density: "light"      # none / light / moderate / heavy
  traffic_direction_deg: 90.0   # azimuth of road from array
```

- **Model**: Bandpass-filtered white noise (200–2000 Hz) at 0.1 Hz amplitude modulation (simulating varying engine load).
- **Position**: Point source 50 m from array in the given azimuth direction. Propagates via FFT-based delay-and-attenuation (same as drone).
- **Amplitude**: `"light"` = 0.02 RMS, `"moderate"` = 0.05 RMS, `"heavy"` = 0.10 RMS at the source.
- **Reality note**: Traffic is static in this model — a real car has Doppler shift and evolving spectrum.

## Bird Chirps

```yaml
noise:
  bird_activity: 0.10       # chirp density (0-1)
```

- **Model**: Poisson-distributed FM chirps, linearly sweeping from random start (2–4 kHz) to random end (4–8 kHz), duration 100–250 ms.
- **Envelope**: Raised-cosine (sinusoidal) amplitude per chirp.
- **Position**: 10 m from array at random azimuth within ±60° and elevation 50–80°. Bird position is re-randomized per chirp.
- **Reality note**: Real bird calls are species-specific (not just linear sweeps). For detection-system testing this approximation is adequate.

## Ambient Noise

```yaml
noise:
  ambient_db: 10.0          # pink noise level (0-30)
```

- **Model**: Per-channel uncorrelated pink noise (1/f spectrum). Diffuse — equivalent to infinite uncorrelated directions.
- **Level**: Scale 0–30 (arbitrary; 5 = quiet room, 15 = noticeable, 25 = loud outdoor).

## Atmospheric Turbulence (Propagation Delay Jitter)

Real acoustic propagation includes random delay perturbations from temperature gradients and turbulent eddies. Modeled as an **Ornstein-Uhlenbeck process** per microphone channel:

```
dτ_m = −θ · τ_m · dt + σ · dW_m
```

- `τ_std = 15 μs` (RMS delay perturbation ≈ 0.7 samples at 48 kHz)
- `τ_corr = 50 ms` (correlation time of atmospheric turbulence)
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

## Disabling the Environment

Set `environment.enabled: false`. The simulation will still generate per-mic thermal noise (derived from the mic's EIN) but no ground reflection, environmental noise, or turbulence.
