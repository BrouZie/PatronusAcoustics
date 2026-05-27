# Dual-Ring Array Geometry

## Physical Layout

```
                    Ring 1 (outer)
         ╭─────────────────────────╮
         │   ●    ●    ●    ●      │  R1 = configurable (default 0.34 m)
         │  ●                  ●   │  8 mics
         │   ●                ●    │
         │    ●              ●     │
         │     ●            ●      │
         │      ●●────────●●       │
         ├───────── 0.20 m ────────┤  ← ring spacing
         │      ●●────────●●       │
         │     ●            ●      │
         │    ●              ●     │
         │   ●                ●    │
         │  ●                  ●   │  R2 = configurable (default 0.17 m)
         │   ●    ●    ●    ●      │  8 mics
         ╰─────────────────────────╯
```

Both rings are coaxial, separated by `ring_spacing`. Mics on each ring are evenly spaced in azimuth. Ring 1 is the outer ring; Ring 2 is the inner, offset along Z.

## Steering Model

For a source at position **s**, the time delay at mic **m** is:

```
τ_m = ||s − p_m|| / c    where c = 343 m/s
```

TDOAs for grid-based beamforming use the same formula, computed once into a steering-delay matrix `(n_mics × n_directions)`.

## Array Tilt

The array can be tilted around the X-axis (forward-backward tilt) using `set_tilt(deg)`. This rotates the mic positions via a rotation matrix and adds a coordinate transform for world→array frame conversions. Typical tilt: 0–15° (matching roof-mast or tripod deployment).

## DualRingArray API

| Method | Purpose |
|---|---|
| `get_tdoa(source_pos)` | Per-mic time delays for a single source position |
| `get_steering_delays(directions)` | `(n_mics, n_dirs)` delay matrix for grid directions |
| `get_mic_positions_world()` | Mic positions after tilt rotation |
| `world_to_array_coords(pos)` | Transform world positions to tilted array frame |
| `set_tilt(deg)` | Activate tilt with given angle |

## Config Reference

Array geometry is configured under `config/` via the `array:` block:

```yaml
array:
  ring1_radius: 0.34       # outer ring radius (m)
  ring2_radius: 0.17       # inner ring radius (m)
  n_mics_ring1: 8          # mics on outer ring
  n_mics_ring2: 8          # mics on inner ring
  ring_spacing: 0.20       # vertical separation between rings (m)
```
