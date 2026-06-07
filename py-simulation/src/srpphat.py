import numpy as np
from scipy.signal import get_window

from .geometry import DualRingArray
from .metrics import peak_to_sidelobe_ratio

try:
    from . import _srp
    _HAS_CPP_SRP = True
except ImportError:
    _HAS_CPP_SRP = False


class SRPPhatProcessor:
    def __init__(self, array: DualRingArray, fs: int, fft_size: int,
                 hop_length: int, search_config, max_freq: float = 4000.0,
                 min_freq: float = 0.0, mode: str = "phat",
                 frequency_weight: float = 0.0,
                 detection_config=None):
        self.array = array
        self.fs = fs
        self.fft_size = fft_size
        self.hop_length = hop_length
        self.max_freq = max_freq
        self.min_freq = min_freq
        self.mode = mode
        self.frequency_weight = frequency_weight
        self.detection = detection_config

        az_min, az_max = search_config.azimuth_range
        el_min, el_max = search_config.elevation_range
        res = np.radians(search_config.resolution_deg)

        self.az_range = np.radians(np.arange(az_min, az_max + np.degrees(res) / 2, np.degrees(res)))
        self.el_range = np.radians(np.arange(el_min, el_max + np.degrees(res) / 2, np.degrees(res)))
        self.az_grid, self.el_grid = np.meshgrid(self.az_range, self.el_range, indexing="ij")
        self.n_az = len(self.az_range)
        self.n_el = len(self.el_range)
        self.n_directions = self.n_az * self.n_el

        directions = DualRingArray.direction_vectors(self.az_grid, self.el_grid)
        self.steering_delays = array.get_steering_delays(directions)
        # Shape: (n_mics, n_directions)

        self.freqs = np.fft.rfftfreq(self.fft_size, 1.0 / self.fs)
        self.freq_mask = (self.freqs >= self.min_freq) & (self.freqs <= self.max_freq)
        self.freqs_used = self.freqs[self.freq_mask]
        self.n_freqs_used = len(self.freqs_used)
        self.window = get_window("hann", self.fft_size)

        # Precompute frequency weights
        if self.mode == "phat":
            self._label = "SRP-PHAT"
        else:
            self._label = "SRP (standard)"

        if self.frequency_weight > 0:
            norm_freqs = self.freqs_used / (self.freqs_used[-1] + 1e-10)
            self.freq_weight = norm_freqs ** self.frequency_weight
            self._label += f"  f-weight α={frequency_weight:.1f}"
        else:
            self.freq_weight = np.ones(self.n_freqs_used)

        # Precompute phase tensor: phase[f, m, d] = exp(-j * ω_f * delay[m, d])
        # This replaces the per-frequency phase computation in the inner loop.
        omegas = 2 * np.pi * self.freqs_used
        self.phase = np.exp(
            -1j * omegas[:, None, None] * self.steering_delays[None, :, :]
        )
        # Shape: (n_freqs, n_mics, n_directions)

    @property
    def label(self):
        return self._label

    def process_frame(self, frame):
        n_mics = frame.shape[0]
        X = np.fft.rfft(frame * self.window[None, :], axis=1)
        X = X[:, self.freq_mask]

        if self.mode == "phat":
            X_used = X / (np.abs(X) + 1e-10)
        else:
            X_used = X

        if _HAS_CPP_SRP:
            srp = np.empty(self.n_directions)
            _srp.compute_srp_beam(X_used, self.phase, self.freq_weight, srp)
        else:
            beam = np.einsum("mf,fmd->fd", X_used, self.phase, optimize=True)
            srp = np.einsum("fd,f->d", np.abs(beam) ** 2, self.freq_weight, optimize=True)

        srp_map = srp.reshape(self.n_az, self.n_el)
        peak_idx = np.argmax(srp)
        peak_az = self.az_grid.ravel()[peak_idx]
        peak_el = self.el_grid.ravel()[peak_idx]

        detected = True
        if self.detection is not None and self.detection.enabled:
            if self.detection.method == "psr":
                psr = peak_to_sidelobe_ratio(srp_map)
                detected = psr >= self.detection.psr_threshold_db
            elif self.detection.method == "peak_to_mean":
                p2m = 10 * np.log10(np.max(srp) / (np.mean(srp) + 1e-10))
                detected = p2m >= self.detection.peak_to_mean_threshold_db

        doa = np.array([peak_az, peak_el]) if detected else np.array([np.nan, np.nan])

        return {
            "srp_map": srp_map,
            "estimated_doa": doa,
            "peak_value": srp[peak_idx],
            "detected": detected,
        }
