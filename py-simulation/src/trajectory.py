import numpy as np


class Trajectory:
    def get_position(self, t):
        raise NotImplementedError

    @property
    def is_stationary(self):
        return False


class LinearTrajectory(Trajectory):
    def __init__(self, pos0, velocity):
        self.pos0 = np.asarray(pos0, dtype=float)
        self.velocity = np.asarray(velocity, dtype=float)

    def get_position(self, t):
        return self.pos0 + self.velocity * t

    @property
    def is_stationary(self):
        return not np.any(self.velocity)


class FlybyTrajectory(Trajectory):
    def __init__(self, closest_distance, closest_azimuth, closest_elevation,
                 speed, total_duration):
        self.speed = speed
        self.total_duration = total_duration

        cpa_pos = closest_distance * np.array([
            np.sin(closest_elevation) * np.cos(closest_azimuth),
            np.sin(closest_elevation) * np.sin(closest_azimuth),
            np.cos(closest_elevation),
        ])

        cpa_dir = cpa_pos / (np.linalg.norm(cpa_pos) + 1e-10)
        if abs(cpa_dir[2]) < 0.9:
            perp = np.cross(cpa_dir, [0, 0, 1])
        else:
            perp = np.cross(cpa_dir, [1, 0, 0])
        perp = perp / np.linalg.norm(perp)

        self.cpa_pos = cpa_pos
        self.direction = perp

    def get_position(self, t):
        offset = self.speed * (t - self.total_duration / 2)
        return self.cpa_pos + self.direction * offset


class ArcTrajectory(Trajectory):
    def __init__(self, radius, elevation, azimuth_start, azimuth_end, speed):
        self.radius = radius
        self.elevation = elevation
        self.az_start = azimuth_start
        self.az_end = azimuth_end
        angular_extent = abs(azimuth_end - azimuth_start)
        arc_length = radius * angular_extent
        self.speed = speed
        self.duration = arc_length / speed if speed > 0 else 1.0

    def get_position(self, t):
        frac = min(t / self.duration, 1.0)
        az = self.az_start + (self.az_end - self.az_start) * frac
        x = self.radius * np.sin(self.elevation) * np.cos(az)
        y = self.radius * np.sin(self.elevation) * np.sin(az)
        z = self.radius * np.cos(self.elevation)
        return np.array([x, y, z])


class OscillatingTrajectory(Trajectory):
    def __init__(self, closest_distance, closest_azimuth, closest_elevation,
                 cross_range, period):
        self.cross_range = cross_range
        self.period = period
        self.omega = 2 * np.pi / period

        cpa_pos = closest_distance * np.array([
            np.sin(closest_elevation) * np.cos(closest_azimuth),
            np.sin(closest_elevation) * np.sin(closest_azimuth),
            np.cos(closest_elevation),
        ])

        cpa_dir = cpa_pos / (np.linalg.norm(cpa_pos) + 1e-10)
        if abs(cpa_dir[2]) < 0.9:
            perp = np.cross(cpa_dir, [0, 0, 1])
        else:
            perp = np.cross(cpa_dir, [1, 0, 0])
        perp = perp / np.linalg.norm(perp)

        self.cpa_pos = cpa_pos
        self.direction = perp

    def get_position(self, t):
        offset = self.cross_range * np.sin(self.omega * t)
        return self.cpa_pos + self.direction * offset


class WaypointTrajectory(Trajectory):
    def __init__(self, waypoints):
        self.waypoints = sorted(waypoints, key=lambda w: w[0])
        self.times = np.array([w[0] for w in self.waypoints])
        self.positions = np.array([w[1] for w in self.waypoints])

    def get_position(self, t):
        if t <= self.times[0]:
            return self.positions[0].copy()
        if t >= self.times[-1]:
            return self.positions[-1].copy()

        idx = max(0, min(
            int(np.searchsorted(self.times, t)) - 1,
            len(self.times) - 2,
        ))

        t0, t1 = self.times[idx], self.times[idx + 1]
        p0, p1 = self.positions[idx], self.positions[idx + 1]
        frac = (t - t0) / (t1 - t0)
        return p0 + frac * (p1 - p0)


def make_trajectory(drone_config):
    az0 = np.radians(drone_config.initial_bearing["azimuth_deg"])
    el0 = np.radians(drone_config.initial_bearing["elevation_deg"])
    dist = drone_config.distance
    pos0 = np.array([
        dist * np.sin(el0) * np.cos(az0),
        dist * np.sin(el0) * np.sin(az0),
        dist * np.cos(el0),
    ])

    traj_dict = drone_config.trajectory

    if traj_dict:
        ttype = traj_dict.get("type", "linear")

        if ttype == "linear":
            vel = traj_dict.get("velocity", [0, 0, 0])
            return LinearTrajectory(pos0, vel)

        elif ttype == "flyby":
            cd = traj_dict.get("closest_distance", 5.0)
            caz = np.radians(traj_dict.get("closest_azimuth_deg", 0.0))
            cel = np.radians(traj_dict.get("closest_elevation_deg", 30.0))
            spd = traj_dict.get("speed", 8.0)
            dur = traj_dict.get("total_duration", 15.0)
            return FlybyTrajectory(cd, caz, cel, spd, dur)

        elif ttype == "arc":
            r = traj_dict.get("radius", 15.0)
            el = np.radians(traj_dict.get("elevation_deg", 25.0))
            az_start = np.radians(traj_dict.get("azimuth_start_deg", -50.0))
            az_end = np.radians(traj_dict.get("azimuth_end_deg", 50.0))
            spd = traj_dict.get("speed", 5.0)
            return ArcTrajectory(r, el, az_start, az_end, spd)

        elif ttype == "oscillating":
            cd = traj_dict.get("closest_distance", 7.0)
            caz = np.radians(traj_dict.get("closest_azimuth_deg", 0.0))
            cel = np.radians(traj_dict.get("closest_elevation_deg", 30.0))
            cr = traj_dict.get("cross_range", 14.0)
            period = traj_dict.get("period", 12.0)
            return OscillatingTrajectory(cd, caz, cel, cr, period)

        elif ttype == "waypoint":
            wpts = traj_dict.get("waypoints", [])
            parsed = [(w["time"], w["position"]) for w in wpts]
            return WaypointTrajectory(parsed)

    if drone_config.motion.enabled:
        vel = drone_config.motion.velocity
        return LinearTrajectory(pos0, vel)

    return LinearTrajectory(pos0, [0, 0, 0])
