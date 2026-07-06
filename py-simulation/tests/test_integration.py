"""End-to-end integration tests: full Simulation.run() pipeline and result cache.

These are the regression net for refactoring: a tiny, fast, high-SNR
configuration that must keep localizing correctly as internals change.
"""

import unittest
from unittest import mock

import numpy as np

from src.config import Config
from src.results import cache as cache_mod
from src.results.cache import (
    CACHE_SCHEMA_VERSION,
    _cache_dir,
    cached_run,
    clear_cache,
    has_cached,
)
from src.simulation import Simulation


def _quick_config(**signal_overrides) -> Config:
    signal = {"duration": 0.5, "snr_db": 30.0, "seed": 42}
    signal.update(signal_overrides)
    return Config.from_dict({
        "signal": signal,
        "srpphat": {"search": {"resolution_deg": 8.0}},
        "environment": {"enabled": False},
    })


class TestSimulationSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = _quick_config()
        sim = Simulation(cls.config)
        cls.srp = sim.srp
        cls.results = sim.run()

    def test_result_shapes(self):
        n_frames = self.results["n_frames"]
        self.assertGreater(n_frames, 0)
        self.assertEqual(
            self.results["srp_maps"].shape,
            (n_frames, self.srp.n_az, self.srp.n_el),
        )
        self.assertEqual(self.results["true_doas"].shape, (n_frames, 2))
        self.assertEqual(self.results["estimated_doas"].shape, (n_frames, 2))
        self.assertEqual(self.results["detections"].shape, (n_frames,))
        self.assertEqual(self.results["timestamps"].shape, (n_frames,))

    def test_metrics_finite(self):
        metrics = self.results["metrics"]
        self.assertTrue(np.isfinite(metrics.detection_rate))
        self.assertTrue(np.isfinite(metrics.mean_angular_error_deg))
        self.assertTrue(np.isfinite(metrics.mean_psr_db))
        self.assertEqual(metrics.n_total, self.results["n_frames"])

    def test_high_snr_localizes(self):
        metrics = self.results["metrics"]
        self.assertGreater(metrics.detection_rate, 0.5)
        # At 30 dB SNR with a clean stationary source the mean error must be
        # below one grid cell.
        resolution = self.config.srpphat.search.resolution_deg
        self.assertLess(metrics.mean_angular_error_deg, resolution)

    def test_seed_makes_run_deterministic(self):
        repeat = Simulation(_quick_config()).run()
        np.testing.assert_array_equal(
            repeat["estimated_doas"], self.results["estimated_doas"]
        )
        np.testing.assert_array_equal(repeat["detections"], self.results["detections"])


class TestCacheIntegration(unittest.TestCase):
    def setUp(self):
        # Distinct config so we only ever touch our own cache entry.
        self.config = _quick_config(duration=0.4)
        clear_cache(self.config)

    def tearDown(self):
        clear_cache(self.config)

    def test_cache_path_is_versioned(self):
        self.assertIn(f"v{CACHE_SCHEMA_VERSION}", _cache_dir(self.config).parts)

    def test_cached_run_roundtrip(self):
        self.assertFalse(has_cached(self.config))
        first = cached_run(self.config)
        self.assertTrue(has_cached(self.config))

        second = cached_run(self.config)
        self.assertEqual(
            second["metrics"].detection_rate, first["metrics"].detection_rate
        )
        np.testing.assert_array_equal(
            second["estimated_doas"], first["estimated_doas"]
        )

    def test_version_bump_invalidates_cache(self):
        cache_mod.save_cache(self.config, cached_run(self.config))
        self.assertTrue(has_cached(self.config))
        with mock.patch.object(
            cache_mod, "CACHE_SCHEMA_VERSION", CACHE_SCHEMA_VERSION + 1
        ):
            self.assertFalse(has_cached(self.config))
        self.assertTrue(has_cached(self.config))
