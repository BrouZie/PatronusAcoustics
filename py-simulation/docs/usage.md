# Usage Guide

## Quick Start

```bash
# Default realistic simulation (15s, environment, oscillating drone)
python -m src.main

# Fast iteration (4s, coarse grid, 2 kHz, no output files)
python -m src.main -c config/quick.yaml

# Benchmark / regression test (2s, stationary, no environment)
python -m src.main -c config/benchmark.yaml

# Profile (top-20 cumtime)
python -m src.main -c config/benchmark.yaml --profile
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
| `--quick` | 4s, 4° resolution, 2 kHz max freq, no output files (same as `-c config/quick.yaml`) |
| `--no-animation` | Skip animation rendering |
| `--no-figures` | Skip summary figures |
| `--interactive` | Show interactive figure after saving |
| `--profile` | Profile with cProfile (top-20 cumtime) |
| `--dry-run` | Print run name and output path, don't run |
| `--ring1-radius, --ring2-radius, --n-mics-1, --n-mics-2, --ring-spacing` | Array geometry overrides |

## Sweep Runner

```bash
# Run a sweep
python -m src.sweep config/sweep/ground.yaml

# Preview combinations without running
python -m src.sweep config/sweep/ground.yaml --dry-run
```

Sweep configs live in `config/sweep/*.yaml`. Each references `config/default.yaml` as its base.
See [config.md](config.md) for the YAML format.

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

Sweep results go to `results/` as CSV files.

## Provided Config Files

| Command | Scenario | Duration | Time (C++) |
|---|---|---|---|---|
| *(none — loads `config/default.yaml`)* | 15s oscillating + environment (ICS-52000) | 15s | **~23.6s** |
| `-c config/quick.yaml` | 4s, 4° grid, 2 kHz, no output | 4s | ~2s |
| `-c config/benchmark.yaml` | 2s stationary, SNR=25, 4°, 2 kHz | 2s | ~0.3s |

| Sweep config | Parameters swept |
|---|---|
| `config/sweep/ground.yaml` | Ground reflection coefficient, array tilt |
| `config/sweep/distance.yaml` | Closest trajectory distance, wind speed |
| `config/sweep/array.yaml` | Ring1 radius, mic count on ring1 |
| `config/sweep/atmospheric.yaml` | Humidity, source distance |
| `config/sweep/detection_range.yaml` | Source distance (10–500m) |

> Timings on **12th Gen i7-1255U** (Alder Lake, 10c/12t). C++ acceleration active (`make build`).
> 
> Default breakdown: SRP beamforming 11.5s (8.2ms/frame) + wind noise 4.6s + bird noise 2.0s + ambient 0.5s + propagation 2.0s + misc 3.0s.
> Without C++ extensions, expect 2–3× slower.

## Dependencies

```
numpy>=1.24, scipy>=1.10, matplotlib>=3.7, pyyaml>=6.0
Python >= 3.10
```

Install: `pip install -e .` (from `pyproject.toml`) or use the provided `uv.lock`.

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
| `_noise.so` | `src/cpp/noise.cpp` | Wind noise Corcos frequency loop |
| `_srp.so` | `src/cpp/srp.cpp` | SRP-PHAT beamforming (einsum hot path) |

Each falls back to pure Python automatically if the `.so` is missing.
