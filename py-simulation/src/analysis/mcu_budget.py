"""Closed-form SRP-PHAT compute/memory budget for the on-station MCU.

The station (NUCLEO-H753ZI) must run SRP-PHAT in real time. This mirrors
the cost of the `srpphat.py` einsum — n_freqs × n_mics × n_directions
complex MACs per frame plus per-mic FFTs — against stated H753 assumptions,
so geometry candidates that cannot run on-station get flagged in the
compare report, at decision time.

Stated assumptions (adjust here when the firmware measures real numbers):
  480 MHz core, ~1 complex MAC per cycle with CMSIS-DSP, ~820 KB usable
  SRAM (AXI+SRAM1-3, excluding stack/buffers), float32 tables on target.
"""

from dataclasses import dataclass

import numpy as np

H753_CLOCK_HZ = 480e6
H753_CMAC_PER_CYCLE = 1.0
H753_USABLE_SRAM_MB = 0.82
MCU_DTYPE_BYTES = 8  # complex64 phase table on target


@dataclass
class McuBudget:
    n_freqs_used: int
    n_directions: int
    phase_tensor_mb: float
    macs_per_frame: float
    est_frame_ms: float
    frame_period_ms: float
    fits_memory: bool
    fits_realtime: bool

    @property
    def fits_h753(self) -> bool:
        return self.fits_memory and self.fits_realtime

    def summary(self) -> str:
        flag = "OK" if self.fits_h753 else (
            "MEMORY" if not self.fits_memory else "TOO SLOW"
        )
        return (f"{self.phase_tensor_mb:.2f} MB / "
                f"{self.est_frame_ms:.1f} ms per {self.frame_period_ms:.1f} ms "
                f"frame [{flag}]")


def estimate(n_mics: int, fft_size: int, hop_length: int, fs: int,
             n_directions: int, max_freq: float, min_freq: float = 0.0,
             dtype_bytes: int = MCU_DTYPE_BYTES) -> McuBudget:
    freqs = np.fft.rfftfreq(fft_size, 1.0 / fs)
    n_freqs = int(np.sum((freqs >= min_freq) & (freqs <= max_freq)))

    phase_tensor_mb = n_freqs * n_mics * n_directions * dtype_bytes / 2 ** 20

    srp_macs = n_freqs * n_mics * n_directions
    fft_macs = n_mics * fft_size * np.log2(fft_size)
    macs = float(srp_macs + fft_macs)

    est_frame_ms = macs / (H753_CMAC_PER_CYCLE * H753_CLOCK_HZ) * 1e3
    frame_period_ms = hop_length / fs * 1e3

    return McuBudget(
        n_freqs_used=n_freqs,
        n_directions=n_directions,
        phase_tensor_mb=phase_tensor_mb,
        macs_per_frame=macs,
        est_frame_ms=est_frame_ms,
        frame_period_ms=frame_period_ms,
        fits_memory=phase_tensor_mb <= H753_USABLE_SRAM_MB,
        fits_realtime=est_frame_ms <= frame_period_ms,
    )


def estimate_from_config(config, n_mics: int) -> McuBudget:
    """Budget for a full simulation config's SRP settings."""
    search = config.srpphat.search
    res = search.resolution_deg
    n_az = len(np.arange(search.azimuth_range[0],
                         search.azimuth_range[1] + res / 2, res))
    n_el = len(np.arange(search.elevation_range[0],
                         search.elevation_range[1] + res / 2, res))
    return estimate(
        n_mics=n_mics,
        fft_size=config.srpphat.fft_size,
        hop_length=config.srpphat.hop_length,
        fs=config.signal.fs,
        n_directions=n_az * n_el,
        max_freq=config.srpphat.max_freq,
        min_freq=config.srpphat.min_freq,
    )
