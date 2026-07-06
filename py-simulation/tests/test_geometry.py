"""Geometry abstraction tests: subclasses, factory, config union."""

import unittest

import numpy as np

from src.config import (
    ArbitraryArrayConfig,
    ArrayConfig,
    Config,
    DualRingArrayConfig,
    SingleRingArrayConfig,
)
from src.geometry import (
    ArbitraryArray,
    ArrayGeometry,
    DualRingArray,
    SingleRingArray,
    cartesian_to_angles,
    direction_vectors,
    make_array,
)


class TestDualRingArray(unittest.TestCase):
    def test_positions_match_pre_refactor_layout(self):
        cfg = DualRingArrayConfig(
            ring1_radius=0.34, ring2_radius=0.17,
            n_mics_ring1=8, n_mics_ring2=8, ring_spacing=0.20,
        )
        array = DualRingArray(cfg)
        self.assertEqual(array.n_mics, 16)
        # First mic of each ring lies on +x at z = ∓spacing/2.
        np.testing.assert_allclose(array.positions[0], [0.34, 0.0, -0.10])
        np.testing.assert_allclose(array.positions[8], [0.17, 0.0, 0.10])
        # Rings are centered and evenly spread.
        np.testing.assert_allclose(array.positions[:8].sum(axis=0)[:2], 0.0, atol=1e-12)
        np.testing.assert_allclose(
            np.linalg.norm(array.positions[:8, :2], axis=1), 0.34
        )

    def test_backward_compatible_alias(self):
        self.assertIs(ArrayConfig, DualRingArrayConfig)
        with self.assertRaises(Exception):
            ArrayConfig(mic_radius=0.005)  # extra keys now rejected


class TestSingleRingArray(unittest.TestCase):
    def test_matches_degenerate_dual_ring(self):
        single = SingleRingArray(SingleRingArrayConfig(radius=0.3, n_mics=8))
        dual = DualRingArray(DualRingArrayConfig(
            ring1_radius=0.3, ring2_radius=0.3,
            n_mics_ring1=8, n_mics_ring2=8, ring_spacing=1e-9,
        ))
        np.testing.assert_allclose(
            single.positions, dual.positions[:8], atol=1e-9
        )


class TestArbitraryArray(unittest.TestCase):
    def test_inline_positions(self):
        cfg = ArbitraryArrayConfig(positions=[(0, 0, 0), (0.1, 0, 0), (0, 0.1, 0)])
        array = ArbitraryArray(cfg)
        self.assertEqual(array.n_mics, 3)
        np.testing.assert_allclose(array.positions[1], [0.1, 0.0, 0.0])

    def test_requires_exactly_one_source(self):
        with self.assertRaises(Exception):
            ArbitraryArrayConfig()
        with self.assertRaises(Exception):
            ArbitraryArrayConfig(positions=[(0, 0, 0), (1, 0, 0)], csv_path="x.csv")


class TestMakeArrayAndUnion(unittest.TestCase):
    def test_yaml_without_type_is_dual_ring(self):
        cfg = Config.from_dict({"array": {"ring1_radius": 0.3}})
        self.assertIsInstance(cfg.array, DualRingArrayConfig)
        self.assertIsInstance(make_array(cfg.array), DualRingArray)

    def test_union_dispatch(self):
        cfg = Config.from_dict({"array": {"type": "single_ring", "radius": 0.2}})
        self.assertIsInstance(cfg.array, SingleRingArrayConfig)
        array = make_array(cfg.array)
        self.assertIsInstance(array, SingleRingArray)
        self.assertEqual(array.n_mics, 16)

    def test_union_roundtrip(self):
        cfg = Config.from_dict({
            "array": {"type": "xyz", "positions": [[0, 0, 0], [0.1, 0, 0]]},
        })
        again = Config.from_dict(cfg.to_dict())
        self.assertEqual(cfg.array, again.array)

    def test_steering_and_tdoa_consistent_across_types(self):
        directions = direction_vectors(
            np.array([[0.3]]), np.array([[0.5]])
        )
        for array_cfg in (
            DualRingArrayConfig(),
            SingleRingArrayConfig(),
            ArbitraryArrayConfig(positions=[(0.1, 0, 0), (-0.1, 0, 0), (0, 0.1, 0)]),
        ):
            array = make_array(array_cfg)
            delays = array.get_steering_delays(directions)
            self.assertEqual(delays.shape, (array.n_mics, 1))
            self.assertTrue(np.all(np.isfinite(delays)))

    def test_angles_roundtrip(self):
        az, el = 0.4, 1.1
        vec = direction_vectors(np.array([[az]]), np.array([[el]]))[0]
        az2, el2 = cartesian_to_angles(vec)
        self.assertAlmostEqual(az, float(az2))
        self.assertAlmostEqual(el, float(el2))


class TestEndToEndAllGeometries(unittest.TestCase):
    def test_simulation_runs_for_all_array_types(self):
        from src.simulation import Simulation

        base = {
            "signal": {"duration": 0.3, "snr_db": 30.0, "seed": 3},
            "srpphat": {"search": {"resolution_deg": 10.0}},
            "environment": {"enabled": False},
        }
        ring16 = [
            (0.25 * np.cos(a), 0.25 * np.sin(a), 0.0)
            for a in np.arange(8) * 2 * np.pi / 8
        ]
        for array in (
            {"type": "dual_ring"},
            {"type": "single_ring", "radius": 0.25, "n_mics": 8},
            {"type": "xyz", "positions": ring16},
        ):
            with self.subTest(array=array["type"]):
                results = Simulation(Config.from_dict({**base, "array": array})).run()
                self.assertGreater(results["n_frames"], 0)
                self.assertTrue(
                    np.isfinite(results["metrics"].mean_angular_error_deg)
                )
