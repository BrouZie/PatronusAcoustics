import numpy as np


class DualRingArray:
    def __init__(self, config):
        self.ring1_radius = config.ring1_radius
        self.ring2_radius = config.ring2_radius
        self.n_mics_ring1 = config.n_mics_ring1
        self.n_mics_ring2 = config.n_mics_ring2
        self.ring_spacing = config.ring_spacing
        self.speed_sound = 343.0

        angles1 = np.arange(config.n_mics_ring1) * 2 * np.pi / config.n_mics_ring1
        angles2 = np.arange(config.n_mics_ring2) * 2 * np.pi / config.n_mics_ring2

        pos1 = np.column_stack([
            config.ring1_radius * np.cos(angles1),
            config.ring1_radius * np.sin(angles1),
            np.full(config.n_mics_ring1, -config.ring_spacing / 2),
        ])
        pos2 = np.column_stack([
            config.ring2_radius * np.cos(angles2),
            config.ring2_radius * np.sin(angles2),
            np.full(config.n_mics_ring2, config.ring_spacing / 2),
        ])

        self.positions = np.vstack([pos1, pos2])
        self.n_mics = self.positions.shape[0]

    def set_tilt(self, tilt_deg):
        theta = np.radians(tilt_deg)
        c = np.cos(theta)
        s = np.sin(theta)
        self._R_world_to_array = np.array([
            [1, 0,  0],
            [0, c,  s],
            [0, -s, c],
        ])
        self._R_array_to_world = self._R_world_to_array.T

    @property
    def tilt_active(self):
        return hasattr(self, "_R_world_to_array")

    def world_to_array_coords(self, world_pos):
        if not self.tilt_active:
            return world_pos
        return world_pos @ self._R_world_to_array.T

    def get_mic_positions_world(self):
        if not self.tilt_active:
            return self.positions
        return self.positions @ self._R_array_to_world.T

    def get_tdoa(self, source_pos):
        dists = np.linalg.norm(self.positions - source_pos, axis=1)
        return dists / self.speed_sound

    def get_steering_delays(self, directions):
        return self.positions @ directions.T / self.speed_sound

    @staticmethod
    def direction_vectors(az_rad, el_rad):
        sin_el = np.sin(el_rad.ravel())
        cos_el = np.cos(el_rad.ravel())
        sin_az = np.sin(az_rad.ravel())
        cos_az = np.cos(az_rad.ravel())
        return np.column_stack([
            sin_el * cos_az,
            sin_el * sin_az,
            cos_el,
        ])

    @staticmethod
    def cartesian_to_angles(vecs):
        vecs = np.asarray(vecs)
        az = np.arctan2(vecs[..., 1], vecs[..., 0])
        el = np.arccos(np.clip(vecs[..., 2], -1.0, 1.0))
        return az, el
