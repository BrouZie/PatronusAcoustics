import unittest
import numpy as np
from pathlib import Path

from src.config import Config, SignalConfig, DroneConfig, EnvironmentConfig
from src.main import apply_overrides


class MockArgs:
    def __init__(self, **kwargs):
        self.ring1_radius = None
        self.ring2_radius = None
        self.n_mics_1 = None
        self.n_mics_2 = None
        self.ring_spacing = None
        self.snr = None
        self.duration = None
        self.azimuth = None
        self.elevation = None
        self.moving = False
        self.quick = False
        self.no_animation = False
        self.no_3d_animation = False
        self.no_figures = False
        self.config = str(Path(__file__).resolve().parent.parent / "config" / "default.yaml")
        for k, v in kwargs.items():
            setattr(self, k, v)


class TestSignalConfig(unittest.TestCase):
    def test_ein_snr_defaults(self):
        sc = SignalConfig()
        self.assertIsNone(sc.snr_db)
        self.assertEqual(sc.drone_spl_db, 70.0)

    def test_manual_snr_override(self):
        sc = SignalConfig(snr_db=25.0)
        self.assertEqual(sc.snr_db, 25.0)

    def test_drone_spl_changes_snr(self):
        cfg = Config.from_yaml(str(Path(__file__).resolve().parent.parent / "config" / "default.yaml"))
        self.assertIsNone(cfg.signal.snr_db)
        self.assertEqual(cfg.signal.drone_spl_db, 70.0)

    def test_mic_config_defaults(self):
        cfg = Config.from_yaml(str(Path(__file__).resolve().parent.parent / "config" / "default.yaml"))
        self.assertEqual(cfg.mic.snr_dba, 65)
        self.assertEqual(cfg.mic.sensitivity_dbFS, -26.0)


class TestQuickFlag(unittest.TestCase):
    def test_quick_overrides_are_applied(self):
        cfg = SignalConfig(duration=15.0)
        args = MockArgs(quick=True)
        config = Config(signal=cfg)
        config = apply_overrides(config, args)
        self.assertEqual(config.signal.duration, 4.0)
        self.assertEqual(config.srpphat.max_freq, 2000.0)
        self.assertEqual(config.srpphat.search.resolution_deg, 4.0)
        self.assertFalse(config.output.save_animation)

    def test_snr_override(self):
        cfg = SignalConfig(snr_db=None)
        args = MockArgs(snr=25.0)
        config = Config(signal=cfg)
        config = apply_overrides(config, args)
        self.assertEqual(config.signal.snr_db, 25.0)

    def test_snr_override_preserves_none(self):
        cfg = SignalConfig(snr_db=None)
        args = MockArgs()
        config = Config(signal=cfg)
        config = apply_overrides(config, args)
        self.assertIsNone(config.signal.snr_db)


if __name__ == "__main__":
    unittest.main()
