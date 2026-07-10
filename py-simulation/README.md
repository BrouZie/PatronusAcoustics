# Patronus — Acoustic Array Simulation

SRP-PHAT beamforming simulation for microphone-array UAV detection, with realistic environmental noise, ground reflection, and hardware-imperfection modeling. Its job: answer **what geometry to fabricate** — predict detection range, DOA accuracy, and front/back rejection for any candidate array in a realistic environment — and teach the team the underlying physics via an interactive dashboard.

```
# The fabrication decision artifact (report.md + plots)
make compare-baseline

# CLI
python -m src.main -c config/noisy_oscillating.yaml --quick --no-animation

# Interactive dashboard
streamlit run src/dashboard/app.py
```

## Feature Summary

- **Pluggable array geometry** — dual ring (default), single ring, or arbitrary XYZ positions (`array.type` in config); all run through the identical pipeline
- **SRP-PHAT beamforming** — vectorized via `np.einsum` with precomputed phase tensor; window / front-hemisphere / **full-sphere** search coverage
- **Front/back rejection metrics** — mirror-lobe suppression and confusion rate quantify what the axial ring separation actually buys (the core dual-ring design question)
- **Geometry comparison reports** — `python -m src.compare geomA.yaml geomB.yaml` → detection-rate-vs-range curves, range@90%/range@50%, beampattern cuts, and an MCU feasibility column for the first configured target (Teensy 4.1, STM32H7, …)
- **6 drone trajectory types** — stationary, linear, flyby (CPA), arc, oscillating, waypoint; Doppler-capable via per-sample delay interpolation
- **Sensor model** — EIN-derived noise floor (ICS-52000, 65 dBA), per-mic gain/phase mismatch, PCB placement error, dead channels, 24-bit quantization (`mic.imperfections`)
- **ISO 9613-1 atmospheric absorption** — validated against published table anchors; temperature-derived speed of sound shared across all modules
- **Ground reflection** — image-source model with configurable coefficient; dominant detection degrader via BPF harmonic cancellation
- **Directional environmental noise** — Corcos wind coherence field (Cholesky-decomposed), traffic (bandpass+AM), bird FM chirps, ambient diffuse pink noise
- **Two-station triangulation** — geometric Monte Carlo (`python -m src.analysis.triangulation`) mapping 3D position error from measured single-station bearing error
- **Parameter sweep runner** — YAML-defined Cartesian product sweeps over any config path; per-run aggregate CSV output, checkpoint/resume
- **Simulation cache** — results keyed by config hash under `results/cache/v<N>/`; prune with `python -m src.results.cache --prune`
- **Interactive dashboard** — auto-generated config form, sweep browser, educational modules that reuse the production physics, and an Educational → Simulation geometry handoff
- **160+ tests** — including known-answer physics validation (ISO absorption anchors, aperture scaling laws, SRP known answers, front/back physics) and dashboard AppTest smoke tests

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

# The fabrication question: ring spacing vs detection range / front-back rejection
uv run python -m src.sweep config/sweep/ring_spacing_vs_range.yaml
uv run python -m src.sweep config/sweep/ring_spacing_frontback.yaml

# Geometry comparison report (fast variant: make compare-baseline-quick)
make compare-baseline

# Analytical beampattern for the configured geometry
uv run python -m src.beampattern -c config/default.yaml

# Two-station triangulation error map (σ from a measured range curve)
uv run python -m src.analysis.triangulation --baseline 40 --sigma 3

# Dump config schema with descriptions and defaults
uv run python -m src.main --dump-schema

# Run tests
uv run python -m pytest tests/
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
| [docs/metrics.md](docs/metrics.md) | Per-frame + aggregate metrics (incl. front/back), CSV column reference |
| [docs/analysis.md](docs/analysis.md) | Range curves, geometry comparison reports, triangulation, MCU feasibility |
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
