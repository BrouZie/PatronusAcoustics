"""Front/back rejection: full-sphere search, mirror metrics, az wraparound.

The dual-ring axial separation exists solely to break front/back mirror
symmetry — the planar-vs-separated contrast here validates that premise.
"""

import unittest

import numpy as np

from src.config import Config
from src.metrics import (
    front_back_metrics,
    mirror_direction,
    peak_to_sidelobe_ratio,
)
from src.simulation import Simulation


def _full_sphere_config(array: dict) -> Config:
    return Config.from_dict({
        "array": array,
        "signal": {"duration": 0.5, "snr_db": 30.0, "seed": 5},
        "srpphat": {
            "search": {"coverage": "full_sphere", "resolution_deg": 8.0},
        },
        "environment": {"enabled": False},
    })


class TestMirrorDirection(unittest.TestCase):
    def test_mirror_about_ring_plane(self):
        az, el = mirror_direction(0.3, np.radians(30.0))
        self.assertAlmostEqual(az, 0.3)
        self.assertAlmostEqual(np.degrees(el), 150.0)

    def test_ring_plane_is_own_mirror(self):
        _, el = mirror_direction(0.0, np.pi / 2)
        self.assertAlmostEqual(el, np.pi / 2)


class TestPsrAzWraparound(unittest.TestCase):
    def test_wrapped_mainlobe_not_counted_as_sidelobe(self):
        srp = np.full((36, 11), 0.1)
        srp[0, 5] = 1.0    # peak at the azimuth seam
        srp[35, 5] = 0.9   # its own mainlobe, wrapped across the seam
        psr_wrap = peak_to_sidelobe_ratio(srp, wrap_az=True)
        psr_no_wrap = peak_to_sidelobe_ratio(srp, wrap_az=False)
        self.assertGreater(psr_wrap, psr_no_wrap + 5.0)


class TestFrontBackMetrics(unittest.TestCase):
    def test_confused_when_peak_on_wrong_side(self):
        az = np.radians(np.arange(-180, 181, 8.0))
        el = np.radians(np.arange(0, 181, 8.0))
        srp = np.ones((len(az), len(el)))
        true_doa = (0.0, np.radians(24.0))
        mirror_el_idx = np.argmin(np.abs(el - (np.pi - true_doa[1])))
        az_idx = np.argmin(np.abs(az - 0.0))
        srp[az_idx, mirror_el_idx] = 10.0  # dominant lobe at the mirror

        fb = front_back_metrics(srp, az, el, true_doa)
        self.assertTrue(fb["confused"])
        self.assertLess(fb["mirror_suppression_db"], 0.0)


class TestFrontBackPhysics(unittest.TestCase):
    """The headline physics: axial separation buys mirror rejection."""

    @classmethod
    def setUpClass(cls):
        planar_cfg = _full_sphere_config({
            "type": "dual_ring", "ring_spacing": 0.001,
        })
        separated_cfg = _full_sphere_config({
            "type": "dual_ring", "ring_spacing": 0.20,
        })
        cls.planar = Simulation(planar_cfg).run()["metrics"]
        cls.separated = Simulation(separated_cfg).run()["metrics"]

    def test_metrics_populated_for_full_sphere(self):
        self.assertFalse(np.isnan(self.planar.mean_mirror_suppression_db))
        self.assertFalse(np.isnan(self.separated.mean_mirror_suppression_db))

    def test_planar_array_cannot_reject_mirror(self):
        # A (near-)planar array's SRP map is symmetric about the ring plane.
        self.assertLess(abs(self.planar.mean_mirror_suppression_db), 1.0)

    def test_axial_separation_buys_suppression(self):
        self.assertGreater(
            self.separated.mean_mirror_suppression_db,
            self.planar.mean_mirror_suppression_db + 2.0,
            f"spacing 0.20 m suppression "
            f"{self.separated.mean_mirror_suppression_db:.2f} dB not clearly "
            f"above planar {self.planar.mean_mirror_suppression_db:.2f} dB",
        )
        self.assertLess(
            self.separated.front_back_confusion_rate,
            0.5,
        )

    def test_window_coverage_reports_nan(self):
        cfg = Config.from_dict({
            "signal": {"duration": 0.3, "snr_db": 30.0, "seed": 5},
            "srpphat": {"search": {"resolution_deg": 10.0}},
            "environment": {"enabled": False},
        })
        metrics = Simulation(cfg).run()["metrics"]
        self.assertTrue(np.isnan(metrics.mean_mirror_suppression_db))
        self.assertTrue(np.isnan(metrics.front_back_confusion_rate))
