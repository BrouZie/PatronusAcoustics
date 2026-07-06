# Experiments

The parameter sweep runner (`python -m src.sweep config/sweep/<topic>.yaml`) makes it easy to run structured experiments over any config path. Each run produces a CSV with per-run aggregate metrics, ready for analysis in pandas, Excel, or your tool of choice.

Sweep YAML files live in `config/sweep/` — see [config.md](config.md) for the format.

For geometry decisions specifically, prefer the higher-level tools in [analysis.md](analysis.md) (`make compare-baseline`, `run_range_curve`) — sweeps remain the tool for open-ended exploration.

## Provided Sweep Configs

| Config | Params | Question |
|---|---|---|
| `config/sweep/ring_spacing_vs_range.yaml` | ring spacing × distance | **The fabrication question**: how does spacing trade against range? |
| `config/sweep/ring_spacing_frontback.yaml` | ring spacing × distance (full sphere) | How much front/back rejection does axial separation buy? |
| `config/sweep/mounting_height.yaml` | height × ground model (constant R / Delany-Bazley) | How does mounting height affect detection through ground multipath? |
| `config/sweep/gate_threshold.yaml` | PSR threshold (2–10 dB, 3 distances) | Does PSR gate threshold limit detection range? |
| `config/sweep/freq_band.yaml` | min_freq × max_freq | Which frequency band maximises detection rate? |
| `config/sweep/detection_range.yaml` | source distance (full band) | Max reliable detection range (full band)? |
| `config/sweep/detection_range_optimal.yaml` | source distance (500–2000 Hz band) | Max reliable detection range (optimal band)? |
| `config/sweep/array.yaml`, `atmospheric.yaml`, `distance.yaml`, `ground.yaml` | single-topic | Further exploration |

Tip: set `signal.seed` in sweep `overrides:` for reproducible rows, and sweep `signal.seed: [0, 1, 2]` to measure run-to-run variance.

## Completed Experiments

> **Staleness caveat**: the result numbers below were produced before the mid-2026 physics refactor (ISO absorption fix, sensor imperfections in `default.yaml`, sensor-chain rework). Trends and rankings hold; absolute rates — especially long-range, full-band results — should be re-run before being quoted. The results cache versioning (v4) already ignores pre-fix cached runs.

These are documented with full results in [design_validation.md](design_validation.md).

### Mounting Height & Ground Reflection

`config/sweep/mounting_height.yaml` — Height (0.3–5.0 m) × ground model (constant R=0.8 vs Delany-Bazley grass).

- **Constant ground**: detection flat at 47–52% across all heights — mounting height is not a significant factor with coherent ground reflection
- **Delany-Bazley grass**: 0% detection at all heights — physically correct grass absorption destroys beamforming coherence
- **Practical takeaway**: design assuming absorptive ground; choose height (1.5–3.0 m) by wind noise shielding and deployment convenience, not detection performance

### Frequency Band Analysis

`config/sweep/freq_band.yaml` — min_freq (0–700 Hz) × max_freq (1500–3000 Hz).

- Sub-300 Hz frequencies **degrade** detection (100% → 64–89%) due to wind/environmental noise
- Optimal band: **300–2000 Hz** (100% detection, 6.1° error)
- Recommended band: **500–2000 Hz** (rejects all wind noise, captures BPF harmonics 3–10, beamwidth 21.7°)

### Detection Range

`config/sweep/detection_range.yaml` and `config/sweep/detection_range_optimal.yaml` — distance 10–500 m.

- Full band (0–3000 Hz): detection drops to 0% at 100 m
- Optimal band (500–2000 Hz): **100% detection to 75 m**, 92% at 100 m, 64% at 150 m
- **3× range improvement** from optimised band alone

### Gate Threshold Tuning

`config/sweep/gate_threshold.yaml` — PSR threshold 2–10 dB × distances 20/50/100 m.

