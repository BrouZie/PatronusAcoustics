import unittest
import numpy as np

from src.geometry import DualRingArray
from src.config import ArrayConfig, SearchConfig, DetectionConfig, SRPPhatConfig
from src.srpphat import SRPPhatProcessor


class TestSRPPhatVectorization(unittest.TestCase):
    def setUp(self):
        array_cfg = ArrayConfig(
            ring1_radius=0.34, ring2_radius=0.17,
            n_mics_ring1=8, n_mics_ring2=8, ring_spacing=0.20,
        )
        self.array = DualRingArray(array_cfg)
        search = SearchConfig(azimuth_range=[-10, 10], elevation_range=[-10, 10], resolution_deg=5.0)
        det = DetectionConfig(enabled=False)
        self.srp = SRPPhatProcessor(
            array=self.array, fs=48000, fft_size=512, hop_length=256,
            search_config=search, max_freq=4000, mode="phat",
            frequency_weight=0.0, detection_config=det,
        )

    def test_phase_tensor_shape(self):
        n_freq = self.srp.n_freqs_used
        n_dir = self.srp.n_directions
        self.assertEqual(self.srp.phase.shape, (n_freq, self.array.n_mics, n_dir))

    def test_process_frame_returns_expected_keys(self):
        np.random.seed(42)
        frame = np.random.randn(self.array.n_mics, 512)
        result = self.srp.process_frame(frame)
        self.assertIn("srp_map", result)
        self.assertIn("estimated_doa", result)
        self.assertIn("peak_value", result)
        self.assertIn("detected", result)

    def test_tone_at_boresight_gives_peak_at_center(self):
        np.random.seed(0)
        center = np.array([0, 0, 1])
        dists = np.linalg.norm(self.array.positions - center, axis=1)
        delays = dists / 343.0
        t = np.arange(512) / 48000
        tone = np.sin(2 * np.pi * 800 * t)
        frame = np.zeros((self.array.n_mics, 512))
        for m in range(self.array.n_mics):
            delay_samp = delays[m] * 48000
            int_delay = int(delay_samp)
            frac = delay_samp - int_delay
            if int_delay < 512 - 1:
                frame[m] = (1 - frac) * np.roll(tone, int_delay) + frac * np.roll(tone, int_delay + 1)
        frame += 0.01 * np.random.randn(*frame.shape)

        result = self.srp.process_frame(frame)
        est = result["estimated_doa"]
        self.assertFalse(np.any(np.isnan(est)),
                         f"DOA should not be NaN, got {est}")

    def test_peak_value_positive(self):
        np.random.seed(0)
        frame = 0.1 * np.random.randn(self.array.n_mics, 512)
        result = self.srp.process_frame(frame)
        self.assertGreater(result["peak_value"], 0)


if __name__ == "__main__":
    unittest.main()
