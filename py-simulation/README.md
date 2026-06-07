# Patronus — Dual-Ring Acoustic Array Simulation

SRP-PHAT beamforming simulation for a 16-microphone dual-ring array targeting UAV detection, with realistic environmental noise and ground reflection modeling. Includes an interactive research dashboard for parameter exploration and educational visualizations.

```
# CLI
python -m src.main -c config/noisy_oscillating.yaml --quick --no-animation

# Interactive dashboard
streamlit run src/dashboard/app.py
```

## Feature Summary

- **Dual-ring array** — 8+8 mics on concentric rings, configurable radii/spacing/mic count, optional tilt
- **SRP-PHAT beamforming** — vectorized via `np.einsum` with precomputed phase tensor; 7.3× speedup vs frequency loop
- **6 drone trajectory types** — stationary, linear, flyby (CPA), arc, oscillating, waypoint; Doppler-capable via per-sample delay interpolation
- **ICS-52000 MEMS microphone model** — EIN-derived SNR (65 dBA → 29 dBA noise floor), 75 Hz HPF, tanh AOP soft-clipping
- **Ground reflection** — image-source model with configurable coefficient; dominant detection degrader via BPF harmonic cancellation
- **Directional environmental noise** — Corcos wind coherence field (Cholesky-decomposed), traffic (bandpass+AM), bird FM chirps, ambient diffuse pink noise
- **Detection gate** — peak-to-mean ratio with configurable threshold; only high-confidence frames contribute to angular error
- **3D beamsphere animation** — rotating MP4 with SRP sphere, heatmap, DOA tracking, and metrics panel
- **Parameter sweep runner** — YAML-defined Cartesian product sweeps over any config path; per-run aggregate CSV output, checkpoint/resume
- **Simulation cache** — auto-caches results keyed by config hash; avoids redundant recomputation during dashboard exploration
- **Interactive dashboard** — Streamlit app with auto-generated config form, sweep results browser, and 3 educational visualization modules
- **96 unit tests** — configuration (Pydantic validation), SRP vectorization, environment/turbulence/ground, sweep results & cache

## Quick Start

```bash
# Install dependencies (uses uv.lock for pinned versions)
uv sync

# CLI — run with default config
uv run python -m src.main

# Benchmark (0.3s, stationary, coarse grid)
uv run python -m src.main -c config/benchmark.yaml

# Realistic scenario (oscillating + environment noise)
uv run python -m src.main -c config/noisy_oscillating.yaml

# Launch interactive dashboard
uv run streamlit run src/dashboard/app.py

# Parameter sweep
uv run python -m src.sweep config/sweep/mounting_height.yaml

# Dump config schema with descriptions and defaults
uv run python -m src.main --dump-schema

# Run tests
uv run pytest
```

## Documentation

| Document | Content |
|---|---|
| [docs/overview.md](docs/overview.md) | Architecture, module map, design decisions |
| [docs/array.md](docs/array.md) | Dual-ring geometry, steering model, tilt |
| [docs/config.md](docs/config.md) | Pydantic config system, sections, override precedence, sweep format |
| [docs/trajectory.md](docs/trajectory.md) | 6 trajectory types with YAML examples |
| [docs/environment.md](docs/environment.md) | Ground reflection, Corcos wind, traffic, birds, ambient |
| [docs/snr.md](docs/snr.md) | EIN-based SNR vs manual override, ICS-52000 specs |
| [docs/srpphat.md](docs/srpphat.md) | Vectorized SRP-PHAT, phase tensor, detection gate |
| [docs/metrics.md](docs/metrics.md) | Per-frame + aggregate metrics, CSV column reference |
| [docs/usage.md](docs/usage.md) | CLI reference, sweep runner, dashboard, config inventory |
| [docs/visualization.md](docs/visualization.md) | Figures, animations, raw data format |
| [docs/realism.md](docs/realism.md) | Realism assessment, key findings, trust guidance |
| [docs/experiments.md](docs/experiments.md) | Experiment ideas, sweep config reference, analysis tips |
| [docs/design_validation.md](docs/design_validation.md) | Validation sweep results and practical range recommendations |

## Dependencies

Python ≥ 3.10, numpy, scipy, matplotlib, pyyaml, pydantic≥2.0, streamlit≥1.40.

## Project Structure

```
py-simulation/
├── src/
│   ├── config/            # Pydantic models, merge, config_hash (replaces single config.py)
│   ├── results/           # Manifest, catalog, simulation cache
│   ├── dashboard/         # Streamlit app, config form, results viewer, educational modules
│   ├── geometry.py        # DualRingArray (mic positions, steering, tilt)
│   ├── trajectory.py      # 6 trajectory types
│   ├── drone_signal.py    # DroneSource (harmonics, HPF, AOP, turbulence)
│   ├── environment.py     # Environment, GroundReflector, 4 noise sources
│   ├── srpphat.py         # SRPPhatProcessor (vectorized phase tensor)
│   ├── simulation.py      # Simulation orchestrator
│   ├── metrics.py         # MetricsResult, angular error, PSR, beamwidth
│   ├── main.py            # CLI, run_simulation(), apply_overrides()
│   ├── sweep.py           # Parameter sweep runner
│   ├── visualize.py       # Summary figures
│   └── visualize_3d.py    # 3D beamsphere animation
├── config/                # YAML config files (12 provided)
├── tests/                 # 96 unit tests
├── docs/                  # Topic documentation
├── output/                # Run output (figures, animations, data)
├── results/               # Sweep CSV outputs
├── pyproject.toml
└── README.md
```
