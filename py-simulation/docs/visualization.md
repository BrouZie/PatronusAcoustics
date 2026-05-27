# Visualization Output

The simulation produces three types of visual output: summary figures, 3D animations, and raw data files.

## Summary Figures (`output/*/figures/`)

Three static PNG files generated at the end of each run:

### 1. `srp_heatmap_average.png`

Time-averaged SRP-PHAT map across all frames. Azimuth vs elevation with true DOA (cyan cross) and mean estimated DOA (lime circle) overlaid. Shows the overall beampattern and sidelobe structure.

### 2. `doa_error_over_time.png`

Angular error (red line) versus time, with mean ±1σ band. Red-shaded regions indicate frames where the detection gate suppressed the estimate.

### 3. `metrics_summary.png`

Three-panel figure showing:
- **Left**: Peak-to-sidelobe ratio over time, with mean and detection threshold
- **Center**: 3 dB beamwidth over time
- **Right**: Summary text block with detection rate, mean/std/max angular error, mean PSR, mean beamwidth

## 3D Beamsphere Animation (`output/*/animations/`)

A rotating MP4 animation (`beamforming_3d.mp4`) with four panels:

| Panel | Content |
|---|---|
| **Beamsphere** | 3D spherical SRP map projected onto a sphere, with rotating camera. Array geometry shown at center. True DOA (cyan cross) and estimated DOA (lime circle) are connected to the origin with dashed/solid lines. Color intensity = SRP power. |
| **SRP Map** | 2D azimuth-elevation heatmap of the current frame. |
| **DOA Tracking** | True and estimated azimuth/elevation vs time, with vertical cursor at current frame. Red-shaded regions = suppressed frames. |
| **Metrics Panel** | Static summary of aggregate metrics and configuration. |

Configuration: `output.animation_fps` (default 15). Disable with `--no-animation` or `output.save_animation: false`.

## Raw Data (`output/*/data/`)

All frame-level arrays saved as `simulation_results.npz`:

| Key | Shape | Description |
|---|---|---|
| `true_doas` | `(n_frames, 2)` | Ground-truth (azimuth, elevation) in radians |
| `estimated_doas` | `(n_frames, 2)` | Estimated (azimuth, elevation); NaN for suppressed frames |
| `srp_maps` | `(n_frames, n_az, n_el)` | Full SRP-PHAT map per frame |
| `peak_values` | `(n_frames,)` | SRP peak value per frame |
| `detections` | `(n_frames,)` | Boolean detection mask |
| `timestamps` | `(n_frames,)` | Center timestamp of each frame (seconds) |

## Controllable Output

```yaml
output:
  animation_fps: 15
  save_animation: true        # → animations/beamforming_3d.mp4
  save_3d_animation: true     # alias for save_animation
  save_figures: true          # → figures/*.png
  save_data: true             # → data/simulation_results.npz
```

All three output types can be independently enabled/disabled via config or CLI flags (`--no-animation`, `--no-figures`, `--quick`).
