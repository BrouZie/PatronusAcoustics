# Configuration System

The simulation uses YAML configuration files validated through a hierarchy of **Pydantic v2 `BaseModel`** classes in the `src/config/` package.

| File | Purpose |
|---|---|
| `__init__.py` | Re-exports all models, `deep_merge`, `parse_dotted_key`, `config_hash` |
| `models.py` | Pydantic models with `Field(ge=..., le=..., description=...)`, `json_schema_extra` for unit metadata; the array-config union |
| `merge.py` | `deep_merge()`, `parse_dotted_key()` |
| `hash.py` | `config_hash()` — SHA-256 of the JSON-serialized config dict (keys the results cache) |

## Loading Order

1. **YAML file** → raw dict via `yaml.safe_load()`
2. **CLI overrides** → nested override dict via `apply_overrides()` (e.g., `--snr 25`, `--quick`, `--ring1-radius 0.5`)
3. **Deep merge** → `deep_merge(base_dict, overrides)`
4. **Pydantic construction** → `Config.from_dict(merged_dict)` validates and structures the result

## Array Config Union

`array` is a discriminated union on `array.type`:

| Type | Model | Fields |
|---|---|---|
| `dual_ring` (default) | `DualRingArrayConfig` | `ring1_radius`, `ring2_radius`, `n_mics_ring1`, `n_mics_ring2`, `ring_spacing` |
| `single_ring` | `SingleRingArrayConfig` | `radius`, `n_mics`, `z_offset` |
| `xyz` | `ArbitraryArrayConfig` | `positions` (list of `[x,y,z]`) **or** `csv_path` (exactly one) |

- YAML without a `type` key validates as `dual_ring` (backward compatible).
- Array models use `extra="forbid"` — unknown keys are rejected instead of silently dropped.
- `ArrayConfig` remains as an alias of `DualRingArrayConfig` for existing code.
- `deep_merge` cannot switch union variants (it would mix incompatible keys); to change the type, replace the whole `array:` section — `src/compare.py` does this automatically for its override fragments.

## Validation Highlights

`@field_validator` / `@model_validator` enforce, among others:
- `srpphat.fft_size` power of 2; `hop_length ≤ fft_size`; `min_freq < max_freq`
- `srpphat.search` ranges ordered `[min, max]`; `coverage` presets (`front_hemisphere`, `full_sphere`) overwrite the explicit ranges
- `detection.method`, `srpphat.mode`, `noise.traffic_density`, `ground.model` enums
- `drone.initial_bearing` must contain `azimuth_deg` and `elevation_deg`
- `array` xyz variant: exactly one of `positions`/`csv_path`, ≥ 2 mics

## Schema Generation

```bash
python -m src.main --dump-schema
```

```python
from src.config import Config
schema = Config.model_json_schema()   # JSON Schema (with unit metadata)
text = Config.schema()                # human-readable text schema
```

The dashboard's configuration form is generated from `model_json_schema()`, including the array-type selector for the union.

## Sweep Overrides

The sweep runner (`src/sweep.py`) follows the same pattern:

```
base YAML → deep_merge(overrides) → deep_merge(sweep_combo) → Config.from_dict()
```

## Utilities

- **`deep_merge(base, override)`** — recursive dict merge; nested dicts merge, scalars/arrays override (note: an empty dict override merges nothing — it cannot *clear* a section)
- **`parse_dotted_key("environment.ground.height_m", 3.0)`** — dot-notation to nested dict
- **`config_hash(config)`** — deterministic 12-hex-char fingerprint; identical configs share cached results. Any model change (even adding a defaulted field) changes all hashes; physics changes without config changes are handled by `CACHE_SCHEMA_VERSION` in `src/results/cache.py`.

## Config Sections

| Section | Pydantic Model | Key Parameters |
|---|---|---|
| `array` | union (see above) | geometry |
| `signal` | `SignalConfig` | `fs`, `duration`, `snr_db` (None = EIN budget), `drone_spl_db`, `seed` (reproducible runs) |
| `mic` | `MicConfig` | `snr_dba`, `sensitivity_dbFS`, `aop_db_spl`, `imperfections` (gain/phase/position/quantization/failed mics/seed) |
| `drone` | `DroneConfig` | `rpm`, `num_blades`, `num_rotors`, `distance`, `initial_bearing`, `trajectory`, `bpf_harmonics` |
| `srpphat` | `SRPPhatConfig` | `fft_size`, `hop_length`, `search` (incl. `coverage`), `min/max_freq`, `mode`, `detection` |
| `environment` | `EnvironmentConfig` | `enabled`, `ground`, `noise` (wind/traffic/birds/ambient + Corcos alphas + source distances), `atmospheric` (drives speed of sound + absorption), `refraction`, `turbulence` (incl. phase-jitter and scintillation time constants) |
| `output` | `OutputConfig` | animation/figure/data save flags |

## Override Precedence

CLI flags > sweep parameters > sweep overrides > YAML file > Pydantic model defaults

## Available Config Files

| File | Purpose |
|---|---|
| `config/default.yaml` | Full realistic reference: environment enabled, oscillating drone, ICS-52000 imperfections |
| `config/quick.yaml` | Fast iteration: 4 s, 4° grid, 2 kHz, no output files |
| `config/benchmark.yaml` | Minimal stationary benchmark |
| `config/compare/*.yaml` | Geometry fragments for `src.compare` (dual-ring spacings, 16-mic single ring) |
| `config/sweep/ring_spacing_vs_range.yaml` | The fabrication question: spacing × distance |
| `config/sweep/ring_spacing_frontback.yaml` | Spacing × distance at full-sphere coverage → front/back metrics |
| `config/sweep/detection_range*.yaml` | Distance sweeps (full vs optimal band) |
| `config/sweep/mounting_height.yaml` | Height × ground model |
| `config/sweep/gate_threshold.yaml` | Detection threshold |
| `config/sweep/freq_band.yaml` | SRP band limits |
| `config/sweep/array.yaml`, `atmospheric.yaml`, `distance.yaml`, `ground.yaml` | Further single-topic sweeps |
