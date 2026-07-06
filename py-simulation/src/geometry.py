"""Microphone array geometries.

`ArrayGeometry` holds everything the pipeline needs from an array —
positions, steering delays, tilt, perturbation — so any candidate geometry
(dual ring, single ring, arbitrary XYZ) runs through the identical
simulation. Build instances via `make_array(array_config, speed_sound)`.
"""

import numpy as np

from .constants import SPEED_OF_SOUND_REF


def direction_vectors(az_rad, el_rad):
    """Unit vectors for (azimuth, elevation) pairs.

    Elevation is the polar angle from boresight (+z): el=0 is boresight,
    el=180° is directly behind the array.
    """
    sin_el = np.sin(el_rad.ravel())
    cos_el = np.cos(el_rad.ravel())
    sin_az = np.sin(az_rad.ravel())
    cos_az = np.cos(az_rad.ravel())
    return np.column_stack([
        sin_el * cos_az,
        sin_el * sin_az,
        cos_el,
    ])


def cartesian_to_angles(vecs):
    vecs = np.asarray(vecs)
    az = np.arctan2(vecs[..., 1], vecs[..., 0])
    el = np.arccos(np.clip(vecs[..., 2], -1.0, 1.0))
    return az, el


class ArrayGeometry:
    """Base array: (n_mics, 3) positions in the array frame, +z = boresight.

    `positions` are the nominal (designed) coordinates — SRP steering uses
    these. `positions_true` are the as-built coordinates (see `perturb`) —
    physical propagation uses these.
    """

    def __init__(self, positions, speed_sound=SPEED_OF_SOUND_REF):
        positions = np.asarray(positions, dtype=float)
        if positions.ndim != 2 or positions.shape[1] != 3:
            raise ValueError(
                f"positions must have shape (n_mics, 3), got {positions.shape}"
            )
        if positions.shape[0] < 2:
            raise ValueError("an array needs at least 2 microphones")
        self.positions = positions
        self.n_mics = positions.shape[0]
        self.positions_true = self.positions
        self.speed_sound = speed_sound

    def perturb(self, offsets):
        offsets = np.asarray(offsets, dtype=float)
        if offsets.shape != self.positions.shape:
            raise ValueError(
                f"offsets shape {offsets.shape} != positions shape {self.positions.shape}"
            )
        self.positions_true = self.positions + offsets

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
        """True (as-built) mic positions in world coordinates — physical
        propagation paths must use these, not the nominal positions."""
        if not self.tilt_active:
            return self.positions_true
        return self.positions_true @ self._R_array_to_world.T

    def get_tdoa(self, source_pos):
        dists = np.linalg.norm(self.positions_true - source_pos, axis=1)
        return dists / self.speed_sound

    def get_steering_delays(self, directions):
        """Steering delays from *nominal* positions — what the DSP knows."""
        return self.positions @ directions.T / self.speed_sound

    # Backward-compatible aliases (prefer the module-level functions).
    direction_vectors = staticmethod(direction_vectors)
    cartesian_to_angles = staticmethod(cartesian_to_angles)


class DualRingArray(ArrayGeometry):
    """Two concentric rings separated along boresight (the pitch design)."""

    def __init__(self, config, speed_sound=SPEED_OF_SOUND_REF):
        self.ring1_radius = config.ring1_radius
        self.ring2_radius = config.ring2_radius
        self.n_mics_ring1 = config.n_mics_ring1
        self.n_mics_ring2 = config.n_mics_ring2
        self.ring_spacing = config.ring_spacing

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

        super().__init__(np.vstack([pos1, pos2]), speed_sound=speed_sound)


class SingleRingArray(ArrayGeometry):
    """Planar UCA — the baseline a dual ring must beat on front/back rejection."""

    def __init__(self, config, speed_sound=SPEED_OF_SOUND_REF):
        self.radius = config.radius
        angles = np.arange(config.n_mics) * 2 * np.pi / config.n_mics
        positions = np.column_stack([
            config.radius * np.cos(angles),
            config.radius * np.sin(angles),
            np.full(config.n_mics, config.z_offset),
        ])
        super().__init__(positions, speed_sound=speed_sound)


class ArbitraryArray(ArrayGeometry):
    """Arbitrary XYZ positions, inline in config or loaded from CSV."""

    def __init__(self, config, speed_sound=SPEED_OF_SOUND_REF):
        if config.positions is not None:
            positions = np.asarray(config.positions, dtype=float)
        else:
            positions = np.loadtxt(config.csv_path, delimiter=",", ndmin=2)
        super().__init__(positions, speed_sound=speed_sound)


def make_array(array_config, speed_sound=SPEED_OF_SOUND_REF) -> ArrayGeometry:
    """Build the geometry matching an array config (union dispatch)."""
    kind = getattr(array_config, "type", "dual_ring")
    if kind == "dual_ring":
        return DualRingArray(array_config, speed_sound=speed_sound)
    if kind == "single_ring":
        return SingleRingArray(array_config, speed_sound=speed_sound)
    if kind == "xyz":
        return ArbitraryArray(array_config, speed_sound=speed_sound)
    raise ValueError(f"unknown array type: {kind!r}")
