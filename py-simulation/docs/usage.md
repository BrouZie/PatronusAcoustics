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
| `--ring1-radius, --ring2-radius, --n-mics-1, --n-mics-2, --ring-spacing` | Array geometry overrides (dual-ring configs only; other `array.type`s must be edited in the YAML) |

## Interactive Dashboard

The Streamlit dashboard provides a GUI for the simulation:

```bash
uv run streamlit run src/dashboard/app.py
```

Three tabs:

1. **Simulation** — Auto-generated parameter form from Pydantic config schema (sliders for bounded numbers, checkboxes for booleans, selectboxes for enums, expanders for nested sub-configs). Quick/DEFAULT preset buttons. Cache-aware run (loads cached results when config unchanged). Results summary with metric cards and diagnostic plots (angular error timeline, PSR timeline, error distribution).

2. **Sweep Results** — Browse past sweep runs via `SweepCatalog`. View CSV data in a table, explore parameter vs metric relationships with interactive scatter plots.

3. **Educational** — Three interactive learning modules built on the production physics (`src.beampattern`, `src.geometry`, `src.environment`), with `st.cache_data` so slider changes stay responsive:
   - **Beamforming Basics**: Polar + cartesian beampattern plots, array geometry visualization, multi-frequency overlay, ULA comparison — plus a **"Send geometry to Simulation tab"** button that loads the slider geometry into the Simulation form (explore → run the full sim on that exact geometry)
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
```

Combinations run sequentially (the `--workers` flag is currently accepted but not used).

Sweep configs live in `config/sweep/*.yaml`. Each references `config/default.yaml` as its base.
See [config.md](config.md) for the YAML format.

Each run creates a timestamped subfolder under `results/` containing:
- `sweep_results.csv` — incremental CSV with per-combination metrics
- `sweep_results.csv.state.json` — checkpoint state for resume

## Geometry Comparison & Analysis Tools

The decision-grade layer on top of sweeps — see [analysis.md](analysis.md):

```bash
# Fabrication-trade report: dual ring at 3 spacings vs 16-mic planar ring
make compare-baseline          # full;  make compare-baseline-quick for a fast pass

# Custom geometry comparison → report.md + plots under results/compare_<ts>/
uv run python -m src.compare config/compare/dual_ring_s20.yaml my_array.yaml \
    --distances 10 20 30 50 70

# Analytical beampattern of the configured geometry
uv run python -m src.beampattern -c config/default.yaml

# Two-station triangulation error heatmap (σ from a measured range curve)
uv run python -m src.analysis.triangulation --baseline 40 --sigma 3
```

## Simulation Cache

Results are cached in `results/cache/v<N>/<config_hash>/` (gitignored). When the same config is run again (e.g., from the dashboard or a range curve), cached results are loaded instead of re-running. The version directory `v<N>` (`CACHE_SCHEMA_VERSION` in `src/results/cache.py`) is bumped whenever simulation numerics change without a config change — old-physics results are then ignored automatically.

```python
from src.results import clear_cache
clear_cache()          # clear all
clear_cache(config)    # clear specific
```

```bash
# Prune oldest entries until the cache fits in 5 GB (LRU by mtime)
uv run python -m src.results.cache --prune --max-gb 5
```

Reproducibility: set `signal.seed` for a deterministic acoustic realization; `mic.imperfections.seed` fixes one hardware "build" independently.

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

| Sweep config | Parameters swept |
|---|---|
| `config/sweep/ring_spacing_vs_range.yaml` | **The fabrication question**: ring spacing × distance |
| `config/sweep/ring_spacing_frontback.yaml` | Ring spacing × distance at full-sphere coverage → front/back rejection |
| `config/sweep/mounting_height.yaml` | Height × ground model (constant/Delany-Bazley) |
| `config/sweep/gate_threshold.yaml` | PSR threshold (2–10 dB) |
| `config/sweep/freq_band.yaml` | Min/max frequency band limits |
| `config/sweep/detection_range.yaml` | Source distance (full band) |
| `config/sweep/detection_range_optimal.yaml` | Source distance (500–2000 Hz band) |
| `config/sweep/array.yaml`, `atmospheric.yaml`, `distance.yaml`, `ground.yaml` | Further single-topic sweeps |

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