- PSR threshold has **negligible effect** (58–63% at 20 m, 25–29% at 50 m across all thresholds)
- PSR distribution is bimodal: either > 10 dB or < 2 dB — the threshold is not the limiting factor
- **6 dB** recommended as standard practice

## Experiment Ideas

### 1. Array Geometry × Bandwidth Cross

The freq band sweep used the default dual-ring geometry (8+16 mics, 0.13/0.26 m radii). Does the optimal band change for different array sizes?

```yaml
base_config: config/noisy_oscillating.yaml
overrides:
  srpphat.min_freq: 500
sweep:
  srpphat.max_freq: [1500, 2000, 3000, 4000]
  array.ring1_radius: [0.065, 0.13, 0.26]
output: results/sweep_array_bandwidth.csv
```

Hypothesis: Larger aperture arrays benefit from higher max_freq (better spatial resolution) while compact arrays may need a lower max_freq to avoid aliasing.

### 2. Atmospheric Absorption vs Range

The detection range sweeps used default humidity (50%). At high frequencies and long ranges, absorption becomes significant. Sweep humidity at marginal ranges (100–200 m):

```yaml
base_config: config/sweep/detection_range_optimal.yaml
overrides:
  drone.distance: 150
sweep:
  environment.humidity_pct: [20, 50, 80, 100]
output: results/sweep_humidity.csv
```

### 3. SNR Sweep at Fixed Range

Determine the minimum SNR required for reliable detection at a given range:

```yaml
base_config: config/noisy_oscillating.yaml
overrides:
  drone.distance: 100
  srpphat.min_freq: 500
  srpphat.max_freq: 2000
sweep:
  signal.snr_db: [5, 10, 15, 20, 25, 30]
output: results/sweep_snr.csv
```

### 4. Trajectory × Environment Cross

Does the oscillating trajectory (varying distance) give a different aggregate detection rate than a fixed-distance arc or a linear flyby?

```yaml
base_config: config/default.yaml
overrides:
  environment: {enabled: true}
sweep:
  drone.trajectory.type: ["arc", "oscillating", "flyby"]
output: results/sweep_trajectory.csv
```

### 5. Random Array vs Dual-Ring

Compare the baseline dual-ring with alternative layouts at the same mic budget. This no longer requires new code — use the `xyz` array type with generated positions, or better, run it through the compare CLI:

```bash
python -m src.compare config/compare/dual_ring_s20.yaml my_random_array.yaml \
    --distances 10 20 30 50
```

where `my_random_array.yaml` contains an `array: {type: xyz, positions: [...]}` section.

### 6. Windscreen Directionality Validation

Quantify the wind noise asymmetry from a one-sided windscreen by comparing forward vs rear-mic coherence at various wind speeds. The current simulation assumes symmetric wind noise. A windscreen effect could be modelled by reducing wind amplitude on the rear half of mics:

```yaml
base_config: config/noisy_oscillating.yaml
overrides:
  noise.wind_speed_ms: 5.0
sweep:
  noise.wind_shielding_db: [0, 3, 6, 10]
output: results/sweep_windscreen.csv
```

Requires adding a `wind_shielding_db` parameter to the noise config.

## Analysis Tips

- **Detection rate** is your primary metric. Everything else (angular error, PSR) only matters on detected frames.
- **Mean angular error** on detected frames may be artificially low when only high-SNR frames pass the gate. Compare with raw (ungated) error for the full picture.
- **Run time** scales roughly linearly with `duration × (1/resolution²) × (max_freq / fs) × n_mics`. The benchmark config runs in ~0.3s; a full 15s/2°/4kHz run takes ~24s.
- **Statistical variation**: Set `signal.seed` for reproducible runs and sweep the seed itself to measure variance (range curves in `src/analysis` average over seeds automatically).
- **Optimal band** (500–2000 Hz) should be the default for any realistic assessment; full-band (0–3000 Hz) results are significantly pessimistic.
