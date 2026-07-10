"""Per-stage MCU requirement estimation and multi-target feasibility.

Each pipeline stage — SRP-PHAT, log-mel transform (cost model only; the
classifier lives in the C2 codebase), and log-mel uplink — emits a
profile-independent *work statement*: op counts (complex MACs, real
FMAs, divisions, square roots, logs, FFTs by size), bytes streamed per
frame, and named RAM contributions. Verdicts convert work to cycles per
profile using its core op-cost model, its memory regions (the steering
einsum streams a phase table far larger than any cache, so sustained
throughput is min(compute-bound, bandwidth-bound)), and any measured
calibration data. Every verdict names its binding constraint with
numbers, and audio I/O (can the part actually clock the mic chains in?)
is checked with the same weight as compute and memory.

Conventions:
  - `required_mhz` on the requirement object is a cross-config reference
    metric: cycles on a reference Cortex-M7 core model with unbounded
    memory bandwidth (per-profile verdicts use the profile's own core,
    regions, and calibration).
  - RAM/flash are sums of named contributions; firmware code size is NOT
    included (it belongs in each profile's "usable" figures). Scheduler
    and DMA-interrupt overhead ARE modeled, via
    `mcu.sched_overhead_cycles` and `mcu.isr_cycles`; `headroom_pct`
    remains a pure safety margin for unmodeled costs.
  - Calibration precedence, field-wise:
    config `mcu.calibrations[name]` > profile `calibration` > analytic.
"""

import math
from dataclasses import dataclass, field

import numpy as np

from ..config import (Config, McuCalibration, McuCoreModel,
                      McuMemoryRegion, McuProfile)
from .mcu_profiles import mics_per_bus, required_tdm_buses, resolve_profiles

PHASE_TABLE_BYTES = 8   # complex64 steering table on target
SAMPLE_BYTES = 4        # float32 working buffers / 32-bit DMA slots

# Reference core for the profile-independent `required_mhz` metric
# (Cortex-M7-class defaults; documented in docs/mcu.md).
REFERENCE_CORE = McuCoreModel()


def _fmt_bytes(n: float) -> str:
    if n >= 2**20:
        return f"{n / 2**20:.2f} MB"
    return f"{n / 2**10:.0f} KB"


@dataclass
class RamContribution:
    """One named RAM allocation of a pipeline stage."""
    name: str
    bytes: float
    const: bool = False     # read-only table → may live in flash XIP
    streamed: bool = False  # read start-to-end every frame (zero reuse)


@dataclass
class StageWork:
    """Per-frame op counts of one pipeline stage (profile-independent)."""
    cmacs: float = 0.0                # complex MACs (steering einsum)
    streamed_bytes: float = 0.0       # table bytes read once per frame
    rffts: list[tuple[int, int]] = field(default_factory=list)
                                      # (fft_size, transforms per frame)
    rmacs: float = 0.0                # real FMAs
    divs: float = 0.0
    sqrts: float = 0.0
    logs: float = 0.0


@dataclass
class StageRequirement:
    """Resource footprint of one pipeline stage."""
    name: str
    ram: list[RamContribution]
    flash_bytes: float
    work: StageWork
    frame_period_s: float
    link_bps: float = 0.0

    @property
    def ram_bytes(self) -> float:
        return sum(c.bytes for c in self.ram)


def _rfft_cycles(n: int, core: McuCoreModel,
                 cal: McuCalibration | None) -> float:
    """Real-FFT cycle cost: measured if available, else k·N·log2(N).

    Uncalibrated sizes scale from the nearest measured size (in log2
    distance) by the N·log2(N) ratio.
    """
    if cal is not None and cal.rfft_cycles:
        if n in cal.rfft_cycles:
            return float(cal.rfft_cycles[n])
        nearest = min(cal.rfft_cycles,
                      key=lambda m: abs(math.log2(m) - math.log2(n)))
        scale = (n * math.log2(n)) / (nearest * math.log2(nearest))
        return cal.rfft_cycles[nearest] * scale
    return core.rfft_cycles_per_nlogn * n * math.log2(n)


