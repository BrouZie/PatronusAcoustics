# Configuration System

The simulation uses YAML configuration files parsed into a hierarchy of frozen dataclasses (`Config`, `ArrayConfig`, `SignalConfig`, `DroneConfig`, `SRPPhatConfig`, `EnvironmentConfig`, `OutputConfig`).

## Loading Order

1. **YAML file** → raw dict via `yaml.safe_load()`
2. **CLI overrides** → nested override dict via `apply_overrides()` (e.g., `--snr 25`, `--quick`, `--ring1-radius 0.5`)
3. **Deep merge** → `deep_merge(base_dict, overrides)` applies CLI flags on top of file values
4. **Dataclass construction** → `Config.from_dict(merged_dict)` validates and structures the result

## Sweep Overrides

The sweep runner (`src/sweep.py`) follows the same pattern:

```
base YAML → deep_merge(overrides) → deep_merge(sweep_combo) → Config.from_dict()
```

Where `overrides` are fixed modifications and `sweep_combo` is one Cartesian-product element from the `sweep:` parameter lists.

## Utilities

- **`deep_merge(base, override)`** — recursive dict merge; nested dicts are merged, scalars/arrays override
- **`parse_dotted_key("ground.coeff", 0.03)`** — converts dot-notation to `{ground: {coeff: 0.03}}`
- **`Config.from_dict(data)`** — constructs full dataclass tree from a raw dict, applying defaults for missing keys

## Config Sections

| Section | Dataclass | Key Parameters |
|---|---|---|
| `array` | `ArrayConfig` | ring radii, mic counts, ring spacing |
| `signal` | `SignalConfig` | fs, duration, snr_db, drone_spl_db |
| `mic` | `MicConfig` | snr_dba, sensitivity_dbFS, aop_db_spl |
| `drone` | `DroneConfig` | rpm, blades, rotors, distance, trajectory, motion |
| `srpphat` | `SRPPhatConfig` | fft_size, hop_length, search grid, max_freq, mode, detection |
| `environment` | `EnvironmentConfig` | ground params, noise params (wind/traffic/birds/ambient) |
| `output` | `OutputConfig` | animation/figure/data save flags |

## Override Precedence

CLI flags > sweep parameters > sweep overrides > YAML file > dataclass defaults

## Available Config Files

| File | Purpose |
|---|---|
| `config/default.yaml` | Full reference config (environment disabled) |
| `config/benchmark.yaml` | Minimal 2s stationary benchmark (fast) |
| `config/noisy_oscillating.yaml` | Realistic default: oscillating drone + environment |
| `config/oscillating_drone.yaml` | Oscillating trajectory, environment disabled |
| `config/moving_drone.yaml` | Flyby trajectory, environment disabled |
| `config/prototype.yaml` | Oscillating + environment (coeff=0.05, light traffic) |
| `config/16_prototype.yaml` | 16+16 mic array + environment |
| `config/sweep_ground.yaml` | Sweep: ground reflection |
| `config/sweep_distance.yaml` | Sweep: detection range |
| `config/sweep_array.yaml` | Sweep: array geometry |
