import unittest
import numpy as np
from pathlib import Path

from src.config import (
    Config, ArrayConfig, SignalConfig, DroneConfig, EnvironmentConfig,
    SearchConfig, SRPPhatConfig, DetectionConfig, MicConfig, MotionConfig,
    GroundConfig, AtmosphericConfig, NoiseConfig, OutputConfig,
    RefractionConfig, TurbulenceConfig,
    deep_merge, parse_dotted_key,
)
from src.main import apply_overrides


CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


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
        self.config = str(CONFIG_DIR / "default.yaml")
        for k, v in kwargs.items():
            setattr(self, k, v)


# ── Existing tests (adapted for new defaults) ───────────────────────────

class TestSignalConfig(unittest.TestCase):
    def test_ein_snr_defaults(self):
        sc = SignalConfig()
        self.assertIsNone(sc.snr_db)
        self.assertEqual(sc.drone_spl_db, 70.0)

    def test_manual_snr_override(self):
        sc = SignalConfig(snr_db=25.0)
        self.assertEqual(sc.snr_db, 25.0)

    def test_drone_spl_changes_snr(self):
        cfg = Config.from_yaml(str(CONFIG_DIR / "default.yaml"))
        self.assertIsNone(cfg.signal.snr_db)
        self.assertEqual(cfg.signal.drone_spl_db, 73.0)

    def test_mic_config_defaults(self):
        cfg = Config.from_yaml(str(CONFIG_DIR / "default.yaml"))
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


# ── New tests: from_dict / to_dict roundtrip ────────────────────────────

class TestFromDict(unittest.TestCase):
    def test_from_none_returns_default(self):
        cfg = Config.from_dict(None)
        self.assertIsInstance(cfg, Config)
        self.assertEqual(cfg.array.ring1_radius, 0.34)

    def test_from_empty_returns_default(self):
        cfg = Config.from_dict({})
        self.assertIsInstance(cfg, Config)
        self.assertEqual(cfg.signal.fs, 48000)

    def test_partial_override(self):
        cfg = Config.from_dict({"signal": {"duration": 10.0}})
        self.assertEqual(cfg.signal.duration, 10.0)
        self.assertEqual(cfg.array.ring1_radius, 0.34)

    def test_full_from_dict_matches_yaml(self):
        yaml_cfg = Config.from_yaml(str(CONFIG_DIR / "default.yaml"))
        raw = yaml_cfg.to_dict()
        dict_cfg = Config.from_dict(raw)
        self.assertEqual(dict_cfg.signal.duration, yaml_cfg.signal.duration)
        self.assertEqual(dict_cfg.array.ring1_radius, yaml_cfg.array.ring1_radius)
        self.assertEqual(dict_cfg.srpphat.fft_size, yaml_cfg.srpphat.fft_size)

    def test_to_dict_roundtrip(self):
        cfg = Config()
        d = cfg.to_dict()
        cfg2 = Config.from_dict(d)
        self.assertEqual(cfg2.array.ring1_radius, cfg.array.ring1_radius)
        self.assertEqual(cfg2.signal.fs, cfg.signal.fs)

    def test_trajectory_dict_preserved(self):
        cfg = Config.from_dict({"drone": {"trajectory": {"type": "arc", "radius": 20}}})
        self.assertEqual(cfg.drone.trajectory, {"type": "arc", "radius": 20})

    def test_initial_bearing_dict_preserved(self):
        cfg = Config.from_dict({"drone": {"initial_bearing": {"azimuth_deg": 45.0, "elevation_deg": 10.0}}})
        self.assertEqual(cfg.drone.initial_bearing["azimuth_deg"], 45.0)


# ── New tests: to_dict ──────────────────────────────────────────────────

class TestToDict(unittest.TestCase):
    def test_to_dict_has_all_keys(self):
        cfg = Config()
        d = cfg.to_dict()
        for key in ("array", "signal", "mic", "drone", "srpphat", "environment", "output"):
            self.assertIn(key, d)
        self.assertIn("ring1_radius", d["array"])

    def test_to_dict_tuples_to_lists(self):
        cfg = Config()
        d = cfg.to_dict()
        motion = d["drone"]["motion"]
        self.assertIsInstance(motion["velocity"], list)


# ── New tests: merge ────────────────────────────────────────────────────

class TestMerge(unittest.TestCase):
    def test_merge_overrides_single_field(self):
        cfg = Config()
        merged = cfg.merge({"signal": {"duration": 99.0}})
        self.assertEqual(merged.signal.duration, 99.0)
        self.assertEqual(merged.array.ring1_radius, cfg.array.ring1_radius)

    def test_merge_deeply_nested(self):
        cfg = Config()
        merged = cfg.merge({"environment": {"atmospheric": {"humidity_pct": 80}}})
        self.assertEqual(merged.environment.atmospheric.humidity_pct, 80)

    def test_merge_does_not_mutate_original(self):
        cfg = Config()
        cfg.merge({"signal": {"duration": 99.0}})
        self.assertEqual(cfg.signal.duration, 5.0)


# ── New tests: from_yamls ───────────────────────────────────────────────