def _stage_cycles(work: StageWork, core: McuCoreModel,
                  cal: McuCalibration | None,
                  steering_cmacs_per_cycle: float) -> float:
    """Cycles per frame for one stage on one core."""
    def op(cal_value, core_value):
        return core_value if cal_value is None else cal_value

    fft = sum(count * _rfft_cycles(n, core, cal) for n, count in work.rffts)
    steer = work.cmacs / steering_cmacs_per_cycle if work.cmacs else 0.0
    ops = (work.rmacs / core.rmacs_per_cycle
           + work.divs * op(cal.div_cycles if cal else None, core.div_cycles)
           + work.sqrts * op(cal.sqrt_cycles if cal else None,
                             core.sqrt_cycles)
           + work.logs * op(cal.log_cycles if cal else None, core.log_cycles))
    return fft + steer + ops


def reference_stage_cycles(stage: StageRequirement) -> float:
    """Cycles/frame on REFERENCE_CORE with unbounded memory bandwidth."""
    return _stage_cycles(stage.work, REFERENCE_CORE, None,
                         REFERENCE_CORE.cmacs_per_cycle)


@dataclass
class McuRequirements:
    """Aggregate requirements for one simulation configuration."""
    stages: list[StageRequirement]
    n_mics: int
    fs: int
    slot_bits: int
    mic_max_sck_hz: float
    headroom_pct: float
    sched_overhead_cycles: float = 2000.0
    isr_cycles: float = 400.0
    calibrations: dict[str, McuCalibration] = field(default_factory=dict)

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
    def reference_cycles_per_second(self) -> float:
        """Workload on REFERENCE_CORE with unbounded memory bandwidth."""
        return sum(
            _stage_cycles(s.work, REFERENCE_CORE, None,
                          REFERENCE_CORE.cmacs_per_cycle) / s.frame_period_s
            for s in self.stages)

    @property
    def required_mhz(self) -> float:
        """Reference-core clock including headroom (cross-config metric)."""
        return (self.reference_cycles_per_second
                * (1 + self.headroom_pct / 100) / 1e6)


@dataclass
class _RegionState:
    region: McuMemoryRegion
    bandwidth: float   # bytes per core cycle, calibration applied
    free: float


def _region_states(profile: McuProfile,
                   cal: McuCalibration | None) -> list[_RegionState]:
    """Profile regions with calibrated bandwidths, fastest first.

    Profiles without regions synthesize one from `sram_bytes` with
    bandwidth that never binds (legacy RAM semantics).
    """
    regions = profile.memory_regions or [
        McuMemoryRegion(name="sram", size_bytes=profile.sram_bytes,
                        read_bytes_per_cycle=8.0)
    ]
    states = []
    for r in regions:
        bw = r.read_bytes_per_cycle
        if cal is not None and r.name in cal.region_bytes_per_cycle:
            bw = cal.region_bytes_per_cycle[r.name]
        states.append(_RegionState(r, bw, float(r.size_bytes)))
    states.sort(key=lambda s: s.bandwidth, reverse=True)
    return states


@dataclass
class _Placement:
    fits: bool
    table_parts: list[tuple[_RegionState, float]]  # streamed-table spans
    flash_spill: float                             # const bytes in XIP flash


def _place(stages: list[StageRequirement],
           states: list[_RegionState]) -> _Placement:
    """Greedily place RAM contributions into regions, fastest first.

    Working buffers (non-const) go to writable regions only; constant
    streamed tables may span regions and land in read-only flash-XIP
    space (counted against flash, not RAM).
    """
    dynamic = sum(c.bytes for s in stages for c in s.ram if not c.const)
    remaining = dynamic
    for st in states:
        if not st.region.writable:
            continue
        take = min(remaining, st.free)
        st.free -= take
        remaining -= take
    if remaining > 1e-9:
        return _Placement(False, [], 0.0)

    table_parts: list[tuple[_RegionState, float]] = []
    flash_spill = 0.0
    for s in stages:
        for c in s.ram:
            if not c.const:
                continue
            left = c.bytes
            for st in states:
                if left <= 0:
                    break
                take = min(left, st.free)
                if take <= 0:
                    continue
                st.free -= take
                left -= take
                if c.streamed:
                    table_parts.append((st, take))
                if not st.region.writable:
                    flash_spill += take
            if left > 1e-9:
                return _Placement(False, table_parts, flash_spill)
    return _Placement(True, table_parts, flash_spill)


