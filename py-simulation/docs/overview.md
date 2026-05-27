# Architecture Overview

The simulation models a dual-ring microphone array capturing acoustic emissions from a UAV (drone), with realistic environmental effects, processed through vectorized SRP-PHAT beamforming.

## High-Level Flow

```
YAML Config → Config dataclass → Simulation.run()
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
                          MetricsResult + Figures
```

## Module Map

| Module | Responsibility |
|---|---|
| `config.py` | Dataclass hierarchy (`Config`, `ArrayConfig`, `NoiseConfig`, etc.), YAML loading, `deep_merge`/`parse_dotted_key` |
| `geometry.py` | `DualRingArray` — mic positions, steering delays, tilt support |
| `trajectory.py` | `Trajectory` base + 5 subclasses (linear, flyby, arc, oscillating, waypoint) |
| `drone_signal.py` | `DroneSource` — BPF harmonics, turbulence, HPF, AOP, delay rendering |
| `environment.py` | `Environment` + `GroundReflector`, `WindSource`, `TrafficSource`, `BirdSource`, `AmbientSource` |
| `srpphat.py` | `SRPPhatProcessor` — vectorized phase tensor, `einsum` beamforming, detection gate |
| `simulation.py` | `Simulation.run()` — orchestrates signal gen → noise → SRP → metrics |
| `metrics.py` | `MetricsResult`, `compute_metrics()` — angular error, PSR, beamwidth |
| `main.py` | CLI entry point, `run_simulation()`, `apply_overrides()` |
| `sweep.py` | YAML-driven parameter sweep runner |
| `visualize.py` | Summary figures (SRP heatmap, DOA tracking, metrics panel) |
| `visualize_3d.py` | 3D beamsphere animation with rotating camera |

## Key Design Decisions

- **Vectorized SRP**: Precomputed 3D phase tensor `(n_freq × n_mics × n_dirs)` replaces Python-level frequency loop with two `einsum` calls — 7.3× speedup.
- **EIN-based SNR**: Noise floor derived from microphone datasheet (94 − snr_dba) rather than arbitrary SNR values. Manual override always available.
- **Directional noise**: Wind, traffic, and birds propagate through FFT-based delay-and-attenuation, creating spatially-correlated mic signals. Only ambient noise is diffuse (per-channel pink).
- **Ground reflection**: Image-source model with configurable coefficient. The dominant physical effect — creates frequency-dependent comb-filter nulls that align with BPF harmonics.
- **Detection gating**: Peak-to-mean ratio (P2M) threshold on SRP map. Only frames exceeding the gate contribute to angular error statistics. Rejected frames are displayed but excluded from error computation.
