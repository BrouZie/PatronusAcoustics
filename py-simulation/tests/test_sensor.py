"""Tests for the sensor model: EIN budget, imperfections, degradation."""

import unittest

import numpy as np

from src.config import Config
from src.sensor import SensorModel, effective_snr_db
from src.simulation import Simulation


def _config(imperfections=None, **signal_overrides):
    signal = {"duration": 0.5, "snr_db": 30.0, "seed": 42}
    signal.update(signal_overrides)
    mic = {"imperfections": imperfections} if imperfections else {}
    return Config.from_dict({
        "signal": signal,
        "mic": mic,
        "srpphat": {"search": {"resolution_deg": 8.0}},
        "environment": {"enabled": False},
    })


class TestEffectiveSnr(unittest.TestCase):
    def test_override_wins(self):
        cfg = Config.from_dict({"signal": {"snr_db": 12.5}})
        self.assertEqual(effective_snr_db(cfg), 12.5)

    def test_ein_budget_without_absorption(self):
        # drone_spl 70 dB @1m, distance 10 m, mic SNR 65 dBA:
        # SNR = 70 - 20*log10(10) - (94 - 65) = 70 - 20 - 29 = 21 dB
        cfg = Config.from_dict({"signal": {"snr_db": None}})
        self.assertAlmostEqual(effective_snr_db(cfg), 21.0, places=6)

    def test_absorption_reduces_snr(self):
        from src.absorption import AtmosphericAbsorption
        cfg = Config.from_dict({
            "signal": {"snr_db": None}, "drone": {"distance": 50.0},
        })
        absorption = AtmosphericAbsorption(20.0, 50.0, 101.325)
        self.assertLess(
            effective_snr_db(cfg, absorption), effective_snr_db(cfg)
        )


class TestSensorModel(unittest.TestCase):
    def test_ideal_by_default(self):
        cfg = _config()
        sensor = SensorModel(cfg.mic, 16, 48000)
        self.assertTrue(sensor.is_ideal)
        np.testing.assert_array_equal(sensor.gains, np.ones(16))
        np.testing.assert_array_equal(sensor.position_offsets, np.zeros((16, 3)))

    def test_failed_mic_is_zeroed(self):
        cfg = _config(imperfections={"failed_mics": [3]})
        sensor = SensorModel(cfg.mic, 4, 48000)
        out = sensor.apply(np.random.default_rng(0).normal(size=(4, 1024)))
        np.testing.assert_array_equal(out[3], 0.0)
        self.assertGreater(np.abs(out[0]).max(), 0.0)

    def test_quantization_error_bounded(self):
        x = np.random.default_rng(0).uniform(-0.9, 0.9, size=(2, 512))
        for bits in (8, 16, 24):
            q = SensorModel._quantize(x, bits)
            self.assertLessEqual(np.abs(q - x).max(), 2.0 ** -(bits - 1))

    def test_gain_mismatch_draw_is_deterministic(self):
        cfg = _config(imperfections={"gain_std_db": 1.0, "seed": 7})
        s1 = SensorModel(cfg.mic, 16, 48000)
        s2 = SensorModel(cfg.mic, 16, 48000)
        np.testing.assert_array_equal(s1.gains, s2.gains)
        self.assertGreater(np.std(s1.gains), 0.0)


class TestImperfectionDegradation(unittest.TestCase):
    """A badly built array must measurably underperform the ideal one."""

    def test_position_and_phase_error_degrade_performance(self):
        ideal = Simulation(_config()).run()["metrics"]
        rough = Simulation(_config(imperfections={
            "position_std_mm": 20.0,
            "phase_std_deg": 45.0,
            "seed": 1,
        })).run()["metrics"]

        degraded = (
            rough.mean_psr_db < ideal.mean_psr_db
            or rough.mean_angular_error_deg > ideal.mean_angular_error_deg
            or rough.detection_rate < ideal.detection_rate
        )
        self.assertTrue(
            degraded,
            f"imperfect array did not degrade: ideal PSR {ideal.mean_psr_db:.2f}, "
            f"rough PSR {rough.mean_psr_db:.2f}; ideal err "
            f"{ideal.mean_angular_error_deg:.2f}°, rough err "
            f"{rough.mean_angular_error_deg:.2f}°",
        )