@dataclass
class ProfileVerdict:
    """One MCU profile checked against one requirement set."""
    profile: McuProfile
    required_clock_hz: float
    ram_bytes: float           # placed in RAM (flash-XIP spill excluded)
    ram_capacity: float        # writable region capacity
    flash_bytes: float         # const tables + flash-XIP spill
    mics_per_bus: int
    required_buses: int | None
    fits_compute: bool
    fits_ram: bool
    fits_flash: bool
    fits_audio_io: bool
    bottleneck: str = "compute"
    utilization_pct: float = 0.0
    phase_table_regions: list[str] = field(default_factory=list)
    cycles_by_stage: dict[str, float] = field(default_factory=dict)

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
        compute = (f"{self.required_clock_hz / 1e6:.0f} MHz "
                   f"{'≤' if self.fits_compute else '>'} "
                   f"{self.profile.clock_hz / 1e6:.0f} MHz")
        if self.bottleneck != "compute":
            compute += f", {self.bottleneck}-bound"
        parts = [
            ("compute", self.fits_compute, compute),
            ("SRAM", self.fits_ram,
             f"{_fmt_bytes(self.ram_bytes)} "
             f"{'≤' if self.fits_ram else '>'} "
             f"{_fmt_bytes(self.ram_capacity)}"),
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

    def short_summary(self) -> str:
        """One-cell verdict for summary tables."""
        name = self.profile.name
        if self.fits:
            return f"{name} OK ({self.utilization_pct:.0f}% CPU)"
        if not self.fits_ram:
            return (f"{name} fails: SRAM {_fmt_bytes(self.ram_bytes)} > "
                    f"{_fmt_bytes(self.ram_capacity)}")
        if not self.fits_compute:
            return (f"{name} fails: needs "
                    f"{self.required_clock_hz / 1e6:.0f} MHz > "
                    f"{self.profile.clock_hz / 1e6:.0f} MHz "
                    f"({self.bottleneck}-bound)")
        if not self.fits_flash:
            return (f"{name} fails: flash {_fmt_bytes(self.flash_bytes)} > "
                    f"{_fmt_bytes(self.profile.flash_bytes)}")
        return f"{name} fails: audio I/O"


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

    ram = [
        RamContribution("phase_table",
                        n_freqs * n_mics * n_dirs * PHASE_TABLE_BYTES,
                        const=True, streamed=True),
        RamContribution("ring_buffer", n_mics * fft_size * SAMPLE_BYTES),
        RamContribution("dma_double_buffer",
                        2 * n_mics * hop * SAMPLE_BYTES),
        RamContribution("spectra", n_mics * n_bins * 2 * SAMPLE_BYTES),
        RamContribution("power_map", n_dirs * SAMPLE_BYTES),
    ]
    # PHAT weighting per (freq, mic): |X| = 2 FMAs + 1 sqrt, then
    # X/|X| = 1 div + 2 FMAs.
    work = StageWork(
        cmacs=n_freqs * n_mics * n_dirs,               # steering einsum
        streamed_bytes=n_freqs * n_mics * n_dirs * PHASE_TABLE_BYTES,
        rffts=[(fft_size, n_mics)],                    # per-mic FFT
        rmacs=4 * n_freqs * n_mics,
        divs=n_freqs * n_mics,
        sqrts=n_freqs * n_mics,
    )
    flash = fft_size * SAMPLE_BYTES                    # analysis window
    return StageRequirement("srp_phat", ram, flash, work, hop / fs)


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

    work = StageWork(
        rffts=[] if reuse_fft else [(fft_size, ch)],
        rmacs=(ch * 2 * n_bins        # power spectrum |X|²
               + ch * 2 * n_bins),    # sparse triangular filterbank
        logs=ch * lm.n_mels,
    )
    ram = [RamContribution("mel_frame", ch * lm.n_mels * SAMPLE_BYTES)]
    if not reuse_fft:
        ram.append(RamContribution("logmel_fft",
                                   ch * fft_size * SAMPLE_BYTES))
    flash = (
        2 * n_bins * SAMPLE_BYTES     # filterbank weights (two per bin)
        + 2 * lm.n_mels * 4           # mel band edge indices
    )
    return StageRequirement("log_mel", ram, flash, work, hop / fs)


def _transmit_stage(config: Config) -> StageRequirement:
    lm = config.mcu.logmel
    hop = lm.hop_length or config.srpphat.hop_length
    fs = config.signal.fs
    frame_rate = fs / hop

    payload_bps = lm.n_mels * frame_rate * lm.bits_per_bin * lm.channels
    link_bps = payload_bps * (1 + config.mcu.link_overhead_pct / 100)
    packet_bytes = lm.n_mels * lm.channels * lm.bits_per_bin / 8
    # Serialization cost is a rounding error next to SRP; count the copy.
    ram = [RamContribution("tx_buffer", 2 * packet_bytes)]
    work = StageWork(rmacs=packet_bytes / 4)
    return StageRequirement("transmit", ram, 0.0, work, hop / fs,
                            link_bps=link_bps)


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
        sched_overhead_cycles=config.mcu.sched_overhead_cycles,
        isr_cycles=config.mcu.isr_cycles,
        calibrations=dict(config.mcu.calibrations),
    )


