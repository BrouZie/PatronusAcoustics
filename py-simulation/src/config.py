from dataclasses import MISSING, dataclass, field, fields, is_dataclass
from datetime import datetime
from pathlib import Path

import yaml


# ── Helpers for recursive dict↔dataclass conversion ──────────────────────

def _dataclass_from_dict(cls, data):
    """Build any Config dataclass from a potentially partial nested dict."""
    if data is None:
        return cls()

    valid_names = {f.name for f in fields(cls)}
    filtered = {k: v for k, v in data.items() if k in valid_names and v is not None}

    kwargs = {}
    for f in fields(cls):
        if f.name not in filtered:
            continue
        val = filtered[f.name]
        ftype = f.type

        if is_dataclass(ftype):
            kwargs[f.name] = _dataclass_from_dict(ftype, val)
        elif ftype is tuple and isinstance(val, list):
            kwargs[f.name] = tuple(val)
        else:
            kwargs[f.name] = val

    return cls(**kwargs)


def _dataclass_to_dict(instance):
    """Serialize any Config dataclass to a nested dict."""
    result = {}
    for f in fields(instance):
        val = getattr(instance, f.name)
        if is_dataclass(val):
            result[f.name] = _dataclass_to_dict(val)
        elif isinstance(val, tuple):
            result[f.name] = list(val)
        else:
            result[f.name] = val
    return result


# ── Validation helpers ──────────────────────────────────────────────────

def _check(cond, msg, errors):
    if not cond:
        errors.append(msg)


def _validate_config(obj):
    """Run __post_init__ validation safely — subclasses define their own."""
    if hasattr(obj, '_validate') and callable(obj._validate):
        errors = []
        obj._validate(errors)
        if errors:
            cls_name = type(obj).__name__
            raise ValueError(f"{cls_name}: " + "; ".join(errors))


# ── Config dataclasses ──────────────────────────────────────────────────

@dataclass
class ArrayConfig:
    ring1_radius: float = 0.34
    ring2_radius: float = 0.17
    n_mics_ring1: int = 8
    n_mics_ring2: int = 8
    ring_spacing: float = 0.20

    def __post_init__(self):
        errors = []
        _check(0 < self.ring1_radius <= 5, f"ring1_radius must be in (0, 5], got {self.ring1_radius}", errors)
        _check(0 < self.ring2_radius <= 5, f"ring2_radius must be in (0, 5], got {self.ring2_radius}", errors)
        _check(2 <= self.n_mics_ring1 <= 64, f"n_mics_ring1 must be in [2, 64], got {self.n_mics_ring1}", errors)
        _check(2 <= self.n_mics_ring2 <= 64, f"n_mics_ring2 must be in [2, 64], got {self.n_mics_ring2}", errors)
        _check(0 < self.ring_spacing <= 2, f"ring_spacing must be in (0, 2], got {self.ring_spacing}", errors)
        if errors:
            raise ValueError("ArrayConfig: " + "; ".join(errors))


@dataclass
class MicConfig:
    model: str = "ics-52000"
    snr_dba: float = 65.0
    sensitivity_dbFS: float = -26.0
    aop_db_spl: float = 120.0

    def __post_init__(self):
        errors = []
        _check(20 <= self.snr_dba <= 120, f"snr_dba must be in [20, 120], got {self.snr_dba}", errors)
        _check(-100 <= self.sensitivity_dbFS <= 0, f"sensitivity_dbFS must be in [-100, 0], got {self.sensitivity_dbFS}", errors)
        _check(60 <= self.aop_db_spl <= 200, f"aop_db_spl must be in [60, 200], got {self.aop_db_spl}", errors)
        if errors:
            raise ValueError("MicConfig: " + "; ".join(errors))


@dataclass
class SignalConfig:
    fs: int = 48000
    duration: float = 5.0
    snr_db: float | None = None
    drone_spl_db: float = 70.0

    def __post_init__(self):
        errors = []
        _check(8000 <= self.fs <= 192000, f"fs must be in [8000, 192000], got {self.fs}", errors)
        _check(0 < self.duration <= 3600, f"duration must be in (0, 3600], got {self.duration}", errors)
        if self.snr_db is not None:
            _check(-10 <= self.snr_db <= 60, f"snr_db must be in [-10, 60] or None, got {self.snr_db}", errors)
        _check(0 <= self.drone_spl_db <= 200, f"drone_spl_db must be in [0, 200], got {self.drone_spl_db}", errors)
        if errors:
            raise ValueError("SignalConfig: " + "; ".join(errors))


