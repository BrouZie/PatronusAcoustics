# SRP-PHAT Beamforming

## Vectorized Implementation (`SRPPhatProcessor`)

Standard SRP-PHAT loops over frequency bins, computing steering vectors and correlations per bin. This implementation replaces that loop with a **precomputed 3D phase tensor** and two vectorized `einsum` calls.

## Phase Tensor

At construction time, the processor precomputes:

```
phase[f, m, d] = exp(-j · 2π · f · τ[m, d])
```

where:
- `f` = frequency bin index (up to `max_freq`)
- `m` = microphone index (1…16)
- `d` = search direction index (up to 3721 at 2° resolution)
- `τ[m, d]` = steering delay for mic `m` toward direction `d`

**Memory**: ~163 MB (complex128, 171 freq × 16 mics × 3721 dirs at 2°). Halved at 4° resolution.

## Per-Frame Processing

For each frame of `(n_mics × fft_size)`:

1. **Windowing + FFT**: Hann window, RFFT, extract bins up to `max_freq`
2. **PHAT normalization** (optional): `X[f,m] /= |X[f,m]|` — removes amplitude, keeps phase
3. **Beamform**: `beam[f,d] = einsum("mf,fmd->fd", X, phase)` — project onto all directions
4. **Power sum**: `power[d] = einsum("fd,f->d", |beam|², weight)` — sum across freqs
5. **Reshape** `power` → 2D SRP map `(n_az × n_el)`
6. **Peak find**: locate maximum in the SRP map
7. **Detection gate**: P2M or PSR threshold

## Detection Gate

The detection gate controls which frames are counted as valid detections:

| Method | Config Value | Behavior |
|---|---|---|
| Peak-to-mean | `peak_to_mean` | `10·log₁₀(peak / mean(SRP_map)) >= threshold_db` |
| PSR | `psr` | `10·log₁₀(peak / max_sidelobe) >= threshold_db` |

Default: peak-to-mean with 5 dB threshold. Only detected frames contribute to angular error statistics.

## Config Reference

```yaml
srpphat:
  fft_size: 2048            # FFT window length (samples)
  hop_length: 512           # frame stride (samples)
  search:
    azimuth_range: [-60, 60]    # search bounds (deg)
    elevation_range: [-60, 60]
    resolution_deg: 2.0         # grid step (deg)
  max_freq: 4000.0          # upper frequency bound (Hz)
  mode: "phat"              # "phat" or "standard"
  frequency_weight: 0.0     # 0=flat, 0.5=sqrt, 1=linear, 2=quadratic
  detection:
    enabled: true
    method: peak_to_mean
    peak_to_mean_threshold_db: 5.0
```

## Performance

| Resolution | Directions | Max Freq | Phase Tensor | Frame Time |
|---|---|---|---|---|
| 2° | 61×61 = 3721 | 4000 Hz | ~163 MB | ~2.2 ms |
| 4° | 31×31 = 961 | 2000 Hz | ~10 MB | ~1.1 ms |
| 4° | 31×31 = 961 | 4000 Hz | ~21 MB | ~1.5 ms |

Total benchmark run (2s stationary, 4°, 2 kHz): **0.5–0.9 s** (~185 frames).
