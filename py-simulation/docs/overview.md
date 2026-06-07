# Architecture Overview

The simulation models a dual-ring microphone array capturing acoustic emissions from a UAV (drone), with realistic environmental effects, processed through vectorized SRP-PHAT beamforming. Results are exposed through a Streamlit dashboard or programmatically via the results/cache modules.

## High-Level Flow

```
YAML Config → Pydantic Config (src/config/) → Simulation.run()
                                    │
                    ┌───────────────┼────────────────┐
                    ▼               ▼                ▼
            DroneSource       Environment      DualRingArray
         (harmonic stack,   (ground refl.,    (mic positions,
          HPF, AOP,          wind, traffic,     steering vecs)
          turbulence)        birds, ambient)
                    │               │                │
                    └───────────────┼────────────────┘
                                    ▼
                          Mic signals (n_mics, n_samples)
                                    │
                                    ▼
                      SRPPhatProcessor.process_frame()
                      (precomputed phase tensor,
                       einsum beamforming,
                       P2M detection gate)
                                    │
                                    ▼
                     ┌──────────────┤
                     ▼              ▼
              MetricsResult    optional: save_cache()
              + Figures         (results/cache/)
                     │
                     ▼
              Streamlit Dashboard  or  CLI
```

## Module Map

| Module | Responsibility |
|---|---|
| `config/` | Pydantic `BaseModel` hierarchy (`Config`, `ArrayConfig`, `NoiseConfig`, etc.), YAML loading, `deep_merge`/`parse_dotted_key`, `config_hash()` |
| `geometry.py` | `DualRingArray` — mic positions, steering delays, tilt support |
| `trajectory.py` | `Trajectory` base + 5 subclasses (linear, flyby, arc, oscillating, waypoint) |
| `drone_signal.py` | `DroneSource` — BPF harmonics, turbulence, HPF, AOP, delay rendering |
| `environment.py` | `Environment` + `GroundReflector`, `WindSource`, `TrafficSource`, `BirdSource`, `AmbientSource` |
| `srpphat.py` | `SRPPhatProcessor` — vectorized phase tensor, `einsum` beamforming, detection gate |
| `simulation.py` | `Simulation.run()` — orchestrates signal gen → noise → SRP → metrics |
| `metrics.py` | `MetricsResult`, `compute_metrics()` — angular error, PSR, beamwidth |
| `main.py` | CLI entry point, `run_simulation()`, `apply_overrides()` |
| `sweep.py` | YAML-driven parameter sweep runner with checkpoint/resume |
| `visualize.py` | Summary figures (SRP heatmap, DOA tracking, metrics panel) |
| `visualize_3d.py` | 3D beamsphere animation with rotating camera |
| `results/` | `SweepResultDir`/`SweepCatalog` (sweep discovery), `cached_run()` (simulation cache) |
| `dashboard/` | Streamlit app: config form, results viewer, educational visualizations |

## Key Design Decisions

- **Pydantic v2** replaces hand-rolled dataclass validation. All 15 config models use `Field(ge=..., le=..., description=...)` with `json_schema_extra` for unit metadata. Free JSON Schema generation via `model_json_schema()`.
- **Vectorized SRP**: Precomputed 3D phase tensor `(n_freq × n_mics × n_dirs)` replaces Python-level frequency loop with two `einsum` calls — 7.3× speedup.
- **EIN-based SNR**: Noise floor derived from microphone datasheet (94 − snr_dba) rather than arbitrary SNR values. Manual override always available.
- **Directional noise**: Wind, traffic, and birds propagate through FFT-based delay-and-attenuation, creating spatially-correlated mic signals. Only ambient noise is diffuse (per-channel pink).
- **Ground reflection**: Image-source model with configurable coefficient. The dominant physical effect — creates frequency-dependent comb-filter nulls that align with BPF harmonics.
- **Detection gating**: Peak-to-mean ratio (P2M) threshold on SRP map. Only frames exceeding the gate contribute to angular error statistics.
- **Simulation cache**: `cached_run()` stores results keyed by config hash in `results/cache/<hash>/`. Avoids redundant recomputation during dashboard parameter exploration.
- **Config package**: The old monolithic `config.py` was split into `config/__init__.py` (re-exports), `models.py` (15 Pydantic models), `merge.py` (deep_merge, parse_dotted_key), and `hash.py` (config_hash).
