# Usage Guide

## Quick Start

```bash
# Install dependencies (uses uv.lock for pinned versions)
uv sync

# Default realistic simulation (15s, environment, oscillating drone)
uv run python -m src.main

# Fast iteration (4s, coarse grid, 2 kHz, no output files)
uv run python -m src.main -c config/quick.yaml

# Benchmark / regression test (2s, stationary, no environment)
uv run python -m src.main -c config/benchmark.yaml

# Profile (top-20 cumtime)
uv run python -m src.main -c config/benchmark.yaml --profile

# Interactive dashboard
uv run streamlit run src/dashboard/app.py
```

## CLI Flags

| Flag | Effect |
|---|---|
| `-c, --config` | Config file path (default: `config/default.yaml`) |
| `-o, --output-dir` | Output root directory |
| `--run-name` | Custom run subfolder name |
| `--snr` | Override SNR (dB) |
| `--duration` | Override simulation duration (s) |
| `--azimuth, --elevation` | Override drone initial bearing |
| `--moving` | Enable drone motion |
| `--quick` | 4s, 4° resolution, 2 kHz max freq, no output files (same as `-c config/quick.yaml`) |
| `--no-animation` | Skip animation rendering |
| `--no-figures` | Skip summary figures |
| `--interactive` | Show interactive figure after saving |
| `--profile` | Profile with cProfile (top-20 cumtime) |
| `--dry-run` | Print run name and output path, don't run |
| `--dump-schema` | Print configuration schema with descriptions and defaults, then exit |
| `--ring1-radius, --ring2-radius, --n-mics-1, --n-mics-2, --ring-spacing` | Array geometry overrides |

## Interactive Dashboard

The Streamlit dashboard provides a GUI for the simulation:

```bash
uv run streamlit run src/dashboard/app.py
```

Three tabs:

1. **Simulation** — Auto-generated parameter form from Pydantic config schema (sliders for bounded numbers, checkboxes for booleans, selectboxes for enums, expanders for nested sub-configs). Quick/DEFAULT preset buttons. Cache-aware run (loads cached results when config unchanged). Results summary with metric cards and diagnostic plots (angular error timeline, PSR timeline, error distribution).

2. **Sweep Results** — Browse past sweep runs via `SweepCatalog`. View CSV data in a table, explore parameter vs metric relationships with interactive scatter plots.

3. **Educational** — Three interactive learning modules:
   - **Beamforming Basics**: Polar + cartesian beampattern plots, array geometry visualization, multi-frequency overlay, ULA comparison
   - **Ground Reflection**: Image source geometry, frequency response with interference notches, coherence vs range
   - **Array Geometry Tradeoffs**: Dual-ring vs ULA vs UCA vs Sparse comparison with metrics table

## Sweep Runner

```bash
# Run a sweep
uv run python -m src.sweep config/sweep/detection_range.yaml

# Preview combinations without running
uv run python -m src.sweep config/sweep/detection_range.yaml --dry-run

# Resume from checkpoint
uv run python -m src.sweep config/sweep/detection_range.yaml --resume

# Use 8 parallel workers
uv run python -m src.sweep config/sweep/detection_range.yaml --workers 8
```

Sweep configs live in `config/sweep/*.yaml`. Each references `config/default.yaml` as its base.
See [config.md](config.md) for the YAML format.

Each run creates a timestamped subfolder under `results/` containing:
- `sweep_results.csv` — incremental CSV with per-combination metrics
- `sweep_results.csv.state.json` — checkpoint state for resume

## Simulation Cache

Results are automatically cached in `results/cache/<config_hash>/`. When the same config is run again (e.g., from the dashboard), cached results are loaded instead of re-running. Clear the cache with:

```python
from src.results import clear_cache
clear_cache()          # clear all
clear_cache(config)    # clear specific
```

## Output Structure

Each run creates a dated subfolder under `output/`:

```
output/<run_name>/
├── data/
│   └── simulation_results.npz    # raw arrays (DOAs, SRP maps, detections)
├── animations/
│   └── beamforming_3d.mp4        # rotating 3D beamsphere animation
└── figures/
    ├── srp_heatmap_average.png    # time-averaged SRP map
    ├── doa_error_over_time.png    # angular error vs time
    └── metrics_summary.png        # PSR, beamwidth, detection rate
```

## Programmatic Access

```python
from src.config import Config
from src.results import SweepCatalog, cached_run, clear_cache

# Load and modify config
cfg = Config.from_yaml("config/default.yaml")

# Run with caching
results = cached_run(cfg)
metrics = results["metrics"]
print(f"Detection rate: {metrics.detection_rate:.1%}")

# Browse past sweeps
catalog = SweepCatalog()
for sweep in catalog.list_sweeps():
    df = catalog.to_dataframe(sweep)
    print(sweep.name, df["detection_rate"].mean())

# Dump config schema
print(Config.schema())
```

## Provided Config Files

| Command | Scenario | Duration | Time (C++) |
|---|---|---|---|---|
| *(none — loads `config/default.yaml`)* | 15s oscillating + environment (ICS-52000) | 15s | **~23.6s** |
| `-c config/quick.yaml` | 4s, 4° grid, 2 kHz, no output | 4s | ~2s |
| `-c config/benchmark.yaml` | 2s stationary, SNR=25, 4°, 2 kHz | 2s | ~0.3s |

| Sweep config | Parameters swept | Combos |
|---|---|---|
| `config/sweep/mounting_height.yaml` | Height × ground model (constant/Delany-Bazley) | 16 |
| `config/sweep/gate_threshold.yaml` | PSR threshold (2–10 dB) | 18 |
| `config/sweep/freq_band.yaml` | Min/max frequency band limits | 12 |
| `config/sweep/detection_range.yaml` | Source distance (10–300 m, full band) | 10 |
| `config/sweep/detection_range_optimal.yaml` | Source distance (10–500 m, 500–2000 Hz band) | 10 |

> Timings on **12th Gen i7-1255U** (Alder Lake, 10c/12t). C++ acceleration active (`make build`).
> 
> Default breakdown: SRP beamforming 11.5s (8.2ms/frame) + wind noise 4.6s + bird noise 2.0s + ambient 0.5s + propagation 2.0s + misc 3.0s.
> Without C++ extensions, expect 2–3× slower.

## Setup

```bash
# Recommended — install using uv (reads pyproject.toml + uv.lock)
uv sync

# Alternatively, install with pip
pip install -e .
```

Dependencies: `numpy>=1.24, scipy>=1.10, matplotlib>=3.7, pyyaml>=6.0, pydantic>=2.0, streamlit>=1.40` — Python >= 3.10.

All commands can be run with `uv run <cmd>` or after activating the virtual environment (`source .venv/bin/activate`).

### C++ Acceleration (optional, recommended)

Build the C++ extensions for 2×–10× speedup:

```bash
make build
```

Requires:
- **pybind11** (installed via pip, in `pyproject.toml`)
- **FFTW3** (system library):

  | OS | Install |
  |---|---|
  | Debian/Ubuntu | `sudo apt install libfftw3-dev` |
  | Arch | `sudo pacman -S fftw` |
  | Fedora | `sudo dnf install fftw-devel` |
  | macOS | `brew install fftw` |

Three modules are built:
| Module | Path | Accelerates |
|---|---|---|
| `_propagate.so` | `src/cpp/propagate.cpp` | Per-sample delay+attenuation + absorption OLA |
| `_srp.so` | `src/cpp/srp.cpp` | SRP-PHAT beamforming (einsum hot path) |

Each falls back to pure Python automatically if the `.so` is missing.
