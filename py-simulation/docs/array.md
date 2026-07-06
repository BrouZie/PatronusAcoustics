# Array Geometry

Geometry is the open design variable of the project, so the simulation supports pluggable array types through a single abstraction: every geometry is an `ArrayGeometry` (`src/geometry.py`) built by `make_array(array_config, speed_sound)` and runs through the identical pipeline.

## Array Types (config union)

Select with `array.type` (defaults to `dual_ring`; YAML without a `type` key keeps working):

```yaml
# Dual concentric rings separated along boresight (the pitch design)
array:
  type: dual_ring          # optional — this is the default
  ring1_radius: 0.34       # outer ring radius (m)
  ring2_radius: 0.17       # inner ring radius (m)
  n_mics_ring1: 8
  n_mics_ring2: 8
  ring_spacing: 0.20       # axial separation between rings (m)

# Planar UCA — the baseline a dual ring must beat on front/back rejection
array:
  type: single_ring
  radius: 0.25
  n_mics: 16
  z_offset: 0.0

# Arbitrary positions (prototype PCB layouts, exotic candidates)
array:
  type: xyz
  positions: [[0.1, 0.0, 0.0], [-0.1, 0.0, 0.0], [0.0, 0.1, 0.05]]
  # or csv_path: path/to/positions.csv  (x,y,z rows — prefer inline
  # positions: file contents are not part of the config hash)
```

Array config models reject unknown keys (`extra="forbid"`), so typos fail loudly instead of being silently ignored.

## Dual-Ring Physical Layout

```
                    Ring 1 (outer)
         ╭─────────────────────────╮
         │   ●    ●    ●    ●      │  R1 = 0.34 m (Ø 0.68 m), 8 mics
         │  ●                  ●   │
         ├───────── 0.20 m ────────┤  ← ring_spacing (axial, along boresight)
         │  ●                  ●   │
         │   ●    ●    ●    ●      │  R2 = 0.17 m (Ø 0.34 m), 8 mics
         ╰─────────────────────────╯
```

Both rings are coaxial (+z = boresight), evenly spaced in azimuth. The **axial separation exists to break front/back mirror symmetry** — a planar ring cannot distinguish a source in front from its mirror behind the array. Quantify this with `srpphat.search.coverage: full_sphere` and the `mean_mirror_suppression_db` / `front_back_confusion_rate` metrics (see [metrics.md](metrics.md)), or sweep it directly with `config/sweep/ring_spacing_frontback.yaml`.

## Steering Model and Coordinate Conventions

- Elevation is the **polar angle from boresight**: el = 0° is boresight, el = 90° is the ring plane, el = 180° is directly behind the array.
- For a source at position **s**, the delay at mic **m** is `τ_m = ||s − p_m|| / c`. The speed of sound `c` is injected by `Simulation` from the configured temperature (`speed_of_sound(T)` in `src/constants.py`); standalone tools default to 343 m/s.

## Nominal vs True Positions

`ArrayGeometry` keeps two position sets:

- `positions` — the **designed** coordinates. SRP steering delays are computed from these (the DSP only knows the design).
- `positions_true` — the **as-built** coordinates after `perturb(offsets)`. All physical propagation (drone, ground reflection, noise sources) uses these.

`Simulation` calls `array.perturb(sensor.position_offsets)` with placement errors drawn from `mic.imperfections.position_std_mm`. The steering/propagation mismatch this creates is the dominant real-world beamforming degradation (see [snr.md](snr.md)).

## ArrayGeometry API

| Member | Purpose |
|---|---|
| `positions` / `positions_true` | Nominal vs as-built mic coordinates `(n_mics, 3)` |
| `get_steering_delays(directions)` | `(n_mics, n_dirs)` delays from **nominal** positions |
| `get_tdoa(source_pos)` | Per-mic physical delays from **true** positions |
| `perturb(offsets)` | Set as-built positions = nominal + offsets |
| `set_tilt(deg)` | Tilt about the X axis (roof-mast / tripod deployment) |
| `get_mic_positions_world()` | True positions after tilt rotation (used by propagation) |
| `world_to_array_coords(pos)` | World → tilted array frame |

Module-level helpers `direction_vectors(az, el)` and `cartesian_to_angles(vecs)` define the angle conventions used everywhere (SRP grid, metrics, visualization).

## Comparing Geometries

- Analytical beampattern for any configured geometry: `python -m src.beampattern -c config/default.yaml` (see [array_geometry.md](array_geometry.md)).
- Full detection-performance comparison: `python -m src.compare` / `make compare-baseline` (see [analysis.md](analysis.md)).
- Interactive: dashboard Educational → Beamforming Basics, with a **Send geometry to Simulation tab** button that loads the slider geometry into the full simulation form.
