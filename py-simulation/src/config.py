from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class ArrayConfig:
    ring1_radius: float = 0.15
    ring2_radius: float = 0.15
    n_mics_ring1: int = 8
    n_mics_ring2: int = 8
    ring_spacing: float = 0.30


@dataclass
class MicConfig:
    snr_dba: float = 65.0          # ICS-52000: 65 dBA (94 dB SPL @ 1 kHz ref)
    sensitivity_dbFS: float = -26.0  # dBFS at 94 dB SPL, 1 kHz
    aop_db_spl: float = 120.0      # Acoustic Overload Point (dB SPL)


@dataclass
class SignalConfig:
    fs: int = 48000
    duration: float = 5.0
    snr_db: float | None = None   # Manual SNR override (None = derive from mic specs)
    drone_spl_db: float = 70.0    # Drone SPL at 1m (for EIN-based SNR)


@dataclass
class MotionConfig:
    enabled: bool = False
    velocity: tuple = (0.0, 0.0, 0.0)


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


@dataclass
class SearchConfig:
    azimuth_range: list = field(default_factory=lambda: [-60.0, 60.0])
    elevation_range: list = field(default_factory=lambda: [-60.0, 60.0])
    resolution_deg: float = 2.0


@dataclass
class DetectionConfig:
    enabled: bool = True
    method: str = "peak_to_mean"
    psr_threshold_db: float = 3.0
    peak_to_mean_threshold_db: float = 5.0


@dataclass
class SRPPhatConfig:
    fft_size: int = 2048
    hop_length: int = 512
    search: SearchConfig = field(default_factory=SearchConfig)
    max_freq: float = 4000.0
    mode: str = "phat"       # "phat" (phase transform) or "standard" (delay-and-sum)
    frequency_weight: float = 0.0  # 0=flat, 0.5=sqrt, 1=linear, 2=quadratic emphasis on high freqs
    detection: DetectionConfig = field(default_factory=DetectionConfig)


@dataclass
class OutputConfig:
    animation_fps: int = 15
    save_animation: bool = True
    save_3d_animation: bool = True
    save_figures: bool = True
    save_data: bool = True


@dataclass
class GroundConfig:
    height_m: float = 5.0
    tilt_deg: float = 0.0
    reflection_coefficient: float = 0.5
    model: str = "constant"
    flow_resistivity: float = 200000.0


@dataclass
class AtmosphericConfig:
    temperature_C: float = 20.0
    humidity_pct: float = 50.0
    pressure_kPa: float = 101.325


@dataclass
class RefractionConfig:
    enabled: bool = False
    wind_shear_ms_per_m: float = 0.0
    temperature_lapse_rate: float = -0.0065
    roughness_length: float = 0.03


@dataclass
class TurbulenceConfig:
    amplitude_scintillation: bool = False
    scintillation_strength: float = 0.1


@dataclass
class NoiseConfig:
    wind_speed_ms: float = 0.0
    wind_direction_deg: float = 0.0     # azimuth (0 = front, 90 = right)
    traffic_density: str = "none"
    traffic_direction_deg: float = 90.0  # road azimuth from array
    bird_activity: float = 0.0
    ambient_db: float = 0.0


@dataclass
class EnvironmentConfig:
    enabled: bool = False
    ground: GroundConfig = field(default_factory=GroundConfig)
    noise: NoiseConfig = field(default_factory=NoiseConfig)
    atmospheric: AtmosphericConfig = field(default_factory=AtmosphericConfig)
    refraction: RefractionConfig = field(default_factory=RefractionConfig)
    turbulence: TurbulenceConfig = field(default_factory=TurbulenceConfig)


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
    def from_yaml(cls, path):
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data):
        if data is None:
            return cls()

        def pop_dict(d, key, default=None):
            v = d.get(key, default)
            return v if v is not None else default

        array = ArrayConfig(**data.get("array", {}))
        signal = SignalConfig(**data.get("signal", {}))
        mic = MicConfig(**data.get("mic", {}))
        drone_data = data.get("drone", {}) or {}
        motion = MotionConfig(**drone_data.get("motion", {})) if drone_data.get("motion") else MotionConfig()
        traj_data = drone_data.get("trajectory", {}) or {}
        drone_kwargs = {k: v for k, v in drone_data.items() if k not in ("motion", "trajectory")}
        drone = DroneConfig(**drone_kwargs, motion=motion, trajectory=traj_data)
        srpphat_data = data.get("srpphat", {}) or {}
        search = SearchConfig(**srpphat_data.get("search", {})) if srpphat_data.get("search") else SearchConfig()
        detection_data = srpphat_data.get("detection", {}) or {}
        detection = DetectionConfig(**detection_data)
        srpphat_kwargs = {k: v for k, v in srpphat_data.items() if k not in ("search", "detection")}
        srpphat = SRPPhatConfig(**srpphat_kwargs, search=search, detection=detection)

        env_data = data.get("environment", {}) or {}
        ground_data = env_data.get("ground", {}) or {}
        ground = GroundConfig(**ground_data)
        noise_data = env_data.get("noise", {}) or {}
        noise = NoiseConfig(**noise_data)
        atmos_data = env_data.get("atmospheric", {}) or {}
        atmospheric = AtmosphericConfig(**atmos_data)
        refrac_data = env_data.get("refraction", {}) or {}
        refraction = RefractionConfig(**refrac_data)
        turb_data = env_data.get("turbulence", {}) or {}
        turbulence = TurbulenceConfig(**turb_data)
        env_kwargs = {k: v for k, v in env_data.items()
                      if k not in ("ground", "noise", "atmospheric", "refraction", "turbulence")}
        environment = EnvironmentConfig(**env_kwargs, ground=ground, noise=noise,
                                        atmospheric=atmospheric, refraction=refraction,
                                        turbulence=turbulence)

        output = OutputConfig(**data.get("output", {}))
        return cls(array=array, signal=signal, mic=mic, drone=drone, srpphat=srpphat,
                    environment=environment, output=output)


def deep_merge(base, override):
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            deep_merge(base[key], value)
        else:
            base[key] = value


def parse_dotted_key(key, value):
    parts = key.split(".")
    result = {}
    current = result
    for part in parts[:-1]:
        current[part] = {}
        current = current[part]
    current[parts[-1]] = value
    return result