@dataclass
class MotionConfig:
    enabled: bool = False
    velocity: tuple = (0.0, 0.0, 0.0)

    def __post_init__(self):
        errors = []
        if self.enabled and len(self.velocity) != 3:
            errors.append(f"velocity must have 3 elements, got {len(self.velocity)}")
        if errors:
            raise ValueError("MotionConfig: " + "; ".join(errors))


@dataclass
class DroneConfig:
    rpm: int = 6000
    num_blades: int = 2
    num_rotors: int = 4
    distance: float = 10.0
    initial_bearing: dict = field(default_factory=lambda: {"azimuth_deg": 15.0, "elevation_deg": 10.0})
    motion: MotionConfig = field(default_factory=MotionConfig)
    trajectory: dict = field(default_factory=dict)
    bpf_harmonics: int = 6

    def __post_init__(self):
        errors = []
        _check(0 < self.rpm <= 100000, f"rpm must be in (0, 100000], got {self.rpm}", errors)
        _check(1 <= self.num_blades <= 8, f"num_blades must be in [1, 8], got {self.num_blades}", errors)
        _check(1 <= self.num_rotors <= 16, f"num_rotors must be in [1, 16], got {self.num_rotors}", errors)
        _check(self.distance > 0, f"distance must be > 0, got {self.distance}", errors)
        _check(1 <= self.bpf_harmonics <= 20, f"bpf_harmonics must be in [1, 20], got {self.bpf_harmonics}", errors)
        if "azimuth_deg" not in self.initial_bearing or "elevation_deg" not in self.initial_bearing:
            errors.append("initial_bearing must contain keys 'azimuth_deg' and 'elevation_deg'")
        if errors:
            raise ValueError("DroneConfig: " + "; ".join(errors))


@dataclass
class SearchConfig:
    azimuth_range: list = field(default_factory=lambda: [-60.0, 60.0])
    elevation_range: list = field(default_factory=lambda: [-60.0, 60.0])
    resolution_deg: float = 2.0

    def __post_init__(self):
        errors = []
        _check(len(self.azimuth_range) == 2, f"azimuth_range must have 2 elements, got {len(self.azimuth_range)}", errors)
        _check(len(self.elevation_range) == 2, f"elevation_range must have 2 elements, got {len(self.elevation_range)}", errors)
        if len(self.azimuth_range) == 2:
            _check(self.azimuth_range[0] < self.azimuth_range[1],
                   f"azimuth_range[0] ({self.azimuth_range[0]}) must be < azimuth_range[1] ({self.azimuth_range[1]})", errors)
        if len(self.elevation_range) == 2:
            _check(self.elevation_range[0] < self.elevation_range[1],
                   f"elevation_range[0] ({self.elevation_range[0]}) must be < elevation_range[1] ({self.elevation_range[1]})", errors)
        _check(0.1 <= self.resolution_deg <= 90, f"resolution_deg must be in [0.1, 90], got {self.resolution_deg}", errors)
        if errors:
            raise ValueError("SearchConfig: " + "; ".join(errors))


@dataclass
class DetectionConfig:
    enabled: bool = True
    method: str = "peak_to_mean"
    psr_threshold_db: float = 3.0
    peak_to_mean_threshold_db: float = 5.0

    def __post_init__(self):
        errors = []
        _check(self.method in ("peak_to_mean", "peak_to_sidelobe", "threshold"),
               f"method must be one of peak_to_mean/peak_to_sidelobe/threshold, got '{self.method}'", errors)
        _check(0 <= self.psr_threshold_db <= 60, f"psr_threshold_db must be in [0, 60], got {self.psr_threshold_db}", errors)
        _check(0 <= self.peak_to_mean_threshold_db <= 60,
               f"peak_to_mean_threshold_db must be in [0, 60], got {self.peak_to_mean_threshold_db}", errors)
        if errors:
            raise ValueError("DetectionConfig: " + "; ".join(errors))


