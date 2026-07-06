"""Microphone/sensor model: EIN-derived noise floor and per-mic imperfections.

Real arrays are limited less by ideal-array theory than by hardware
imperfections: per-mic gain/phase mismatch, PCB placement error, dead
channels, and quantization. This module models those effects so that
geometry sweeps report performance a fabricated array can actually reach.

The imperfection draw uses its own seeded RNG (``imperfections.seed``),
independent of the signal seed: one "build" of an array keeps its mismatch
across runs while the acoustic realization varies.
"""

import numpy as np
from scipy.signal import butter, sosfilt

from .constants import REF_SPL_DB, spl_to_pa


def effective_snr_db(config, absorption=None) -> float:
    """SNR at the mic from drone SPL, spreading loss, absorption, and EIN.

    ``signal.snr_db`` overrides everything when set (used by sweeps).
    Otherwise the budget is:

        SNR = drone_spl_db - 20*log10(distance) - absorption_loss - EIN

    where EIN (equivalent input noise, dB SPL) = REF_SPL_DB - mic.snr_dba,
    per the datasheet convention that mic SNR is quoted re 94 dB SPL.
    Absorption loss uses the ISO 9613-1 coefficient averaged over the
    drone's BPF harmonics.
    """
    if config.signal.snr_db is not None:
        return float(config.signal.snr_db)

    ein_db_spl = REF_SPL_DB - config.mic.snr_dba
    dist = config.drone.distance
    spl_at_mic = config.signal.drone_spl_db - 20 * np.log10(max(dist, 0.1))

    if absorption is not None:
        bpf = (config.drone.rpm * config.drone.num_blades) / 60.0
        harmonics = np.arange(1, config.drone.bpf_harmonics + 1)
        alphas = absorption.coefficient(harmonics * bpf)
        spl_at_mic -= float(np.mean(alphas)) * dist

    return float(spl_at_mic - ein_db_spl)


