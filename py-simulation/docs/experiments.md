# Experiments

The parameter sweep runner (`python -m src.sweep config/sweep_<topic>.yaml`) makes it easy to run structured experiments over any config path. Each run produces a CSV with per-run aggregate metrics, ready for analysis in pandas, Excel, or your tool of choice.

## Provided Sweep Configs

| Config | Params | Combos | Question |
|---|---|---|---|
| `config/sweep_ground.yaml` | coeff × tilt | 15 | Where is the ground-reflection cliff? |
| `config/sweep_distance.yaml` | distance × wind | 12 | What is the max reliable detection range? |
| `config/sweep_array.yaml` | ring1_radius × n_mics | 12 | What is the minimum viable array? |

## How to Run

```bash
# Run the ground sweep
python -m src.sweep config/sweep_ground.yaml

# Preview combinations first
python -m src.sweep config/sweep_ground.yaml --dry-run
```

Results go to `results/{sweep_name}_{timestamp}/sweep_results.csv` by default (override with the optional `output:` key in the YAML). Each row contains the swept parameter values plus detection_rate, mean/max angular error, PSR, beamwidth, effective SNR, and wall-clock time.

## Experiment Ideas

### 1. Detection Cliff Chart

Run `config/sweep_ground.yaml` (5 coeff × 3 tilt = 15 runs). Plot `detection_rate` vs `coeff` for each `tilt_deg`. Expect a sharp transition between coeff=0.02 and 0.05. This quantifies the margin your deployment site needs.

### 2. Frequency Weighting vs Multipath

Modify a sweep config to vary `srpphat.frequency_weight` (0, 0.5, 1.0, 2.0) at a fixed coeff=0.05. Does emphasizing high frequencies improve P2M? The hypothesis: higher frequencies have shorter wavelengths, so the path-length difference spans more λ/2 cycles — some frequencies may avoid the null.

```yaml
# config/sweep_freqweight.yaml
base_config: config/noisy_oscillating.yaml
sweep:
  srpphat.frequency_weight: [0, 0.5, 1.0, 2.0]
output: results/sweep_freqweight.csv
```

### 3. Trajectory × Environment Cross

Run the same environment settings (e.g., `noisy_oscillating` ground + noise) with different trajectory types:

```yaml
base_config: config/default.yaml
overrides:
  environment: {enabled: true, ... fixed env ...}
sweep:
  drone.trajectory.type: ["arc", "oscillating", "flyby"]
output: results/sweep_trajectory.csv
```

Does the oscillating trajectory (varying distance) give a different aggregate detection rate than the arc (constant distance)?

### 4. Tilt Angle as a Mitigation Tool

Vary `ground.tilt_deg` from 0 to 45° at a fixed, punishing coeff=0.10. Some tilt angles may shift the comb-filter nulls away from the BPF harmonics:

```yaml
base_config: config/noisy_oscillating.yaml
sweep:
  ground.tilt_deg: [0, 5, 10, 15, 20, 25, 30, 45]
output: results/sweep_tilt.csv
```

### 5. Array Size vs. Ground Robustness

Using `config/sweep_array.yaml` (or extended), determine whether more mics or larger aperture provides more tolerance to ground reflection. Plot `detection_rate` vs `n_mics_ring1` for each `ring1_radius`.

### 6. Manual SNR vs. EIN-Derived

Compare results with `signal.snr_db: 25` (old manual default) vs `snr_db: null` (EIN-derived, ~17.5 dB at 15m) across the ground sweep. This shows the cost of using the physically correct noise floor vs the previously assumed one.

### 7. All Noise Sources On/Off

Isolate each noise source by varying which is enabled:

```yaml
base_config: config/noisy_oscillating.yaml
# Create variants that disable each source individually
sweep:
  noise.wind_speed_ms: [0, 1.5]
  noise.bird_activity: [0, 0.10]
  noise.ambient_db: [0, 10]
output: results/sweep_noise_breakdown.csv
```

## Analysis Tips

- **Detection rate** is your primary metric. Everything else (angular error, PSR) only matters on detected frames.
- **Mean angular error** on detected frames may be artificially low when only high-SNR frames pass the gate. Compare with raw (ungated) error for the full picture.
- **Run time** scales roughly linearly with `duration × (1/resolution²) × (max_freq / fs) × n_mics`. The benchmark config runs in ~0.5s; a full 15s/2°/4kHz run takes ~36s.
- **Statistical variation**: The simulation is deterministic given the same config. To assess variance, use `signal.snr_db` manual override and sweep `noise.wind_speed_ms` with small variations to see sensitivity.
