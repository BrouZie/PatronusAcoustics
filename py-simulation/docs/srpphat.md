# SRP-PHAT Beamforming

## Vectorized Implementation (`SRPPhatProcessor`)

Standard SRP-PHAT loops over frequency bins, computing steering vectors and correlations per bin. This implementation replaces that loop with a **precomputed 3D phase tensor** and two vectorized `einsum` calls (or the C++ `_srp` extension when built).

## Phase Tensor

At construction time, the processor precomputes:

```
phase[f, m, d] = exp(-j · 2π · f · τ[m, d])
```

where `τ[m, d]` is the steering delay for mic `m` toward direction `d`, computed from the array's **nominal** positions (the DSP only knows the design; propagation uses the as-built positions — see [array.md](array.md)).

**Memory**: `n_freqs × n_mics × n_dirs × 8 B` (complex64 on the numpy path; complex128 when the C++ extension is active — it requires double precision). Examples at 16 mics, 4 kHz band (171 bins):

| Grid | Directions | complex64 | complex128 |
|---|---|---|---|
| ±60° @ 2° (default window) | 61×61 = 3 721 | ~78 MB | ~155 MB |
| full sphere @ 4° | 91×46 = 4 186 | ~87 MB | ~175 MB |
| full sphere @ 2° | 181×91 = 16 471 | ~344 MB | ~688 MB |

The same formula drives the on-station MCU feasibility estimates (`src/analysis/mcu_requirements.py` — per-stage, multi-target verdicts with memory placement; see [mcu.md](mcu.md)).

## Search Coverage

```yaml
srpphat:
  search:
    coverage: window          # window | front_hemisphere | full_sphere
    azimuth_range: [-60, 60]      # used only by 'window'
    elevation_range: [-60, 60]
    resolution_deg: 2.0
```

- **Convention**: elevation is the polar angle from boresight — 0° = boresight, 90° = ring plane, 180° = directly behind the array.
- `front_hemisphere` expands to az ∈ [−180°, 180°], el ∈ [0°, 90°]; `full_sphere` to el ∈ [0°, 180°].
- **Full sphere is required** for the front/back metrics (`mean_mirror_suppression_db`, `front_back_confusion_rate`) — a front-only grid is structurally incapable of measuring mirror ambiguity. Use 4° resolution unless you need finer (see memory table).
- On full-circle azimuth grids the processor sets `wrap_az`, making the PSR mainlobe exclusion wrap across the ±180° seam (a peak at the seam must not count its own wrapped mainlobe as a sidelobe).
- **Comparability**: PSR/beamwidth shift with coverage — hold `coverage` fixed within any sweep or comparison.

## Per-Frame Processing

For each frame of `(n_mics × fft_size)`:

1. **Windowing + FFT**: Hann window, RFFT, extract bins in `[min_freq, max_freq]`
2. **PHAT normalization** (optional): `X[f,m] /= |X[f,m]|` — removes amplitude, keeps phase
3. **Beamform**: `beam[f,d] = einsum("mf,fmd->fd", X, phase)`
4. **Power sum**: `power[d] = einsum("fd,f->d", |beam|², weight)`
5. **Reshape** → 2D SRP map `(n_az × n_el)`
6. **Peak find** + **detection gate** (P2M or PSR threshold)

## Detection Gate

| Method | Config Value | Behavior |
|---|---|---|
| Peak-to-mean | `peak_to_mean` | `10·log₁₀(peak / mean(SRP_map)) ≥ threshold_db` |
| PSR | `psr` | `10·log₁₀(peak / max_sidelobe) ≥ threshold_db` (wrap-aware) |

Default: peak-to-mean with 5 dB threshold. Only detected frames contribute to angular error statistics.

## Config Reference

```yaml
srpphat:
  fft_size: 2048            # FFT window length (samples, power of 2)
  hop_length: 512           # frame stride (samples)
  search:
    coverage: window
    azimuth_range: [-60, 60]
    elevation_range: [-60, 60]
    resolution_deg: 2.0
  max_freq: 4000.0          # upper frequency bound (Hz)
  min_freq: 0.0             # lower bound (500 recommended — see design_validation.md)
  mode: "phat"              # "phat" or "standard"
  frequency_weight: 0.0     # 0=flat, 0.5=sqrt, 1=linear, 2=quadratic
  detection:
    enabled: true
    method: peak_to_mean
    peak_to_mean_threshold_db: 5.0
```

## PHAT and Hardware Mismatch

Because PHAT whitens each channel's magnitude, per-mic **gain** mismatch has almost no effect on the SRP map. **Phase** mismatch and mic **placement error** directly corrupt the steering alignment and are the imperfections that matter — model them via `mic.imperfections` ([snr.md](snr.md)).