class TestFromYamls(unittest.TestCase):
    def test_two_files_merged(self):
        cfg = Config.from_yamls(
            str(CONFIG_DIR / "default.yaml"),
            str(CONFIG_DIR / "benchmark.yaml"),
        )
        # benchmark's signal.duration=2.0 should override default's 15.0
        self.assertEqual(cfg.signal.duration, 2.0)
        self.assertIsNotNone(cfg.signal.snr_db)


# ── New tests: validation ───────────────────────────────────────────────

class TestValidation(unittest.TestCase):
    def test_array_bad_radius(self):
        with self.assertRaises(ValueError):
            ArrayConfig(ring1_radius=-1)

    def test_array_zero_mics(self):
        with self.assertRaises(ValueError):
            ArrayConfig(n_mics_ring1=1)

    def test_signal_bad_fs(self):
        with self.assertRaises(ValueError):
            SignalConfig(fs=100)

    def test_signal_negative_duration(self):
        with self.assertRaises(ValueError):
            SignalConfig(duration=-1)

    def test_signal_bad_snr(self):
        with self.assertRaises(ValueError):
            SignalConfig(snr_db=100)

    def test_search_bad_resolution(self):
        with self.assertRaises(ValueError):
            SearchConfig(resolution_deg=0)

    def test_detection_bad_method(self):
        with self.assertRaises(ValueError):
            DetectionConfig(method="invalid")

    def test_srpphat_bad_fft_size(self):
        with self.assertRaises(ValueError):
            SRPPhatConfig(fft_size=1000)

    def test_srpphat_bad_hop_length(self):
        with self.assertRaises(ValueError):
            SRPPhatConfig(hop_length=99999)

    def test_srpphat_bad_mode(self):
        with self.assertRaises(ValueError):
            SRPPhatConfig(mode="invalid")

    def test_ground_bad_reflection_coefficient(self):
        with self.assertRaises(ValueError):
            GroundConfig(reflection_coefficient=-0.1)

    def test_ground_bad_model(self):
        with self.assertRaises(ValueError):
            GroundConfig(model="invalid")

    def test_atmospheric_bad_temperature(self):
        with self.assertRaises(ValueError):
            AtmosphericConfig(temperature_C=100)

    def test_atmospheric_bad_humidity(self):
        with self.assertRaises(ValueError):
            AtmosphericConfig(humidity_pct=-1)

    def test_noise_bad_wind_speed(self):
        with self.assertRaises(ValueError):
            NoiseConfig(wind_speed_ms=-1)

    def test_noise_bad_traffic_density(self):
        with self.assertRaises(ValueError):
            NoiseConfig(traffic_density="invalid")

    def test_output_bad_fps(self):
        with self.assertRaises(ValueError):
            OutputConfig(animation_fps=200)

    def test_drone_bad_rpm(self):
        with self.assertRaises(ValueError):
            DroneConfig(rpm=-1, initial_bearing={"azimuth_deg": 0, "elevation_deg": 0})

    def test_drone_bad_num_blades(self):
        with self.assertRaises(ValueError):
            DroneConfig(num_blades=0, initial_bearing={"azimuth_deg": 0, "elevation_deg": 0})

    def test_config_from_dict_validation(self):
        with self.assertRaises(ValueError):
            Config.from_dict({"array": {"ring1_radius": -1}})

    def test_config_from_yaml_validation(self):
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("array:\n  ring1_radius: -1\n")
            path = f.name
        try:
            with self.assertRaises(ValueError):
                Config.from_yaml(path)
        finally:
            os.unlink(path)

    def test_merge_bad_value_raises(self):
        cfg = Config()
        with self.assertRaises(ValueError):
            cfg.merge({"array": {"ring1_radius": -1}})

    def test_refraction_bad_roughness(self):
        with self.assertRaises(ValueError):
            RefractionConfig(roughness_length=0)

    def test_turbulence_bad_scintillation(self):
        with self.assertRaises(ValueError):
            TurbulenceConfig(scintillation_strength=5.0)


# ── New tests: schema ──────────────────────────────────────────────────

class TestSchema(unittest.TestCase):
    def test_schema_returns_string(self):
        s = Config.schema()
        self.assertIsInstance(s, str)
        self.assertIn("ring1_radius: 0.34", s)
        self.assertIn("array:", s)
        self.assertNotIn("MISSING_TYPE", s)


# ── New tests: deep_merge / parse_dotted_key ───────────────────────────

class TestMergeHelpers(unittest.TestCase):
    def test_parse_dotted_key_single(self):
        result = parse_dotted_key("drone.distance", 100)
        self.assertEqual(result, {"drone": {"distance": 100}})

    def test_parse_dotted_key_deep(self):
        result = parse_dotted_key("a.b.c", 1)
        self.assertEqual(result, {"a": {"b": {"c": 1}}})

    def test_deep_merge_overwrites_scalar(self):
        base = {"a": 1, "b": 2}
        deep_merge(base, {"a": 99})
        self.assertEqual(base["a"], 99)

    def test_deep_merge_nested(self):
        base = {"drone": {"distance": 10, "rpm": 6000}}
        deep_merge(base, {"drone": {"distance": 100}})
        self.assertEqual(base["drone"]["distance"], 100)
        self.assertEqual(base["drone"]["rpm"], 6000)

    def test_deep_merge_new_key(self):
        base = {"a": 1}
        deep_merge(base, {"b": 2})
        self.assertEqual(base["b"], 2)


if __name__ == "__main__":
    unittest.main()
