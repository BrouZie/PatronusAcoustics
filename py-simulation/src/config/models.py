from dataclasses import MISSING
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator, field_validator
from pydantic.config import ConfigDict
from pydantic.fields import FieldInfo

from .merge import deep_merge, parse_dotted_key

API = (
    "MotionConfig", "ArrayConfig", "AnyArrayConfig", "DualRingArrayConfig",
    "SingleRingArrayConfig", "ArbitraryArrayConfig",
    "MicConfig", "MicImperfectionConfig",
    "SignalConfig", "DroneConfig", "SearchConfig", "DetectionConfig",
    "SRPPhatConfig", "GroundConfig", "AtmosphericConfig", "RefractionConfig",
    "TurbulenceConfig", "NoiseConfig", "EnvironmentConfig",
    "OutputConfig", "Config", "deep_merge", "parse_dotted_key",
    "McuAudioIO", "McuProfile", "LogMelConfig", "McuConfig",
    "McuCoreModel", "McuMemoryRegion", "McuCalibration",
)


def _meta(**kw: Any) -> dict[str, Any]:
    return {"json_schema_extra": kw}


class MotionConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = Field(
        default=False,
        description="Enable source motion",
    )
    velocity: tuple[float, float, float] = Field(
        default=(0.0, 0.0, 0.0),
        description="Source velocity vector (vx, vy, vz) in m/s",
        **_meta(unit="m/s"),
    )

    @model_validator(mode="after")
    def _check_velocity(self):
        if self.enabled and all(abs(v) < 1e-12 for v in self.velocity):
            raise ValueError("velocity must be non-zero when motion is enabled")
        return self


class DualRingArrayConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["dual_ring"] = "dual_ring"
    ring1_radius: float = Field(
        default=0.34, gt=0, le=5,
        description="Radius of the outer ring",
        **_meta(unit="m"),
    )
    ring2_radius: float = Field(
        default=0.17, gt=0, le=5,
        description="Radius of the inner ring",
        **_meta(unit="m"),
    )
    n_mics_ring1: int = Field(
        default=8, ge=2, le=64,
        description="Number of microphones on the outer ring",
    )
    n_mics_ring2: int = Field(
        default=8, ge=2, le=64,
        description="Number of microphones on the inner ring",
    )
    ring_spacing: float = Field(
        default=0.20, gt=0, le=2,
        description="Vertical spacing between rings",
        **_meta(unit="m"),
    )


class SingleRingArrayConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["single_ring"] = "single_ring"
    radius: float = Field(
        default=0.25, gt=0, le=5,
        description="Ring radius",
        **_meta(unit="m"),
    )
    n_mics: int = Field(
        default=16, ge=2, le=64,
        description="Number of microphones on the ring",
    )
    z_offset: float = Field(
        default=0.0, ge=-2, le=2,
        description="Ring offset along boresight",
        **_meta(unit="m"),
    )


class ArbitraryArrayConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["xyz"] = "xyz"
    positions: list[tuple[float, float, float]] | None = Field(
        default=None,
        description="Mic positions (x, y, z) in the array frame, +z = boresight",
        **_meta(unit="m"),
    )
    csv_path: str | None = Field(
        default=None,
        description="CSV file of x,y,z rows (prefer inline positions: file "
                    "contents are not part of the config hash)",
    )

    @model_validator(mode="after")
    def _exactly_one_source(self):
        if (self.positions is None) == (self.csv_path is None):
            raise ValueError("provide exactly one of 'positions' or 'csv_path'")
        if self.positions is not None and len(self.positions) < 2:
            raise ValueError("need at least 2 microphone positions")
        return self


# Backward-compatible alias: existing code constructs ArrayConfig(...) with
# dual-ring kwargs.
ArrayConfig = DualRingArrayConfig

AnyArrayConfig = Annotated[
    DualRingArrayConfig | SingleRingArrayConfig | ArbitraryArrayConfig,
    Field(discriminator="type"),
]


class MicImperfectionConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    gain_std_db: float = Field(
        default=0.0, ge=0, le=12,
        description="Per-mic gain mismatch std (ICS-52000 tolerance ~±1 dB)",
        **_meta(unit="dB"),
    )
    phase_std_deg: float = Field(
        default=0.0, ge=0, le=90,
        description="Per-mic phase mismatch std",
        **_meta(unit="deg"),
    )
    position_std_mm: float = Field(
        default=0.0, ge=0, le=50,
        description="Per-mic placement error std (PCB/assembly tolerance)",
        **_meta(unit="mm"),
    )
    quantization_bits: int | None = Field(
        default=None, ge=8, le=32,
        description="ADC quantization depth (None = ideal, ICS-52000 = 24)",
    )
    hpf_corner_std_pct: float = Field(
        default=0.0, ge=0, le=50,
        description="Per-mic spread of the LF roll-off corner as % of "
                    "nominal — yields frequency-dependent gain AND phase "
                    "mismatch at low frequencies (part-to-part tolerance)",
        **_meta(unit="%"),
    )
    failed_mics: list[int] = Field(
        default_factory=list,
        description="Indices of dead microphone channels",
    )
    seed: int = Field(
        default=0, ge=0,
        description="Seed for the imperfection draw (one 'build' of the array)",
    )


class MicConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str = Field(
        default="ics-52000",
        description="Microphone model identifier",
    )
    snr_dba: float = Field(
        default=65.0, ge=20, le=120,
        description="Microphone self-noise (SNR re 94 dB SPL)",
        **_meta(unit="dBA"),
    )
    sensitivity_dbFS: float = Field(
        default=-26.0, ge=-100, le=0,
        description="Microphone sensitivity",
        **_meta(unit="dBFS"),
    )
    aop_db_spl: float = Field(
        default=120.0, ge=60, le=200,
        description="Acoustic overload point",
        **_meta(unit="dB SPL"),
    )
    imperfections: MicImperfectionConfig = Field(
        default_factory=MicImperfectionConfig,
        description="Per-mic hardware imperfections (mismatch, placement, ADC)",
    )


class SignalConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    fs: int = Field(
        default=48000, ge=8000, le=192000,
        description="Sample rate",
        **_meta(unit="Hz"),
    )
    duration: float = Field(
        default=5.0, gt=0, le=3600,
        description="Signal duration",
        **_meta(unit="s"),
    )
    snr_db: float | None = Field(
        default=None, ge=-10, le=60,
        description="Override SNR (None = auto from drone SPL + distance)",
        **_meta(unit="dB"),
    )
    drone_spl_db: float = Field(
        default=70.0, ge=0, le=200,
        description="Drone source SPL at 1 m",
        **_meta(unit="dB SPL @ 1m"),
    )
    seed: int | None = Field(
        default=None, ge=0,
        description="Random seed for reproducible runs (None = non-deterministic)",
    )


class DroneConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    rpm: int = Field(
        default=6000, gt=0, le=100000,
        description="Rotor rotational speed",
        **_meta(unit="RPM"),
    )
    num_blades: int = Field(
        default=2, ge=1, le=8,
        description="Blades per rotor",
    )
    num_rotors: int = Field(
        default=4, ge=1, le=16,
        description="Number of rotors",
    )
    distance: float = Field(
        default=10.0, gt=0,
        description="Source distance from array",
        **_meta(unit="m"),
    )
    initial_bearing: dict = Field(
        default={"azimuth_deg": 15.0, "elevation_deg": 10.0},
        description="Initial source direction (azimuth, elevation in degrees)",
        **_meta(unit="deg"),
    )
    motion: MotionConfig = Field(
        default_factory=MotionConfig,
        description="Source motion parameters",
    )
    trajectory: dict = Field(
        default_factory=dict,
        description="Trajectory definition (empty = stationary point source)",
    )
    bpf_harmonics: int = Field(
        default=6, ge=1, le=20,
        description="Number of blade-pass frequency harmonics",
    )
    rpm_spread_pct: float = Field(
        default=2.0, ge=0, le=20,
        description="Per-rotor RPM offset std as % of nominal RPM; distinct "
                    "rotor BPFs beat against each other (0 = identical rotors)",
        **_meta(unit="%"),
    )
    rpm_jitter_pct: float = Field(
        default=0.5, ge=0, le=20,
        description="Slow RPM wander std as % of nominal (throttle/gust "
                    "corrections), Ornstein-Uhlenbeck per rotor",
        **_meta(unit="%"),
    )
    rpm_jitter_corr_s: float = Field(
        default=0.5, gt=0, le=30,
        description="Correlation time of the RPM wander",
        **_meta(unit="s"),
    )
    motor_whine_db: float | None = Field(
        default=None, ge=-60, le=0,
        description="Motor/ESC whine level relative to the BPF fundamental "
                    "(None = no whine tone)",
        **_meta(unit="dB"),
    )
    whine_multiple: float = Field(
        default=14.0, gt=0, le=100,
        description="Whine frequency as a multiple of shaft rate (motor "
                    "pole-pass order, e.g. 14 for a 14-pole outrunner)",
    )

    @field_validator("initial_bearing")
    @classmethod
    def _check_bearing_keys(cls, v):
        if "azimuth_deg" not in v or "elevation_deg" not in v:
            raise ValueError(
                "initial_bearing must contain keys 'azimuth_deg' and 'elevation_deg'"
            )
        return v


class SearchConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    coverage: Literal["window", "front_hemisphere", "full_sphere"] = Field(
        default="window",
        description="Search coverage preset. 'window' uses the explicit "
                    "ranges below; the presets override them. Full sphere at "
                    "2° is ~16k directions — consider 4° resolution. Note "
                    "PSR/beamwidth are only comparable at equal coverage.",
    )
    azimuth_range: list[float] = Field(
        default=[-60.0, 60.0],
        description="Azimuth search range [min, max] in degrees",
        min_length=2, max_length=2,
        **_meta(unit="deg"),
    )
    elevation_range: list[float] = Field(
        default=[-60.0, 60.0],
        description="Elevation search range [min, max] in degrees "
                    "(polar angle from boresight: 90° = ring plane, "
                    "180° = behind the array)",
        min_length=2, max_length=2,
        **_meta(unit="deg"),
    )
    resolution_deg: float = Field(
        default=2.0, ge=0.1, le=90,
        description="Search grid resolution",
        **_meta(unit="deg"),
    )

    @field_validator("azimuth_range", "elevation_range")
    @classmethod
    def _range_ordered(cls, v):
        if len(v) != 2:
            raise ValueError("must have exactly 2 elements")
        if v[0] >= v[1]:
            raise ValueError(f"[0] ({v[0]}) must be less than [1] ({v[1]})")
        return v

    @model_validator(mode="after")
    def _apply_coverage(self):
        if self.coverage == "front_hemisphere":
            self.azimuth_range = [-180.0, 180.0]
            self.elevation_range = [0.0, 90.0]
        elif self.coverage == "full_sphere":
            self.azimuth_range = [-180.0, 180.0]
            self.elevation_range = [0.0, 180.0]
        return self


class DetectionConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = Field(
        default=True,
        description="Enable SRP-PHAT detection logic",
    )
    method: str = Field(
        default="peak_to_mean",
        description="Detection method: peak_to_mean, peak_to_sidelobe, or threshold",
    )
    psr_threshold_db: float = Field(
        default=3.0, ge=0, le=60,
        description="Peak-to-sidelobe ratio threshold for detection",
        **_meta(unit="dB"),
    )
    peak_to_mean_threshold_db: float = Field(
        default=5.0, ge=0, le=60,
        description="Peak-to-mean ratio threshold for detection",
        **_meta(unit="dB"),
    )

    @field_validator("method")
    @classmethod
    def _check_method(cls, v):
        allowed = {"peak_to_mean", "peak_to_sidelobe", "threshold"}
        if v not in allowed:
            raise ValueError(f"must be one of {', '.join(sorted(allowed))}, got '{v}'")
        return v


class SRPPhatConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    fft_size: int = Field(
        default=2048, gt=0,
        description="FFT size (must be a power of 2)",
    )
    hop_length: int = Field(
        default=512, gt=0,
        description="Hop length between consecutive frames (samples)",
    )
    search: SearchConfig = Field(
        default_factory=SearchConfig,
        description="Spatial search grid configuration",
    )
    max_freq: float = Field(
        default=4000.0, gt=0,
        description="Maximum frequency for SRP-PHAT processing",
        **_meta(unit="Hz"),
    )
    min_freq: float = Field(
        default=0.0, ge=0,
        description="Minimum frequency for SRP-PHAT processing (0 = no high-pass)",
        **_meta(unit="Hz"),
    )
    mode: str = Field(
        default="phat",
        description="SRP-PHAT mode: 'phat' or 'standard'",
    )
    frequency_weight: float = Field(
        default=0.0, ge=0, le=5,
        description="Frequency-domain weighting exponent (0 = uniform, 1 = amplitude-weighted)",
    )
    detection: DetectionConfig = Field(
        default_factory=DetectionConfig,
        description="Detection threshold configuration",
    )

    @field_validator("fft_size")
    @classmethod
    def _power_of_two(cls, v):
        if v <= 0 or (v & (v - 1)) != 0:
            raise ValueError(f"fft_size must be a power of 2, got {v}")
        return v

    @field_validator("mode")
    @classmethod
    def _check_mode(cls, v):
        allowed = {"phat", "standard"}
        if v not in allowed:
            raise ValueError(f"mode must be 'phat' or 'standard', got '{v}'")
        return v

    @model_validator(mode="after")
    def _check_ranges(self):
        if not (0 < self.hop_length <= self.fft_size):
            raise ValueError(
                f"hop_length ({self.hop_length}) must be in (0, fft_size ({self.fft_size})]"
            )
        if not (0 <= self.min_freq < self.max_freq):
            raise ValueError(
                f"min_freq ({self.min_freq}) must be in [0, max_freq ({self.max_freq}))"
            )
        return self


class GroundConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    height_m: float = Field(
        default=5.0, ge=0,
        description="Array mounting height above ground",
        **_meta(unit="m"),
    )
    tilt_deg: float = Field(
        default=0.0,
        description="Ground plane tilt offset from horizontal",
        **_meta(unit="deg"),
    )
    reflection_coefficient: float = Field(
        default=0.5, ge=0, le=1,
        description="Ground reflection coefficient (constant model only)",
    )
    model: str = Field(
        default="constant",
        description="Ground impedance model: 'constant' or 'delany_bazley'",
    )
    flow_resistivity: float = Field(
        default=200000.0, gt=0,
        description="Flow resistivity for Delany-Bazley model",
        **_meta(unit="Pa·s/m²"),
    )

    @field_validator("model")
    @classmethod
    def _check_model(cls, v):
        allowed = {"constant", "delany_bazley"}
        if v not in allowed:
            raise ValueError(f"model must be 'constant' or 'delany_bazley', got '{v}'")
        return v


class AtmosphericConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    temperature_C: float = Field(
        default=20.0, ge=-50, le=60,
        description="Air temperature",
        **_meta(unit="°C"),
    )
    humidity_pct: float = Field(
        default=50.0, ge=0, le=100,
        description="Relative humidity",
        **_meta(unit="%"),
    )
    pressure_kPa: float = Field(
        default=101.325, ge=80, le=110,
        description="Atmospheric pressure",
        **_meta(unit="kPa"),
    )


class RefractionConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = Field(
        default=False,
        description="Enable sound refraction effects",
    )
    wind_shear_ms_per_m: float = Field(
        default=0.0,
        description="Vertical wind shear gradient",
        **_meta(unit="(m/s)/m"),
    )
    temperature_lapse_rate: float = Field(
        default=-0.0065,
        description="Temperature lapse rate with altitude",
        **_meta(unit="K/m"),
    )
    roughness_length: float = Field(
        default=0.03, gt=0,
        description="Terrain aerodynamic roughness length",
        **_meta(unit="m"),
    )


class TurbulenceConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    amplitude_scintillation: bool = Field(
        default=False,
        description="Enable amplitude scintillation (turbulence-induced fading)",
    )
    scintillation_strength: float = Field(
        default=0.1, ge=0, le=1,
        description="Scintillation strength (0–1, higher = stronger fading)",
    )
    phase_jitter_std_us: float = Field(
        default=15.0, ge=0, le=1000,
        description="Turbulence-induced arrival-time jitter std",
        **_meta(unit="µs"),
    )
    phase_jitter_corr_ms: float = Field(
        default=50.0, gt=0, le=10000,
        description="Correlation time of the arrival-time jitter (AR(1))",
        **_meta(unit="ms"),
    )
    scintillation_corr_ms: float = Field(
        default=50.0, gt=0, le=10000,
        description="Correlation time of amplitude scintillation",
        **_meta(unit="ms"),
    )


class NoiseConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    wind_speed_ms: float = Field(
        default=0.0, ge=0, le=100,
        description="Wind speed at array height",
        **_meta(unit="m/s"),
    )
    wind_direction_deg: float = Field(
        default=0.0, ge=0, lt=360,
        description="Wind direction (0 = from North, clockwise)",
        **_meta(unit="deg"),
    )
    traffic_density: str = Field(
        default="none",
        description="Road traffic density: none, light, moderate, heavy",
    )
    traffic_direction_deg: float = Field(
        default=90.0,
        description="Traffic flow direction relative to North",
        **_meta(unit="deg"),
    )
    bird_activity: float = Field(
        default=0.0, ge=0, le=1,
        description="Bird vocalization activity level (0 = none, 1 = maximum)",
    )
    ambient_db: float = Field(
        default=0.0, ge=0, le=120,
        description="Broadband ambient noise floor",
        **_meta(unit="dB SPL"),
    )
    corcos_alpha_xi: float = Field(
        default=0.15, gt=0, le=5,
        description="Corcos streamwise coherence decay for wind noise",
    )
    corcos_alpha_eta: float = Field(
        default=0.75, gt=0, le=5,
        description="Corcos cross-stream coherence decay for wind noise",
    )
    traffic_distance_m: float = Field(
        default=50.0, gt=0,
        description="Distance of the traffic noise source from the array",
        **_meta(unit="m"),
    )
    bird_distance_m: float = Field(
        default=10.0, gt=0,
        description="Distance of the bird noise source from the array",
        **_meta(unit="m"),
    )
    windscreen_il_db: float = Field(
        default=0.0, ge=0, le=60,
        description="Windscreen insertion loss applied to wind noise "
                    "(calibrated mode; 0 = bare mic, foam ball ~15-25)",
        **_meta(unit="dB"),
    )
    bird_spl_db: float = Field(
        default=90.0, ge=40, le=130,
        description="Bird chirp source level at 1 m (calibrated mode)",
        **_meta(unit="dB SPL"),
    )

    @field_validator("traffic_density")
    @classmethod
    def _check_traffic(cls, v):
        allowed = {"none", "light", "moderate", "heavy"}
        if v not in allowed:
            raise ValueError(
                f"traffic_density must be one of {', '.join(allowed)}, got '{v}'"
            )
        return v


class EnvironmentConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = Field(
        default=False,
        description="Enable all environmental effects",
    )
    ground: GroundConfig = Field(
        default_factory=GroundConfig,
        description="Ground reflection configuration",
    )
    noise: NoiseConfig = Field(
        default_factory=NoiseConfig,
        description="Ambient noise configuration",
    )
    atmospheric: AtmosphericConfig = Field(
        default_factory=AtmosphericConfig,
        description="Atmospheric conditions (temperature, humidity, pressure)",
    )
    refraction: RefractionConfig = Field(
        default_factory=RefractionConfig,
        description="Sound refraction due to wind and temperature gradients",
    )
    turbulence: TurbulenceConfig = Field(
        default_factory=TurbulenceConfig,
        description="Atmospheric turbulence effects",
    )


class OutputConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    animation_fps: int = Field(
        default=15, ge=1, le=120,
        description="Animation frame rate",
    )
    save_animation: bool = Field(
        default=True,
        description="Save 2D beamforming animation",
    )
    save_3d_animation: bool = Field(
        default=True,
        description="Save 3D beamsphere animation",
    )
    save_figures: bool = Field(
        default=True,
        description="Save summary figures (PNG)",
    )
    save_data: bool = Field(
        default=True,
        description="Save simulation data (NPZ)",
    )


class McuAudioIO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    n_tdm_buses: int = Field(
        ge=0, le=16,
        description="TDM-capable audio RX interfaces (SAI/I2S peripherals) "
                    "usable for microphone capture",
    )
    max_slots_per_bus: int = Field(
        ge=1, le=32,
        description="TDM slots supported per bus by the peripheral",
    )
    max_frame_bits: int = Field(
        ge=32, le=1024,
        description="Maximum TDM frame length in bit clocks (STM32 SAI: 256, "
                    "so only 8 × 32-bit slots per frame natively)",
    )
    max_bit_clock_hz: float = Field(
        gt=0,
        description="Maximum TDM bit clock (SCK) the peripheral can run",
        **_meta(unit="Hz"),
    )


