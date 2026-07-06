"""Tests for detection-range curves and the compare report."""

import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np

from src.analysis import RangeCurve, range_at_rate, run_range_curve
from src.config import Config


def _curve(distances, rates):
    return RangeCurve(
        distances=np.asarray(distances, dtype=float),
        detection_rate=np.asarray(rates, dtype=float),
        angular_error_deg=np.zeros(len(distances)),
        mirror_suppression_db=np.zeros(len(distances)),
    )


class TestRangeAtRate(unittest.TestCase):
    def test_interpolated_crossing(self):
        curve = _curve([10, 20, 30], [1.0, 0.8, 0.2])
        # 90% crossing between 10 (1.0) and 20 (0.8): 10 + 0.5*10 = 15
        self.assertAlmostEqual(range_at_rate(curve, 0.9), 15.0)

    def test_never_drops_below_target(self):
        curve = _curve([10, 20, 30], [1.0, 0.95, 0.92])
        self.assertTrue(np.isnan(range_at_rate(curve, 0.9)))

    def test_starts_below_target(self):
        curve = _curve([10, 20, 30], [0.5, 0.3, 0.1])
        self.assertTrue(np.isnan(range_at_rate(curve, 0.9)))

    def test_non_monotone_uses_first_crossing(self):
        curve = _curve([10, 20, 30, 40], [1.0, 0.7, 0.95, 0.2])
        self.assertLess(range_at_rate(curve, 0.9), 20.0)


class TestRunRangeCurve(unittest.TestCase):
    def test_curve_runs_and_caches(self):
        base = Config.from_dict({
            "signal": {"duration": 0.3, "snr_db": None},
            "srpphat": {"search": {"resolution_deg": 10.0}},
            "environment": {"enabled": False},
        })
        curve = run_range_curve(base, [5.0, 40.0], n_seeds=1,
                                label="t", verbose=False)
        self.assertEqual(list(curve.distances), [5.0, 40.0])
        self.assertTrue(np.all(curve.detection_rate >= 0))
        self.assertTrue(np.all(curve.detection_rate <= 1))
        # Nearby drone must never detect worse than a far one in a clean env.
        self.assertGreaterEqual(
            curve.detection_rate[0], curve.detection_rate[1] - 0.15
        )

        again = run_range_curve(base, [5.0, 40.0], n_seeds=1,
                                label="t", verbose=False)
        np.testing.assert_array_equal(curve.detection_rate, again.detection_rate)


class TestCompareCli(unittest.TestCase):
    def test_report_file_set(self):
        from src.compare import main
        out = Path(tempfile.mkdtemp())
        try:
            rc = main([
                "config/compare/dual_ring_s20.yaml",
                "config/compare/single_ring_16.yaml",
                "--distances", "10", "30",
                "--seeds", "1", "--quick",
                "--out", str(out),
            ])
            self.assertEqual(rc, 0)
            for name in (
                "report.md",
                "detection_rate_vs_range.png",
                "angular_error_vs_range.png",
                "mirror_suppression_vs_range.png",
                "beampattern_cuts.png",
                "geometries.png",
            ):
                self.assertTrue((out / name).exists(), name)
            report = (out / "report.md").read_text()
            self.assertIn("dual_ring_s20", report)
            self.assertIn("single_ring_16", report)
            self.assertIn("Range@90%", report)
        finally:
            shutil.rmtree(out)
