from dataclasses import MISSING
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, model_validator, field_validator
from pydantic.config import ConfigDict
from pydantic.fields import FieldInfo

from .merge import deep_merge, parse_dotted_key

API = (
    "MotionConfig", "ArrayConfig", "MicConfig", "SignalConfig",
    "DroneConfig", "SearchConfig", "DetectionConfig", "SRPPhatConfig",
    "GroundConfig", "AtmosphericConfig", "RefractionConfig",
    "TurbulenceConfig", "NoiseConfig", "EnvironmentConfig",
    "OutputConfig", "Config", "deep_merge", "parse_dotted_key",
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


class ArrayConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

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

    azimuth_range: list[float] = Field(
        default=[-60.0, 60.0],
        description="Azimuth search range [min, max] in degrees",
        min_length=2, max_length=2,
        **_meta(unit="deg"),
    )
    elevation_range: list[float] = Field(
        default=[-60.0, 60.0],
        description="Elevation search range [min, max] in degrees",
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


class Config(BaseModel):
    model_config = ConfigDict(extra="ignore")

    array: ArrayConfig = Field(
        default_factory=ArrayConfig,
        description="Array geometry parameters",
    )
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


def _schema_lines(model_cls: type, lines: list[str], indent: int) -> None:
    prefix = "  " * indent
    for name, field_info in model_cls.model_fields.items():
        if field_info.annotation and isinstance(field_info.annotation, type) and issubclass(field_info.annotation, BaseModel):
            lines.append(f"{prefix}# {name} ...")
            lines.append(f"{prefix}{name}:")
            _schema_lines(field_info.annotation, lines, indent + 1)
        else:
            type_hint = getattr(field_info.annotation, "__name__", str(field_info.annotation))
            default = field_info.default if field_info.default is not MISSING else field_info.default_factory() if field_info.default_factory is not MISSING else "REQUIRED"
            lines.append(f"{prefix}# {name}: {type_hint}  (default: {default})")
            lines.append(f"{prefix}{name}: {default}")


def _strip_none(data: Any) -> Any:
    if isinstance(data, dict):
        return {k: _strip_none(v) for k, v in data.items() if v is not None}
    if isinstance(data, list):
        return [_strip_none(v) for v in data]
    return data
