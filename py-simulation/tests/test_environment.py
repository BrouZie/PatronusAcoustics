import unittest
import numpy as np

from src.environment import GroundReflector, WindSource, BirdSource, Environment
from src.config import EnvironmentConfig, GroundConfig, NoiseConfig


class TestGroundReflector(unittest.TestCase):
    def test_image_source_reflection(self):
        g = GroundReflector(height_m=5.0, reflection_coefficient=0.5)
        drone = np.array([10.0, 0.0, 2.0])
        image = g.get_image_source(drone)
        # Image should be reflected across z = -height
        np.testing.assert_array_almost_equal(image[:2], drone[:2])
        self.assertEqual(image[2], -(drone[2] + 2 * g.height_m))

    def test_image_at_ground_level(self):
        g = GroundReflector(height_m=5.0, reflection_coefficient=0.5)
        drone = np.array([0.0, 0.0, 5.0])
        image = g.get_image_source(drone)
        np.testing.assert_array_almost_equal(image, [0.0, 0.0, -15.0])


class TestWindSource(unittest.TestCase):
    def test_corcos_coherence_structure(self):
        np.random.seed(0)
        mic_pos = self._dual_ring_positions()

        # Corcos: higher wind speed → higher coherence (frozen turbulence)
        ws_low = WindSource(speed_ms=1.0, direction_deg=0.0, fs=48000, n_mics=16,
                           n_samples=9600, array_center=[0, 0, 0])
        ws_high = WindSource(speed_ms=20.0, direction_deg=0.0, fs=48000, n_mics=16,
                            n_samples=9600, array_center=[0, 0, 0])
        wind_low = ws_low.generate(mic_pos)
        wind_high = ws_high.generate(mic_pos)
        c_low = abs(np.corrcoef(wind_low[0], wind_low[1])[0, 1])
        c_high = abs(np.corrcoef(wind_high[0], wind_high[1])[0, 1])
        self.assertGreater(c_high, c_low,
            f"Corr at 20 m/s ({c_high:.3f}) should exceed corr at 1 m/s ({c_low:.3f})")

    @staticmethod
    def _dual_ring_positions():
        angles = np.arange(8) * 2 * np.pi / 8
        return np.column_stack([
            np.concatenate([0.34 * np.cos(angles), 0.17 * np.cos(angles)]),
            np.concatenate([0.34 * np.sin(angles), 0.17 * np.sin(angles)]),
            np.concatenate([np.full(8, -0.1), np.full(8, 0.1)]),
        ])

    def test_wind_rms_scales_with_speed(self):
        np.random.seed(0)
        mic_pos = self._dual_ring_positions()
        rms_values = []
        for speed in [1.0, 2.0, 5.0]:
            ws = WindSource(speed_ms=speed, direction_deg=0.0, fs=48000, n_mics=16, n_samples=4800, array_center=[0, 0, 0])
            wind = ws.generate(mic_pos)
            rms_values.append(np.std(wind))
        ratio = rms_values[1] / rms_values[0]
        self.assertAlmostEqual(ratio, 2.0, delta=0.3,
                               msg=f"RMS ratio {ratio:.2f} should be ~2.0")
        ratio = rms_values[2] / rms_values[0]
        self.assertAlmostEqual(ratio, 5.0, delta=1.0,
                               msg=f"RMS ratio {ratio:.2f} should be ~5.0")


class TestTurbulence(unittest.TestCase):
    def test_turbulence_statistics(self):
        from src.drone_signal import DroneSource
        from src.config import DroneConfig

        cfg = DroneConfig(distance=10.0)
        src = DroneSource(cfg)
        tau = src._generate_turbulence(n_samples=48000, fs=48000, n_mics=16)
        mean_abs = np.mean(np.abs(tau))
        std_val = np.std(tau)

        # Mean abs delay should be ~12 μs (for tau_std=15e-6)
        self.assertAlmostEqual(mean_abs * 1e6, 12, delta=4)
        self.assertAlmostEqual(std_val * 1e6, 15, delta=5)

    def test_turbulence_time_correlation(self):
        from src.drone_signal import DroneSource
        from src.config import DroneConfig

        cfg = DroneConfig(distance=10.0)
        src = DroneSource(cfg)
        tau = src._generate_turbulence(n_samples=48000, fs=48000, n_mics=1)

        # Auto-correlation at lag 480 (10 ms) should be positive
        ac = np.correlate(tau[0] - tau[0].mean(), tau[0] - tau[0].mean(), mode="full")
        ac /= ac[len(ac) // 2]
        lag_10ms = ac[len(ac) // 2 + 480]
        self.assertGreater(lag_10ms, 0.5, f"Auto-corr at 10ms = {lag_10ms:.3f}, expected > 0.5")


class TestEnvironmentConfig(unittest.TestCase):
    def test_environment_disabled_by_default(self):
        cfg = EnvironmentConfig()
        self.assertFalse(cfg.enabled)

    def test_noise_config_defaults(self):
        nc = NoiseConfig()
        self.assertEqual(nc.wind_speed_ms, 0.0)
        self.assertEqual(nc.traffic_density, "none")

    def test_environment_disabled_returns_none(self):
        env = Environment(EnvironmentConfig(), fs=48000, n_mics=16, duration=1.0)
        self.assertIsNone(env.generate_noise(np.zeros((16, 3))))


if __name__ == "__main__":
    unittest.main()