class SensorModel:
    """Applies mic-chain effects to clean propagated signals.

    Order: gain mismatch → phase mismatch → mic high-pass response →
    AOP soft clipping → self-noise injection → dead channels → quantization.

    ``position_offsets`` is consumed by the array geometry: propagation uses
    the *true* (perturbed) mic positions while SRP steering keeps using the
    nominal ones — exactly the mismatch that degrades a fabricated array.
    """

    def __init__(self, mic_config, n_mics, fs):
        self.mic = mic_config
        self.n_mics = n_mics
        self.fs = fs

        imp = mic_config.imperfections
        rng = np.random.default_rng(imp.seed)
        self.gains = 10.0 ** (rng.normal(0.0, imp.gain_std_db, n_mics) / 20.0)
        self.phases_rad = np.deg2rad(rng.normal(0.0, imp.phase_std_deg, n_mics))
        self.position_offsets = rng.normal(
            0.0, imp.position_std_mm * 1e-3, (n_mics, 3)
        )
        self.failed_mics = [m for m in imp.failed_mics if 0 <= m < n_mics]
        self.quantization_bits = imp.quantization_bits

        # Per-mic LF corner spread (drawn AFTER the legacy imperfections so
        # existing seeds keep their gain/phase/position draws unchanged).
        corner_std = getattr(imp, "hpf_corner_std_pct", 0.0) / 100.0
        if corner_std > 0:
            self.hpf_corners = np.clip(
                75.0 * (1.0 + rng.normal(0.0, corner_std, n_mics)),
                10.0, 500.0,
            )
        else:
            self.hpf_corners = np.full(n_mics, 75.0)
        self._hpf_sos = [
            butter(1, fc / (fs / 2), btype="high", output="sos")
            for fc in self.hpf_corners
        ]
        self._uniform_hpf = corner_std <= 0

        # ICS-52000 HF magnitude trace (dB re 1 kHz), log-f interpolated
        # and realized as a minimum-phase filter. Approximate anchors from
        # the DS-000121 typical response plot — VERIFY against the exact
        # datasheet revision. Other mic models keep a flat response.
        self._response_anchors = (
            ((1000.0, 0.0), (2000.0, 0.05), (5000.0, 0.2),
             (10000.0, 1.0), (15000.0, 2.2), (20000.0, 3.5))
            if mic_config.model.lower() == "ics-52000" else None
        )
        self._response_cache = {}

        # Calibrated-path conversions: digital full scale per Pa from the
        # datasheet sensitivity (−26 dBFS @ 1 Pa → 120 dB SPL ≈ 1.0 FS,
        # matching the AOP), and the absolute EIN floor in Pa.
        self.fs_per_pa = 10.0 ** (mic_config.sensitivity_dbFS / 20.0)
        self.ein_pa = spl_to_pa(REF_SPL_DB - mic_config.snr_dba)

    @property
    def is_ideal(self) -> bool:
        imp = self.mic.imperfections
        return (
            imp.gain_std_db == 0.0
            and imp.phase_std_deg == 0.0
            and not self.failed_mics
            and self.quantization_bits is None
        )

    def apply(self, mic_signals: np.ndarray, snr_db: float | None = None,
              absolute: bool = False) -> np.ndarray:
        """Mic-chain effects on propagated signals.

        Legacy path (``snr_db`` given, ``absolute=False``): normalized
        units, self-noise placed at ``snr_db`` re each mic's signal power —
        bit-compatible with the ``signal.snr_db`` override used by sweeps.

        Calibrated path (``absolute=True``): input is pressure in Pa; the
        noise floor is the absolute EIN, output is digital full scale via
        the datasheet sensitivity, and clipping/quantization act on FS.
        """
        out = mic_signals * self.gains[:, None]

        if np.any(self.phases_rad != 0.0):
            out = self._apply_phase_mismatch(out)

        if self._uniform_hpf:
            out = sosfilt(self._hpf_sos[0], out, axis=1)
        else:
            out = np.stack([
                sosfilt(self._hpf_sos[m], out[m]) for m in range(self.n_mics)
            ])

        if self._response_anchors is not None:
            out = self._apply_response_curve(out)

        if absolute:
            out = out + self.ein_pa * np.random.randn(*out.shape)
            out = out * self.fs_per_pa
            out = self._apply_aop_clipping(out)
        else:
            out = self._apply_aop_clipping(out)
            if snr_db is not None:
                out = out + self.self_noise(out, snr_db)

        for m in self.failed_mics:
            out[m] = 0.0

        if self.quantization_bits is not None:
            out = self._quantize(out, self.quantization_bits)

        return out

    def self_noise(self, mic_signals: np.ndarray, snr_db: float) -> np.ndarray:
        """Per-mic white self-noise at the given SNR re each mic's signal power.

        The simulation works in normalized (not Pa-referenced) units, so the
        noise floor is placed relative to measured signal power using the
        EIN-derived SNR budget from :func:`effective_snr_db`.
        """
        sig_power = np.mean(mic_signals ** 2, axis=1, keepdims=True)
        noise_power = sig_power / (10.0 ** (snr_db / 10.0))
        return np.sqrt(noise_power) * np.random.randn(*mic_signals.shape)

    def _response_filter(self, n: int) -> np.ndarray:
        """Minimum-phase frequency response for signal length n (cached)."""
        H = self._response_cache.get(n)
        if H is not None:
            return H
        freqs = np.fft.rfftfreq(n, 1.0 / self.fs)
        log_f = np.log10(np.maximum(freqs, 1.0))
        anchor_f = np.log10([a[0] for a in self._response_anchors])
        anchor_db = [a[1] for a in self._response_anchors]
        mag_db = np.interp(log_f, anchor_f, anchor_db)
        mag = 10.0 ** (mag_db / 20.0)

        # Minimum-phase via the real cepstrum of log|H|.
        log_mag = np.log(np.maximum(mag, 1e-9))
        cep = np.fft.irfft(log_mag, n=n)
        fold = np.zeros(n)
        fold[0] = 1.0
        fold[1:(n + 1) // 2] = 2.0
        if n % 2 == 0:
            fold[n // 2] = 1.0
        H = np.exp(np.fft.rfft(cep * fold, n=n))
        self._response_cache[n] = H
        return H

    def _apply_response_curve(self, mic_signals: np.ndarray) -> np.ndarray:
        n = mic_signals.shape[1]
        H = self._response_filter(n)
        S = np.fft.rfft(mic_signals, axis=1)
        return np.fft.irfft(S * H[None, :], n=n, axis=1)

    def _apply_phase_mismatch(self, mic_signals: np.ndarray) -> np.ndarray:
        n = mic_signals.shape[1]
        S = np.fft.rfft(mic_signals, axis=1)
        S *= np.exp(-1j * self.phases_rad)[:, None]
        return np.fft.irfft(S, n=n, axis=1)

    def _apply_aop_clipping(self, mic_signals: np.ndarray) -> np.ndarray:
        peak = np.max(np.abs(mic_signals))
        if peak > 0.5:
            return np.tanh(mic_signals) * 0.95
        return mic_signals

    @staticmethod
    def _quantize(mic_signals: np.ndarray, bits: int) -> np.ndarray:
        scale = 2.0 ** (bits - 1)
        clipped = np.clip(mic_signals, -1.0, 1.0 - 1.0 / scale)
        return np.round(clipped * scale) / scale
