# Drone Trajectory Types

The simulation supports 5 trajectory types via the `drone.trajectory` config block. Each is a subclass of `Trajectory` with a `get_position(t)` method returning a 3D position at time `t`.

| Type | Config Key | Behavior |
|---|---|---|
| **Stationary** | *(no trajectory, motion disabled)* | Drone stays at `initial_bearing` × `distance` |
| **Linear** | `type: linear` | Constant-velocity straight-line path |
| **Flyby** | `type: flyby` | Closest-point-of-approach (CPA) model |
| **Arc** | `type: arc` | Spherical sweep at constant radius & elevation |
| **Oscillating** | `type: oscillating` | Sinusoidal lateral oscillation around CPA |
| **Waypoint** | `type: waypoint` | Piecewise-linear through time-position list |

## Stationary

The default when no trajectory is specified and motion is disabled. The drone sits at a fixed position defined by `distance` and `initial_bearing`. Uses a faster FFT-based delay rendering path in `DroneSource`.

## Linear

```yaml
trajectory:
  type: linear
  velocity: [5, 0, 0]       # m/s in (x, y, z)
```

Position is `pos0 + velocity * t`. Can simulate a simple pass-through.

## Flyby (CPA model)

```yaml
trajectory:
  type: flyby
  closest_distance: 5.0       # CPA distance (m)
  closest_azimuth_deg: 0.0    # CPA direction
  closest_elevation_deg: 30.0
  speed: 8.0                  # m/s along perpendicular path
  total_duration: 15.0        # total sim time (s)
```

The drone flies along a perpendicular path through the CPA. The path is centered in time so CPA occurs at `total_duration / 2`. Realistic for aerial surveys and flyovers.

## Arc

```yaml
trajectory:
  type: arc
  radius: 15.0                # constant distance from array (m)
  elevation_deg: 25.0         # constant elevation
  azimuth_start_deg: -50.0    # start of sweep
  azimuth_end_deg: 50.0       # end of sweep
  speed: 1.75                 # m/s along arc
```

The drone moves along a spherical arc at constant radius and elevation. Since distance doesn't change, SNR and ground-reflection geometry are approximately constant. Useful for studying angular accuracy vs azimuth.

## Oscillating

```yaml
trajectory:
  type: oscillating
  closest_distance: 7.0       # CPA distance (m)
  closest_azimuth_deg: 0.0    # CPA direction
  closest_elevation_deg: 30.0
  cross_range: 14.0           # lateral oscillation amplitude (m)
  period: 12.0                # full oscillation period (s)
```

Sinusoidal lateral oscillation around the CPA direction. Distance varies from `closest_distance` to `~closest_distance + cross_range`, causing SNR to vary by ~9 dB over each cycle. Combined with ground reflection, this creates natural detection/non-detection switching — ideal for studying the detection envelope.

## Waypoint

```yaml
trajectory:
  type: waypoint
  waypoints:
    - time: 0.0
      position: [10, 0, 8]
    - time: 5.0
      position: [0, 10, 5]
    - time: 10.0
      position: [-10, 0, 8]
```

Piecewise-linear interpolation through a sorted list of `(time, position)` pairs. Maximum flexibility.

## Moving vs. Stationary Path

- **Stationary trajectories** (no trajectory + motion disabled) use FFT-based delay rendering — compute once for all frames.
- **Moving trajectories** use per-sample delay interpolation with time-varying delays — required for Doppler and time-varying multipath.

The `DroneSource.generate_mic_signals()` method automatically selects the appropriate path based on `is_stationary`.
