"""Per-stage MCU requirement estimation and multi-target feasibility.

Extends the closed-form H753 budget in `mcu_budget.py` (kept untouched
for backward compatibility) into a requirement *statement* per pipeline
stage — SRP-PHAT, log-mel transform (cost model only; the classifier
lives in the C2 codebase), and log-mel uplink — that is then matched
against MCU profiles. Every verdict names its binding constraint with
numbers, and audio I/O (can the part actually clock the mic chains in?)
is checked with the same weight as compute and memory.

Conventions:
  - MACs are complex-MAC equivalents; `required_mhz` on the requirement
    object assumes 1 MAC/cycle (per-profile verdicts use the profile's
    own throughput).
  - RAM/flash are sums of named contributions; firmware code size and
    RTOS overhead are NOT included (they belong in each profile's
    "usable" figures).
"""

import math
from dataclasses import dataclass, field

import numpy as np

from ..config import Config, McuProfile
from .mcu_profiles import mics_per_bus, required_tdm_buses, resolve_profiles

PHASE_TABLE_BYTES = 8   # complex64 steering table on target
SAMPLE_BYTES = 4        # float32 working buffers / 32-bit DMA slots


def _fmt_bytes(n: float) -> str:
    if n >= 2**20:
        return f"{n / 2**20:.2f} MB"
    return f"{n / 2**10:.0f} KB"


@dataclass
class StageRequirement:
    """Resource footprint of one pipeline stage."""
    name: str
    ram_bytes: float
    flash_bytes: float
    macs_per_frame: float
    frame_period_s: float
    link_bps: float = 0.0

    @property
    def macs_per_second(self) -> float:
        return self.macs_per_frame / self.frame_period_s


@dataclass
class McuRequirements:
    """Aggregate requirements for one simulation configuration."""
    stages: list[StageRequirement]
    n_mics: int
    fs: int
    slot_bits: int
    mic_max_sck_hz: float
    headroom_pct: float

    @property
    def macs_per_second(self) -> float:
        return sum(s.macs_per_second for s in self.stages)

    @property
    def ram_bytes(self) -> float:
        return sum(s.ram_bytes for s in self.stages)

    @property
    def flash_bytes(self) -> float:
        return sum(s.flash_bytes for s in self.stages)

    @property
    def link_bps(self) -> float:
        return sum(s.link_bps for s in self.stages)

    @property
    def required_mhz(self) -> float:
        """Clock needed at 1 complex MAC/cycle, including headroom."""
        return self.macs_per_second * (1 + self.headroom_pct / 100) / 1e6

    def required_clock_hz(self, profile: McuProfile) -> float:
        return (self.macs_per_second / profile.macs_per_cycle
                * (1 + self.headroom_pct / 100))


@dataclass
class ProfileVerdict:
    """One MCU profile checked against one requirement set."""
    profile: McuProfile
    required_clock_hz: float
    ram_bytes: float
    flash_bytes: float
    mics_per_bus: int
    required_buses: int | None
    fits_compute: bool
    fits_ram: bool
    fits_flash: bool
    fits_audio_io: bool

    @property
    def fits(self) -> bool:
        return (self.fits_compute and self.fits_ram
                and self.fits_flash and self.fits_audio_io)

    def summary(self) -> str:
        """Human-readable verdict that names every constraint."""
        audio = self.profile.audio
        buses = ("no valid TDM frame" if self.required_buses is None
                 else f"{self.required_buses} buses "
                      f"{'≤' if self.fits_audio_io else '>'} {audio.n_tdm_buses} "
                      f"({self.mics_per_bus} mics/bus)")
        parts = [
            ("compute", self.fits_compute,
             f"{self.required_clock_hz / 1e6:.0f} MHz "
             f"{'≤' if self.fits_compute else '>'} "
             f"{self.profile.clock_hz / 1e6:.0f} MHz"),
            ("SRAM", self.fits_ram,
             f"{_fmt_bytes(self.ram_bytes)} "
             f"{'≤' if self.fits_ram else '>'} "
             f"{_fmt_bytes(self.profile.sram_bytes)}"),
            ("flash", self.fits_flash,
             f"{_fmt_bytes(self.flash_bytes)} "
             f"{'≤' if self.fits_flash else '>'} "
             f"{_fmt_bytes(self.profile.flash_bytes)}"),
            ("audio", self.fits_audio_io, buses),
        ]
        failing = [f"{n} {d}" for n, ok, d in parts if not ok]
        passing = [f"{n} OK ({d})" for n, ok, d in parts if ok]
        if failing:
            return "fails: " + "; ".join(failing + passing)
        return "OK: " + "; ".join(d for _, _, d in parts)


@dataclass
class McuReport:
    requirements: McuRequirements
    verdicts: list[ProfileVerdict]
    recommended: str | None = field(default=None)


def _search_directions(config: Config) -> int:
    search = config.srpphat.search
    res = search.resolution_deg
    n_az = len(np.arange(search.azimuth_range[0],
                         search.azimuth_range[1] + res / 2, res))
    n_el = len(np.arange(search.elevation_range[0],
                         search.elevation_range[1] + res / 2, res))
    return n_az * n_el


