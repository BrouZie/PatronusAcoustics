# Usage Guide

## Quick Start

```bash
# Basic simulation
python -m src.main -c config/noisy_oscillating.yaml

# Fast iteration (4s, coarse grid, no animation)
python -m src.main -c config/noisy_oscillating.yaml --quick --no-animation

# Benchmark / regression test
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
| `--quick` | 4s, 4° resolution, 2 kHz max freq, no animation |
| `--no-animation` | Skip animation rendering |
| `--no-figures` | Skip summary figures |
| `--interactive` | Show interactive figure after saving |
| `--profile` | Profile with cProfile (top-20 cumtime) |
| `--dry-run` | Print run name and output path, don't run |
| `--ring1-radius, --ring2-radius, --n-mics-1, --n-mics-2, --ring-spacing` | Array geometry overrides |

## Sweep Runner

```bash
# Run a sweep
python -m src.sweep config/sweep_ground.yaml

# Preview combinations without running
python -m src.sweep config/sweep_ground.yaml --dry-run
```

Sweep configs live in `config/sweep_*.yaml`. See [config.md](config.md) for the YAML format.

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
| `-c config/benchmark.yaml` | 2s stationary, SNR=25, 4°, 2 kHz | ~0.3s | ~0.3s |
| `-c config/default.yaml` | 15s arc, no environment | ~2s | ~0.4s |
| `-c config/noisy_oscillating.yaml` | 15s oscillating + environment | ~6s | **~23.6s** |
| `-c config/prototype.yaml` | 10s oscillating + light traffic | ~4s | ~4s |
| `-c config/oscillating_drone.yaml` | 15s oscillating, no environment | ~2s | ~0.4s |
| `-c config/moving_drone.yaml` | 15s flyby, no environment | ~2s | ~0.4s |
| `-c config/16_prototype.yaml` | 10s, 32 mics, environment | ~10s | ~10s |

> Timings on **12th Gen i7-1255U** (Alder Lake, 10c/12t). C++ acceleration active (`make build`).
> 
> `noisy_oscillating` is the heaviest default config: 2° grid (3721 directions), 4 kHz max freq (171 bins), 1403 frames.
> Breakdown: SRP beamforming 11.5s (8.2ms/frame) + wind noise 4.6s + bird noise 2.0s + ambient 0.5s + propagation 2.0s + misc 3.0s.
> Without C++ (`_srp`, `_noise`, `_propagate`), expect 2–3× slower.

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
