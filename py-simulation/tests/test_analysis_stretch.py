"""Tests for triangulation geometry and the MCU requirements engine."""

import unittest

import numpy as np

from src.analysis.mcu_requirements import (
    PHASE_TABLE_BYTES,
    compute_requirements,
    evaluate_from_config,
    reference_stage_cycles,
)
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


class TestMcuRequirementsCrossCheck(unittest.TestCase):
    def _cfg(self, resolution_deg=4.0):
        return Config.from_dict({
            "srpphat": {"search": {"resolution_deg": resolution_deg}},
            "mcu": {"enabled": True, "targets": ["stm32h753"],
                    "logmel": {"enabled": False}},
        })

    def test_phase_table_matches_actual_processor_tensor(self):
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
        req = compute_requirements(self._cfg(), n_mics=array.n_mics)
        table = next(c for c in req.stages[0].ram
                     if c.name == "phase_table")
        # The engine assumes complex64 on target; the processor may use
        # complex128 when the C++ extension is built — compare element
        # counts, then bytes at the on-target dtype.
        n_elements = srp.phase.nbytes / srp.phase.itemsize
        self.assertEqual(table.bytes, n_elements * PHASE_TABLE_BYTES)

    def test_finer_grid_costs_more(self):
        coarse = compute_requirements(self._cfg(8.0), 16)
        fine = compute_requirements(self._cfg(2.0), 16)
        self.assertGreater(
            reference_stage_cycles(fine.stages[0]),
            reference_stage_cycles(coarse.stages[0]))
        self.assertGreater(fine.ram_bytes, coarse.ram_bytes)

    def test_huge_grid_flagged_infeasible(self):
        report = evaluate_from_config(self._cfg(1.0), n_mics=16)
        verdict = report.verdicts[0]
        self.assertFalse(verdict.fits_ram)
        self.assertFalse(verdict.fits)