def _srp_stage(config: Config, n_mics: int) -> StageRequirement:
    fft_size = config.srpphat.fft_size
    hop = config.srpphat.hop_length
    fs = config.signal.fs
    n_dirs = _search_directions(config)

    freqs = np.fft.rfftfreq(fft_size, 1.0 / fs)
    n_freqs = int(np.sum((freqs >= config.srpphat.min_freq)
                         & (freqs <= config.srpphat.max_freq)))
    n_bins = fft_size // 2 + 1

    ram = (
        n_freqs * n_mics * n_dirs * PHASE_TABLE_BYTES  # steering phase table
        + n_mics * fft_size * SAMPLE_BYTES             # per-mic ring buffer
        + 2 * n_mics * hop * SAMPLE_BYTES              # hop-sized DMA double buffer
        + n_mics * n_bins * 2 * SAMPLE_BYTES           # per-mic spectra (complex)
        + n_dirs * SAMPLE_BYTES                        # SRP power map
    )
    macs = (
        n_freqs * n_mics * n_dirs                      # steering einsum
        + n_mics * fft_size * math.log2(fft_size)      # per-mic FFT
        + 2 * n_freqs * n_mics                         # PHAT normalization
    )
    flash = fft_size * SAMPLE_BYTES                    # analysis window
    return StageRequirement("srp_phat", ram, flash, macs, hop / fs)


def _logmel_stage(config: Config, srp: StageRequirement) -> StageRequirement:
    lm = config.mcu.logmel
    fft_size = lm.fft_size or config.srpphat.fft_size
    hop = lm.hop_length or config.srpphat.hop_length
    fs = config.signal.fs
    n_bins = fft_size // 2 + 1
    ch = lm.channels

    # The SRP stage already computes per-mic spectra; a log-mel branch with
    # the same FFT geometry reuses them instead of re-transforming.
    reuse_fft = (fft_size == config.srpphat.fft_size
                 and hop == config.srpphat.hop_length)

    macs = (
        (0 if reuse_fft else ch * fft_size * math.log2(fft_size))
        + ch * n_bins            # power spectrum |X|²
        + ch * 2 * n_bins        # sparse triangular filterbank (≤2 mels/bin)
        + ch * lm.n_mels * 10    # log() cycle-equivalents
    )
    ram = (
        ch * lm.n_mels * SAMPLE_BYTES
        + (0 if reuse_fft else ch * fft_size * SAMPLE_BYTES)
    )
    flash = (
        2 * n_bins * SAMPLE_BYTES     # filterbank weights (two per bin)
        + 2 * lm.n_mels * 4           # mel band edge indices
    )
    return StageRequirement("log_mel", ram, flash, macs, hop / fs)


def _transmit_stage(config: Config) -> StageRequirement:
    lm = config.mcu.logmel
    hop = lm.hop_length or config.srpphat.hop_length
    fs = config.signal.fs
    frame_rate = fs / hop

    payload_bps = lm.n_mels * frame_rate * lm.bits_per_bin * lm.channels
    link_bps = payload_bps * (1 + config.mcu.link_overhead_pct / 100)
    packet_bytes = lm.n_mels * lm.channels * lm.bits_per_bin / 8
    # Serialization cost is a rounding error next to SRP; count the copy.
    return StageRequirement("transmit", 2 * packet_bytes, 0.0,
                            packet_bytes, hop / fs, link_bps=link_bps)


def compute_requirements(config: Config, n_mics: int) -> McuRequirements:
    """Per-stage resource requirements for one configuration."""
    srp = _srp_stage(config, n_mics)
    stages = [srp]
    if config.mcu.logmel.enabled:
        stages.append(_logmel_stage(config, srp))
        stages.append(_transmit_stage(config))
    return McuRequirements(
        stages=stages,
        n_mics=n_mics,
        fs=config.signal.fs,
        slot_bits=config.mcu.slot_bits,
        mic_max_sck_hz=config.mcu.mic_max_sck_hz,
        headroom_pct=config.mcu.headroom_pct,
    )


def evaluate_profile(req: McuRequirements, profile: McuProfile) -> ProfileVerdict:
    per_bus = mics_per_bus(profile.audio, req.fs, req.slot_bits,
                           req.mic_max_sck_hz)
    buses = required_tdm_buses(req.n_mics, per_bus)
    required_hz = req.required_clock_hz(profile)
    return ProfileVerdict(
        profile=profile,
        required_clock_hz=required_hz,
        ram_bytes=req.ram_bytes,
        flash_bytes=req.flash_bytes,
        mics_per_bus=per_bus,
        required_buses=buses,
        fits_compute=required_hz <= profile.clock_hz,
        fits_ram=req.ram_bytes <= profile.sram_bytes,
        fits_flash=req.flash_bytes <= profile.flash_bytes,
        fits_audio_io=buses is not None and buses <= profile.audio.n_tdm_buses,
    )


def evaluate_from_config(config: Config, n_mics: int) -> McuReport:
    """Requirements plus verdicts for every configured target profile.

    Recommendation is the first profile in `mcu.targets` order that
    passes all four constraints (compute, SRAM, flash, audio I/O).
    """
    req = compute_requirements(config, n_mics)
    profiles = resolve_profiles(config.mcu)
    verdicts = [evaluate_profile(req, p) for p in profiles]
    recommended = next((v.profile.name for v in verdicts if v.fits), None)
    return McuReport(requirements=req, verdicts=verdicts,
                     recommended=recommended)