@dataclass
class SRPPhatConfig:
    fft_size: int = 2048
    hop_length: int = 512
    search: SearchConfig = field(default_factory=SearchConfig)
    max_freq: float = 4000.0
    mode: str = "phat"
    frequency_weight: float = 0.0
    detection: DetectionConfig = field(default_factory=DetectionConfig)

    def __post_init__(self):
        errors = []
        _check(self.fft_size > 0 and (self.fft_size & (self.fft_size - 1)) == 0,
               f"fft_size must be a power of 2, got {self.fft_size}", errors)
        _check(0 < self.hop_length <= self.fft_size,
               f"hop_length must be in (0, fft_size], got {self.hop_length}", errors)
        _check(self.max_freq > 0, f"max_freq must be > 0, got {self.max_freq}", errors)
        _check(self.mode in ("phat", "standard"),
               f"mode must be 'phat' or 'standard', got '{self.mode}'", errors)
        _check(0 <= self.frequency_weight <= 5,
               f"frequency_weight must be in [0, 5], got {self.frequency_weight}", errors)
        if errors:
            raise ValueError("SRPPhatConfig: " + "; ".join(errors))


@dataclass
class GroundConfig:
    height_m: float = 5.0
    tilt_deg: float = 0.0
    reflection_coefficient: float = 0.5
    model: str = "constant"
    flow_resistivity: float = 200000.0

    def __post_init__(self):
        errors = []
        _check(self.height_m >= 0, f"height_m must be >= 0, got {self.height_m}", errors)
        _check(0 <= self.reflection_coefficient <= 1,
               f"reflection_coefficient must be in [0, 1], got {self.reflection_coefficient}", errors)
        _check(self.model in ("constant", "delany_bazley"),
               f"model must be 'constant' or 'delany_bazley', got '{self.model}'", errors)
        _check(self.flow_resistivity > 0, f"flow_resistivity must be > 0, got {self.flow_resistivity}", errors)
        if errors:
            raise ValueError("GroundConfig: " + "; ".join(errors))


@dataclass
class AtmosphericConfig:
    temperature_C: float = 20.0
    humidity_pct: float = 50.0
    pressure_kPa: float = 101.325

    def __post_init__(self):
        errors = []
        _check(-50 <= self.temperature_C <= 60,
               f"temperature_C must be in [-50, 60], got {self.temperature_C}", errors)
        _check(0 <= self.humidity_pct <= 100,
               f"humidity_pct must be in [0, 100], got {self.humidity_pct}", errors)
        _check(80 <= self.pressure_kPa <= 110,
               f"pressure_kPa must be in [80, 110], got {self.pressure_kPa}", errors)
        if errors:
            raise ValueError("AtmosphericConfig: " + "; ".join(errors))


@dataclass
class RefractionConfig:
    enabled: bool = False
    wind_shear_ms_per_m: float = 0.0
    temperature_lapse_rate: float = -0.0065
    roughness_length: float = 0.03

    def __post_init__(self):
        errors = []
        _check(self.roughness_length > 0, f"roughness_length must be > 0, got {self.roughness_length}", errors)
        if errors:
            raise ValueError("RefractionConfig: " + "; ".join(errors))


@dataclass
class TurbulenceConfig:
    amplitude_scintillation: bool = False
    scintillation_strength: float = 0.1

    def __post_init__(self):
        errors = []
        _check(0 <= self.scintillation_strength <= 1,
               f"scintillation_strength must be in [0, 1], got {self.scintillation_strength}", errors)
        if errors:
            raise ValueError("TurbulenceConfig: " + "; ".join(errors))