def _merged_calibration(profile: McuProfile,
                        config_cal: McuCalibration | None,
                        ) -> McuCalibration | None:
    """Field-wise merge: config-level values win over profile-level."""
    base = profile.calibration
    if base is None:
        return config_cal
    if config_cal is None:
        return base
    merged = base.model_dump()
    override = config_cal.model_dump(exclude_none=True)
    for key, value in override.items():
        if isinstance(value, dict):
            merged[key] = {**merged.get(key, {}), **value}
        else:
            merged[key] = value
    return McuCalibration.model_validate(merged)


def evaluate_profile(req: McuRequirements,
                     profile: McuProfile) -> ProfileVerdict:
    cal = _merged_calibration(profile, req.calibrations.get(profile.name))
    per_bus = mics_per_bus(profile.audio, req.fs, req.slot_bits,
                           req.mic_max_sck_hz)
    buses = required_tdm_buses(req.n_mics, per_bus)

    states = _region_states(profile, cal)
    placement = _place(req.stages, states)
    ram_capacity = sum(s.region.size_bytes for s in states
                       if s.region.writable)

    # Effective steering throughput: min(compute-bound, bandwidth-bound
    # over the regions the streamed phase table landed in).
    core = profile.core
    table_bytes = sum(take for _, take in placement.table_parts)
    if table_bytes > 0:
        eff_bw = table_bytes / sum(take / st.bandwidth
                                   for st, take in placement.table_parts)
    else:
        eff_bw = states[0].bandwidth
    if cal is not None and cal.steering_cmacs_per_cycle is not None:
        eff_steer = cal.steering_cmacs_per_cycle
        bottleneck = "calibrated"
    else:
        bw_bound = eff_bw / PHASE_TABLE_BYTES
        if bw_bound < core.cmacs_per_cycle:
            slow = sorted({st.region.name
                           for st, _ in placement.table_parts})
            eff_steer = bw_bound
            bottleneck = f"memory ({'+'.join(slow)})"
        else:
            eff_steer = core.cmacs_per_cycle
            bottleneck = "compute"

    cycles_by_stage = {
        s.name: _stage_cycles(s.work, core, cal, eff_steer)
        for s in req.stages
    }
    srp_period = req.stages[0].frame_period_s
    if cal is not None and cal.overhead_cycles_per_frame is not None:
        overhead = cal.overhead_cycles_per_frame
    else:
        overhead = (req.sched_overhead_cycles
                    + 2 * (buses or 0) * req.isr_cycles)
    cycles_per_second = sum(
        cycles_by_stage[s.name] / s.frame_period_s for s in req.stages
    ) + overhead / srp_period
    required_hz = cycles_per_second * (1 + req.headroom_pct / 100)

    ram_placed = req.ram_bytes - placement.flash_spill
    flash_total = req.flash_bytes + placement.flash_spill
    return ProfileVerdict(
        profile=profile,
        required_clock_hz=required_hz,
        ram_bytes=ram_placed,
        ram_capacity=ram_capacity,
        flash_bytes=flash_total,
        mics_per_bus=per_bus,
        required_buses=buses,
        fits_compute=required_hz <= profile.clock_hz,
        fits_ram=placement.fits,
        fits_flash=flash_total <= profile.flash_bytes,
        fits_audio_io=buses is not None and buses <= profile.audio.n_tdm_buses,
        bottleneck=bottleneck,
        utilization_pct=required_hz / profile.clock_hz * 100,
        phase_table_regions=sorted({st.region.name
                                    for st, _ in placement.table_parts}),
        cycles_by_stage=cycles_by_stage,
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
