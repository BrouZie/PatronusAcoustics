"""Tests for triangulation geometry and the MCU compute budget."""

import unittest

import numpy as np

from src.analysis.mcu_budget import estimate, estimate_from_config
from src.analysis.triangulation import (
    position_error_map,
    triangulate,
    vector_to_bearing,
)
from src.config import Config


class TestTriangulate(unittest.TestCase):
    def test_exact_bearings_recover_point(self):
        stations = np.array([[-20.0, 0.0, 0.0], [20.0, 0.0, 0.0]])
        target = np.array([5.0, 60.0, 30.0])
        bearings = np.array([vector_to_bearing(target - s) for s in stations])
        est = triangulate(stations, bearings)
        np.testing.assert_allclose(est, target, atol=1e-9)

    def test_three_stations(self):
        stations = np.array([
            [-20.0, 0.0, 0.0], [20.0, 0.0, 0.0], [0.0, 50.0, 0.0],
        ])
        target = np.array([-10.0, 25.0, 40.0])
        bearings = np.array([vector_to_bearing(target - s) for s in stations])
        np.testing.assert_allclose(triangulate(stations, bearings), target,
                                   atol=1e-9)

    def test_error_map_zero_sigma_is_exact(self):
        result = position_error_map(40.0, 0.0, extent_m=60.0, grid_n=5,
                                    n_trials=3)
        self.assertLess(float(np.max(result["rms_error_m"])), 1e-6)

    def test_error_grows_with_range(self):
        result = position_error_map(40.0, 3.0, extent_m=80.0, grid_n=7,
                                    n_trials=40)
        err = result["rms_error_m"]
        mid = err.shape[0] // 2
        near = err[mid, 0]   # closest y row
        far = err[mid, -1]   # farthest y row
        self.assertGreater(far, near)


class TestMcuBudget(unittest.TestCase):
    def test_memory_matches_actual_phase_tensor(self):
        from src.config import DualRingArrayConfig, SearchConfig, DetectionConfig
        from src.geometry import DualRingArray
        from src.srpphat import SRPPhatProcessor

        array = DualRingArray(DualRingArrayConfig())
        search = SearchConfig(azimuth_range=[-60, 60],
                              elevation_range=[-60, 60], resolution_deg=4.0)
        srp = SRPPhatProcessor(
            array=array, fs=48000, fft_size=2048, hop_length=512,
            search_config=search, max_freq=4000.0,
            detection_config=DetectionConfig(enabled=False),
        )
        # Match the processor's actual dtype (complex128 when the C++
        # extension is built, complex64 on the pure-numpy path).
        budget = estimate(
            n_mics=array.n_mics, fft_size=2048, hop_length=512, fs=48000,
            n_directions=srp.n_directions, max_freq=4000.0,
            dtype_bytes=srp.phase.itemsize,
        )
        self.assertEqual(budget.n_freqs_used, srp.n_freqs_used)
        actual_mb = srp.phase.nbytes / 2 ** 20
        self.assertAlmostEqual(budget.phase_tensor_mb, actual_mb, delta=0.01)

    def test_more_directions_cost_more(self):
        small = estimate(16, 2048, 512, 48000, 1000, 4000.0)
        large = estimate(16, 2048, 512, 48000, 16000, 4000.0)
        self.assertGreater(large.macs_per_frame, small.macs_per_frame)
        self.assertGreater(large.phase_tensor_mb, small.phase_tensor_mb)

    def test_huge_grid_flagged_infeasible(self):
        huge = estimate(16, 2048, 512, 48000, 40000, 4000.0)
        self.assertFalse(huge.fits_memory)
        self.assertFalse(huge.fits_h753)

    def test_estimate_from_config(self):
        cfg = Config.from_dict({
            "srpphat": {"search": {"resolution_deg": 4.0}},
        })
        budget = estimate_from_config(cfg, n_mics=16)
        self.assertGreater(budget.n_directions, 0)
        self.assertIn("MB", budget.summary())