@dataclass
class NoiseConfig:
    wind_speed_ms: float = 0.0
    wind_direction_deg: float = 0.0
    traffic_density: str = "none"
    traffic_direction_deg: float = 90.0
    bird_activity: float = 0.0
    ambient_db: float = 0.0

    def __post_init__(self):
        errors = []
        _check(0 <= self.wind_speed_ms <= 100, f"wind_speed_ms must be in [0, 100], got {self.wind_speed_ms}", errors)
        _check(0 <= self.wind_direction_deg < 360,
               f"wind_direction_deg must be in [0, 360), got {self.wind_direction_deg}", errors)
        _check(self.traffic_density in ("none", "light", "moderate", "heavy"),
               f"traffic_density must be one of none/light/moderate/heavy, got '{self.traffic_density}'", errors)
        _check(0 <= self.bird_activity <= 1, f"bird_activity must be in [0, 1], got {self.bird_activity}", errors)
        _check(0 <= self.ambient_db <= 120, f"ambient_db must be in [0, 120], got {self.ambient_db}", errors)
        if errors:
            raise ValueError("NoiseConfig: " + "; ".join(errors))


@dataclass
class EnvironmentConfig:
    enabled: bool = False
    ground: GroundConfig = field(default_factory=GroundConfig)
    noise: NoiseConfig = field(default_factory=NoiseConfig)
    atmospheric: AtmosphericConfig = field(default_factory=AtmosphericConfig)
    refraction: RefractionConfig = field(default_factory=RefractionConfig)
    turbulence: TurbulenceConfig = field(default_factory=TurbulenceConfig)


@dataclass
class OutputConfig:
    animation_fps: int = 15
    save_animation: bool = True
    save_3d_animation: bool = True
    save_figures: bool = True
    save_data: bool = True

    def __post_init__(self):
        errors = []
        _check(1 <= self.animation_fps <= 120,
               f"animation_fps must be in [1, 120], got {self.animation_fps}", errors)
        if errors:
            raise ValueError("OutputConfig: " + "; ".join(errors))


@dataclass
class Config:
    array: ArrayConfig = field(default_factory=ArrayConfig)
    signal: SignalConfig = field(default_factory=SignalConfig)
    mic: MicConfig = field(default_factory=MicConfig)
    drone: DroneConfig = field(default_factory=DroneConfig)
    srpphat: SRPPhatConfig = field(default_factory=SRPPhatConfig)
    environment: EnvironmentConfig = field(default_factory=EnvironmentConfig)
    output: OutputConfig = field(default_factory=OutputConfig)

    @classmethod
    def from_dict(cls, data):
        return _dataclass_from_dict(cls, data)

    def to_dict(self):
        return _dataclass_to_dict(self)

    @classmethod
    def from_yaml(cls, path):
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls.from_dict(data)

    @classmethod
    def from_yamls(cls, *paths):
        """Load and merge multiple YAML files (later overrides earlier)."""
        merged = {}
        for path in paths:
            with open(path) as f:
                data = yaml.safe_load(f)
            if data:
                deep_merge(merged, data)
        return cls.from_dict(merged)

    def merge(self, overrides):
        """Return a new Config with *overrides* dict merged on top."""
        base = self.to_dict()
        deep_merge(base, overrides)
        return Config.from_dict(base)

    @classmethod
    def schema(cls):
        """Return a human-readable YAML schema string with descriptions and defaults."""
        lines = ["# Patronus Simulation Configuration Schema"]
        lines.append("")

        _schema_lines(lines, cls, indent=0)

        return "\n".join(lines)


def _schema_lines(lines, cls, indent):
    prefix = "  " * indent
    for f in fields(cls):
        ftype = f.type
        if f.default is not MISSING:
            default = f.default
        elif f.default_factory is not MISSING:
            default = f.default_factory()
        else:
            default = "REQUIRED"

        if is_dataclass(ftype):
            lines.append(f"{prefix}# {f.name} ...")
            lines.append(f"{prefix}{f.name}:")
            _schema_lines(lines, ftype, indent + 1)
        else:
            type_hint = getattr(ftype, "__name__", str(ftype))
            lines.append(f"{prefix}# {f.name}: {type_hint}  (default: {default})")
            lines.append(f"{prefix}{f.name}: {default}")


def deep_merge(base, override):
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            deep_merge(base[key], value)
        else:
            base[key] = value


def parse_dotted_key(key, value):
    parts = key.split(".")
    current = {}
    result = current
    for part in parts[:-1]:
        current[part] = {}
        current = current[part]
    current[parts[-1]] = value
    return result
