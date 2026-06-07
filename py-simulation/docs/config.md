# Configuration System

The simulation uses YAML configuration files validated through a hierarchy of **Pydantic v2 `BaseModel`** classes (`Config`, `ArrayConfig`, `SignalConfig`, `DroneConfig`, `SRPPhatConfig`, `EnvironmentConfig`, `OutputConfig`) in the `src/config/` package.

Formerly a single `config.py` with hand-rolled frozen dataclasses (48 `_check()` methods), the config system was migrated to Pydantic v2. The `src/config/` package now contains:

| File | Purpose |
|---|---|
| `__init__.py` | Re-exports all models, `deep_merge`, `parse_dotted_key`, `config_hash` |
| `models.py` | 15 Pydantic `BaseModel` classes with `Field(ge=..., le=..., description=...)`, `json_schema_extra` for unit metadata |
| `merge.py` | `deep_merge()`, `parse_dotted_key()` (unchanged from legacy) |
| `hash.py` | `config_hash()` — SHA-256 of JSON-serialized config dict |

## Loading Order

1. **YAML file** → raw dict via `yaml.safe_load()`
2. **CLI overrides** → nested override dict via `apply_overrides()` (e.g., `--snr 25`, `--quick`, `--ring1-radius 0.5`)
3. **Deep merge** → `deep_merge(base_dict, overrides)` applies CLI flags on top of file values
4. **Pydantic construction** → `Config.from_dict(merged_dict)` validates and structures the result

### Validation

Pydantic `@field_validator` methods enforce:
- `signal.fs` must be a power of 2
- `srpphat.mode` in `{"phat", "standard"}`
- `detection.method` in `{"peak_to_mean", "peak_to_sidelobe", "threshold"}`
- `noise.traffic_density` in `{"none", "light", "moderate", "heavy"}`
- `drone.initial_bearing` has both `azimuth_deg` and `elevation_deg` when present
- `srpphat.search.range_deg` is ordered `[min, max]`

Pydantic `@model_validator(mode="after")` enforces cross-field constraints:
- `srpphat` hop_length ≤ fft_size, min_freq < max_freq
- `drone.motion` velocity vector has correct length (0, 2, or 3)

## Schema Generation

The full configuration schema can be dumped as human-readable text:

```bash
python -m src.main --dump-schema
```

Programmatic access:

```python
from src.config import Config

# Pydantic JSON Schema (with units in json_schema_extra)
schema = Config.model_json_schema()

# Custom human-readable text schema
text = Config.schema()
```

## Sweep Overrides

The sweep runner (`src/sweep.py`) follows the same pattern:

```
base YAML → deep_merge(overrides) → deep_merge(sweep_combo) → Config.from_dict()
```

Where `overrides` are fixed modifications and `sweep_combo` is one Cartesian-product element from the `sweep:` parameter lists.

## Utilities

- **`deep_merge(base, override)`** — recursive dict merge; nested dicts are merged, scalars/arrays override
- **`parse_dotted_key("ground.coeff", 0.03)`** — converts dot-notation to `{ground: {coeff: 0.03}}`
- **`Config.from_dict(data)`** — constructs full Pydantic model tree from a raw dict, applying defaults for missing keys
- **`config_hash(config)`** — deterministic SHA-256 fingerprint (12 hex chars) of a Config, used by the simulation cache

## Config Sections

| Section | Pydantic Model | Key Parameters |
|---|---|---|
| `array` | `ArrayConfig` | ring radii, mic counts, ring spacing |
| `signal` | `SignalConfig` | fs, duration, snr_db, drone_spl_db |
| `mic` | `MicConfig` | snr_dba, sensitivity_dbFS, aop_db_spl |
| `drone` | `DroneConfig` | rpm, blades, rotors, distance, trajectory, motion |
| `srpphat` | `SRPPhatConfig` | fft_size, hop_length, search grid, max_freq, mode, detection |
| `environment` | `EnvironmentConfig` | ground params, noise params (wind/traffic/birds/ambient) |
| `output` | `OutputConfig` | animation/figure/data save flags |

## Override Precedence

CLI flags > sweep parameters > sweep overrides > YAML file > Pydantic model defaults

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
| `config/sweep/mounting_height.yaml` | Sweep: mounting height × ground model |
| `config/sweep/gate_threshold.yaml` | Sweep: detection PSR threshold |
| `config/sweep/freq_band.yaml` | Sweep: SRP frequency band limits |
| `config/sweep/detection_range.yaml` | Sweep: detection range (full band, 0–3000 Hz) |
| `config/sweep/detection_range_optimal.yaml` | Sweep: detection range (optimal band, 500–2000 Hz) |

## Legacy

The old `src/config.py` (frozen dataclasses) has been deleted. All imports route through `src.config` which now points to the `src/config/` package. No backward-compatibility shims are provided.