class McuCoreModel(BaseModel):
    """Op-cost table for one CPU core (defaults: Cortex-M7 float32)."""

    model_config = ConfigDict(extra="forbid")

    cmacs_per_cycle: float = Field(
        default=0.25, gt=0, le=8,
        description="Compute-bound complex MACs per cycle (a complex MAC "
                    "is 4 real FMAs; the M7 FPU issues 1 VFMA.F32/cycle)",
    )
    rmacs_per_cycle: float = Field(
        default=1.0, gt=0, le=8,
        description="Real FMAs per cycle",
    )
    rfft_cycles_per_nlogn: float = Field(
        default=1.7, gt=0,
        description="k in cycles ≈ k·N·log2(N) for an arm_rfft_fast_f32 "
                    "class real FFT of size N",
    )
    div_cycles: float = Field(
        default=14.0, gt=0,
        description="Cycles per float division (VDIV.F32 on M7, "
                    "non-pipelined)",
    )
    sqrt_cycles: float = Field(
        default=14.0, gt=0,
        description="Cycles per float square root (VSQRT.F32 on M7)",
    )
    log_cycles: float = Field(
        default=25.0, gt=0,
        description="Cycles per logf() call (polynomial approximation)",
    )


class McuMemoryRegion(BaseModel):
    """One addressable memory region with its sustained read bandwidth."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        description="Region identifier (e.g. 'dtcm', 'ocram2', 'psram', "
                    "'flash_xip')",
    )
    size_bytes: int = Field(
        gt=0,
        description="Usable capacity of the region",
        **_meta(unit="B"),
    )
    read_bytes_per_cycle: float = Field(
        gt=0,
        description="Sustained streaming read bandwidth per core cycle "
                    "(zero-reuse access pattern, cache misses included)",
    )
    writable: bool = Field(
        default=True,
        description="False for execute/read-only regions (flash XIP): "
                    "only constant tables may be placed there",
    )


class McuCalibration(BaseModel):
    """Measured on-device benchmark results that override analytic costs.

    Any field left unset falls back to the next source in precedence
    order: config-level calibration > profile-level calibration >
    analytic core/memory model.
    """

    model_config = ConfigDict(extra="forbid")

    measured_on: str | None = Field(
        default=None,
        description="Provenance: board, firmware commit, date",
    )
    rfft_cycles: dict[int, int] = Field(
        default_factory=dict,
        description="Measured real-FFT cycles by FFT size; uncalibrated "
                    "sizes scale from the nearest measured size by the "
                    "N·log2(N) ratio",
    )
    steering_cmacs_per_cycle: float | None = Field(
        default=None, gt=0,
        description="Measured end-to-end steering-einsum throughput with "
                    "the phase table in its intended region (overrides "
                    "the min(compute, bandwidth) estimate)",
    )
    region_bytes_per_cycle: dict[str, float] = Field(
        default_factory=dict,
        description="Measured sustained stream bandwidth per memory "
                    "region name",
    )
    div_cycles: float | None = Field(default=None, gt=0)
    sqrt_cycles: float | None = Field(default=None, gt=0)
    log_cycles: float | None = Field(default=None, gt=0)
    overhead_cycles_per_frame: float | None = Field(
        default=None, ge=0,
        description="Measured per-frame RTOS/DMA/ISR overhead; replaces "
                    "the sched_overhead_cycles + isr_cycles model",
    )


class McuProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Profile identifier (e.g. 'stm32h753')")
    clock_hz: float = Field(
        gt=0,
        description="Core clock frequency",
        **_meta(unit="Hz"),
    )
    macs_per_cycle: float | None = Field(
        default=None, gt=0, le=8,
        description="DEPRECATED: sustained complex MACs per cycle. Mapped "
                    "onto core.cmacs_per_cycle when core is not explicitly "
                    "set; prefer configuring `core`",
    )
    core: McuCoreModel = Field(
        default_factory=McuCoreModel,
        description="Core op-cost model (defaults are Cortex-M7 float32)",
    )
    sram_bytes: int = Field(
        gt=0,
        description="Usable SRAM after stacks/OS buffers",
        **_meta(unit="B"),
    )
    flash_bytes: int = Field(
        gt=0,
        description="Usable non-volatile storage for tables (internal flash "
                    "or external, whichever holds constant data)",
        **_meta(unit="B"),
    )
    memory_regions: list[McuMemoryRegion] | None = Field(
        default=None,
        description="Memory regions for placement/bandwidth modeling. "
                    "None synthesizes a single region from sram_bytes "
                    "with bandwidth that never binds (legacy semantics)",
    )
    calibration: McuCalibration | None = Field(
        default=None,
        description="Measured benchmark results baked into the profile",
    )
    notes: str | None = Field(
        default=None,
        description="Fidelity caveats surfaced in reports",
    )
    audio: McuAudioIO = Field(
        description="Audio input (TDM/SAI) capability — a profile that "
                    "cannot physically ingest the array's mics must fail",
    )

    @model_validator(mode="after")
    def _map_deprecated_macs(self):
        if self.macs_per_cycle is not None and "core" not in self.model_fields_set:
            self.core = McuCoreModel(cmacs_per_cycle=self.macs_per_cycle)
        return self


class LogMelConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = Field(
        default=True,
        description="Include the log-mel + transmission stages in the "
                    "MCU requirement estimate (cost model only; the "
                    "classifier itself lives in the C2 codebase)",
    )
    n_mels: int = Field(
        default=64, ge=8, le=256,
        description="Mel bands per frame",
    )
    fft_size: int | None = Field(
        default=None, gt=0,
        description="Log-mel FFT size (None = reuse the SRP-PHAT FFT)",
    )
    hop_length: int | None = Field(
        default=None, gt=0,
        description="Log-mel hop length (None = reuse the SRP-PHAT hop)",
    )
    bits_per_bin: int = Field(
        default=8, ge=4, le=32,
        description="Quantization of each transmitted mel bin",
    )
    channels: int = Field(
        default=1, ge=1, le=64,
        description="Audio channels transformed/transmitted (1 = mixdown)",
    )

    @field_validator("fft_size")
    @classmethod
    def _power_of_two(cls, v):
        if v is not None and (v & (v - 1)) != 0:
            raise ValueError(f"fft_size must be a power of 2, got {v}")
        return v


class McuConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = Field(
        default=False,
        description="Emit per-target MCU feasibility in reports/sweeps",
    )
    headroom_pct: float = Field(
        default=30.0, ge=0, le=90,
        description="Compute headroom reserved for control/comms/ISRs when "
                    "sizing the required clock",
        **_meta(unit="%"),
    )
    targets: list[str] = Field(
        default=["stm32h753"],
        description="MCU profiles to evaluate, in preference order "
                    "(built-in library names or custom_profiles names)",
    )
    custom_profiles: list[McuProfile] = Field(
        default_factory=list,
        description="User-defined MCU profiles (override built-ins by name)",
    )
    calibrations: dict[str, McuCalibration] = Field(
        default_factory=dict,
        description="Measured benchmark overrides by profile name (applies "
                    "field-wise on top of built-in or custom profiles)",
    )
    sched_overhead_cycles: float = Field(
        default=2000.0, ge=0,
        description="Modeled RTOS tick + control-loop cycles per SRP frame "
                    "(known overhead; headroom_pct covers unknowns)",
    )
    isr_cycles: float = Field(
        default=400.0, ge=0,
        description="Cycles per DMA half/complete interrupt; charged "
                    "2 × required buses per frame",
    )
    logmel: LogMelConfig = Field(
        default_factory=LogMelConfig,
        description="Log-mel transform + uplink cost-model parameters",
    )
    link_overhead_pct: float = Field(
        default=20.0, ge=0, le=200,
        description="Protocol/framing overhead on the log-mel uplink",
        **_meta(unit="%"),
    )
    mic_max_sck_hz: float = Field(
        default=24.576e6, gt=0,
        description="Microphone TDM SCK ceiling (ICS-52000 datasheet "
                    "validates 24.576 MHz = 16 mics × 32 SCK × 48 kHz); "
                    "binds the bus bit-clock budget together with the "
                    "peripheral limit",
        **_meta(unit="Hz"),
    )
    slot_bits: int = Field(
        default=32, ge=16, le=32,
        description="TDM slot width in bit clocks (ICS-52000 frames are "
                    "n × 32 SCK, n a power of two ≥ the mics on the bus)",
    )


class Config(BaseModel):
    model_config = ConfigDict(extra="ignore")

    array: AnyArrayConfig = Field(
        default_factory=DualRingArrayConfig,
        description="Array geometry parameters",
    )

    @field_validator("array", mode="before")
    @classmethod
    def _default_array_type(cls, v):
        # Old YAML has no 'type' key; treat it as the original dual-ring.
        if isinstance(v, dict) and "type" not in v:
            return {**v, "type": "dual_ring"}
        return v
    signal: SignalConfig = Field(
        default_factory=SignalConfig,
        description="Signal generation parameters",
    )
    mic: MicConfig = Field(
        default_factory=MicConfig,
        description="Microphone characteristics",
    )
    drone: DroneConfig = Field(
        default_factory=DroneConfig,
        description="Drone source parameters",
    )
    srpphat: SRPPhatConfig = Field(
        default_factory=SRPPhatConfig,
        description="SRP-PHAT processing parameters",
    )
    environment: EnvironmentConfig = Field(
        default_factory=EnvironmentConfig,
        description="Environmental effects",
    )
    output: OutputConfig = Field(
        default_factory=OutputConfig,
        description="Output and visualization settings",
    )
    mcu: McuConfig = Field(
        default_factory=McuConfig,
        description="MCU requirement estimation (per-stage compute/memory/"
                    "I/O budgets matched against target profiles)",
    )

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Config":
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls._from_dict(data)

    @classmethod
    def from_yamls(cls, *paths: str | Path) -> "Config":
        merged: dict[str, Any] = {}
        for path in paths:
            with open(path) as f:
                data = yaml.safe_load(f)
            if data:
                deep_merge(merged, data)
        return cls._from_dict(merged)

    @classmethod
    def _from_dict(cls, data: dict | None) -> "Config":
        if data is None:
            return cls()
        return cls.model_validate(_strip_none(data))

    @classmethod
    def from_dict(cls, data: dict | None) -> "Config":
        return cls._from_dict(data)

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")

    @classmethod
    def schema(cls) -> str:
        lines = ["# Patronus Simulation Configuration Schema", ""]
        _schema_lines(cls, lines, indent=0)
        return "\n".join(lines)

    def merge(self, overrides: dict) -> "Config":
        base = self.model_dump()
        deep_merge(base, overrides)
        return Config._from_dict(base)


def _union_models(annotation) -> list[type]:
    """BaseModel members of a (possibly Annotated) union annotation."""
    from typing import get_args
    args = get_args(annotation)
    return [a for a in args if isinstance(a, type) and issubclass(a, BaseModel)]


def _schema_lines(model_cls: type, lines: list[str], indent: int) -> None:
    prefix = "  " * indent
    for name, field_info in model_cls.model_fields.items():
        annotation = field_info.annotation
        union_members = _union_models(annotation)
        if annotation and isinstance(annotation, type) and issubclass(annotation, BaseModel):
            lines.append(f"{prefix}# {name} ...")
            lines.append(f"{prefix}{name}:")
            _schema_lines(annotation, lines, indent + 1)
        elif len(union_members) > 1:
            variants = ", ".join(
                str(m.model_fields["type"].default) for m in union_members
                if "type" in m.model_fields
            )
            lines.append(f"{prefix}# {name}: one of type: {variants} (showing default)")
            lines.append(f"{prefix}{name}:")
            _schema_lines(union_members[0], lines, indent + 1)
        else:
            type_hint = getattr(annotation, "__name__", str(annotation))
            default = field_info.get_default(call_default_factory=True)
            lines.append(f"{prefix}# {name}: {type_hint}  (default: {default})")
            lines.append(f"{prefix}{name}: {default}")


def _strip_none(data: Any) -> Any:
    if isinstance(data, dict):
        return {k: _strip_none(v) for k, v in data.items() if v is not None}
    if isinstance(data, list):
        return [_strip_none(v) for v in data]
    return data
