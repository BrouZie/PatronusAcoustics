# Architecture Overview

The simulation models a microphone array (dual ring by default, any geometry via config) capturing acoustic emissions from a UAV, with realistic environmental effects and hardware imperfections, processed through vectorized SRP-PHAT beamforming. Its purpose is to answer the fabrication question — *what geometry yields what detection performance in a realistic environment* — and to teach the underlying physics through the dashboard.

## High-Level Flow

```
YAML Config → Pydantic Config (src/config/) → Simulation.run()
                                  │
             speed_of_sound(temperature) from src/constants.py
                                  │
          ┌───────────────┬───────┴────────┬─────────────────┐
          ▼               ▼                ▼                 ▼
     DroneSource      Environment     make_array()      SensorModel
   (BPF harmonics,  (ground refl.,  (DualRing/Single   (EIN noise floor,
    turbulence,      wind, traffic,   Ring/Arbitrary;    gain/phase mismatch,
    ISO absorption,  birds, ambient)  true vs nominal    HPF, AOP clip,
    refraction)                       positions)         quantization)
          │               │                │                 │
          └───────────────┴───────┬────────┴─────────────────┘
                                  ▼
                    Mic signals (n_mics, n_samples)
                                  │
                                  ▼
                    SRPPhatProcessor.process_frame()
                    (precomputed phase tensor, einsum,
                     window/hemisphere/full-sphere grid,
                     P2M/PSR detection gate)
                                  │
                                  ▼
              MetricsResult (error, PSR, beamwidth,
              front/back confusion + mirror suppression)
                                  │
              ┌───────────────────┼──────────────────────┐
              ▼                   ▼                      ▼
      results/cache/v<N>/   Figures/animation    src/analysis + src/compare
      (config-hash keyed)                        (range curves, geometry
                                                  reports, triangulation,
                                                  MCU budget)
```

## Module Map

| Module | Responsibility |
|---|---|
| `constants.py` | `speed_of_sound(T)`, `SPEED_OF_SOUND_REF`, `REF_SPL_DB`, numerical epsilons — single source of truth |
| `config/` | Pydantic `BaseModel` hierarchy, array-config union (`dual_ring`/`single_ring`/`xyz`), YAML loading, `deep_merge`, `config_hash()` |
| `geometry.py` | `ArrayGeometry` base + `DualRingArray`/`SingleRingArray`/`ArbitraryArray`, `make_array()` factory, nominal vs true (perturbed) positions |
| `sensor.py` | `SensorModel` (EIN self-noise, per-mic gain/phase mismatch, placement error, dead channels, quantization) + `effective_snr_db()` budget |
| `trajectory.py` | `Trajectory` base + 5 subclasses (linear, flyby, arc, oscillating, waypoint) |
| `drone_signal.py` | `DroneSource` — BPF harmonics, turbulence, absorption/refraction filters, delay rendering (propagation only; sensor effects live in `sensor.py`) |
| `environment.py` | `Environment` + `GroundReflector`, `WindSource`, `TrafficSource`, `BirdSource`, `AmbientSource`, shared `colored_noise()` |
| `absorption.py` | ISO 9613-1 atmospheric absorption (validated against published table anchors) |
| `refraction.py` | Effective-sound-speed refraction, shadow-zone excess attenuation |
| `srpphat.py` | `SRPPhatProcessor` — vectorized phase tensor, coverage presets up to full sphere, az-wrap-aware detection gate |
| `simulation.py` | `Simulation.run()` — orchestrates signal gen → sensor → noise → SRP → metrics; seeds RNG from `signal.seed` |
| `metrics.py` | `MetricsResult` — angular error, PSR, beamwidth, `front_back_confusion_rate`, `mean_mirror_suppression_db` |
| `beampattern.py` | Analytical DAS beampattern for any `ArrayGeometry` (`python -m src.beampattern -c <cfg>`); reused by dashboard + compare |
| `main.py` | CLI entry point, `run_simulation()`, `apply_overrides()` |
| `sweep.py` | YAML-driven parameter sweep runner with checkpoint/resume |
| `analysis/` | `detection_range` (range curves, `range_at_rate`), `triangulation` (two-station Monte Carlo), `mcu_requirements`/`mcu_profiles` (multi-target MCU feasibility) |
| `compare.py` | Geometry comparison CLI → `report.md` + decision plots (`make compare-baseline`) |
| `visualize.py` / `visualize_3d.py` | Summary figures, 3D beamsphere animation (geometry-agnostic) |
| `results/` | `SweepCatalog` (sweep discovery), versioned `cached_run()` cache with `prune_cache()` |
| `dashboard/` | Streamlit app: config form (union-aware), sweep browser, educational modules built on the production physics, Educational→Simulation geometry handoff |

## Key Design Decisions

- **One speed of sound** — `Simulation` derives c from the configured temperature (fallback 343.0 when the environment is disabled) and injects it into geometry, propagation, and noise paths so steering and physics always agree.
- **Nominal vs true positions** — SRP steering uses the *designed* mic positions while propagation uses the *as-built* (perturbed) ones. That mismatch is exactly what degrades a fabricated array, and it is what `mic.imperfections.position_std_mm` models.
- **Geometry as a config union** — `array.type` selects dual ring / single ring / arbitrary XYZ; every geometry runs the identical pipeline, so candidates are directly comparable.
- **Full-sphere search when it matters** — `srpphat.search.coverage: full_sphere` enables the front/back metrics that justify (or refute) the dual-ring axial separation. PSR/beamwidth are only comparable at equal coverage.
- **Vectorized SRP** — precomputed phase tensor `(n_freq × n_mics × n_dirs)` and two `einsum` calls; complex64 on the numpy path to halve memory, complex128 when the C++ extension is active.
- **EIN-based SNR budget** — `effective_snr_db()` = drone SPL − spreading − ISO absorption − mic noise floor. Manual `signal.snr_db` override always available (sweeps use it).
- **Versioned simulation cache** — results keyed by config hash under `results/cache/v<N>/`; `CACHE_SCHEMA_VERSION` is bumped whenever numerics change without a config change, so stale physics is never served.
- **Reproducibility** — `signal.seed` seeds the acoustic realization; `mic.imperfections.seed` fixes one "build" of the array independently.
- **Detection gating** — peak-to-mean (default) or PSR threshold on the SRP map; only gated frames contribute to angular-error statistics. With no valid detections the error statistics are NaN, not 0.
