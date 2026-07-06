import numpy as np

from .config import Config
from .constants import EPS_NORM, SPEED_OF_SOUND_REF, speed_of_sound
from .geometry import cartesian_to_angles, make_array
from .drone_signal import DroneSource
from .sensor import SensorModel, effective_snr_db
from .srpphat import SRPPhatProcessor
from .metrics import compute_metrics, compute_gate1
from .visualize import save_summary_figures
from .visualize_3d import create_beamsphere_animation
from .environment import Environment


class Simulation:
    def __init__(self, config: Config):
        self.config = config

        # Calibrated Pa-referenced path unless the snr_db override is set
        # (sweeps use snr_db as a direct level knob; that legacy path keeps
        # normalized units and signal-relative noise).
        self.calibrated = config.signal.snr_db is None

        # One speed of sound for geometry steering, propagation, and noise
        # paths alike. Environment disabled keeps the 343.0 reference;
        # enabled uses Cramer (1993) with temperature, humidity, pressure.
        if config.environment.enabled:
            atm = config.environment.atmospheric
            self.speed_sound = speed_of_sound(
                atm.temperature_C,
                humidity_pct=atm.humidity_pct,
                pressure_kPa=atm.pressure_kPa,
            )
        else:
            self.speed_sound = SPEED_OF_SOUND_REF

        self.array = make_array(config.array, speed_sound=self.speed_sound)
        self.sensor = SensorModel(
            config.mic, self.array.n_mics, config.signal.fs
        )
        self.array.perturb(self.sensor.position_offsets)

        self.env = Environment(
            config.environment,
            config.signal.fs,
            self.array.n_mics,
            config.signal.duration,
            array_center=np.array([0.0, 0.0, 0.0]),
            speed_sound=self.speed_sound,
            calibrated=self.calibrated,
        )

        absorption = self.env.absorption if self.env.enabled else None
        refraction = self.env.refraction if self.env.enabled else None

        if self.env.enabled:
            atm = config.environment.atmospheric
            noise_cfg = config.environment.noise
            temp_C = atm.temperature_C
            press_kPa = atm.pressure_kPa
            wind_ms = noise_cfg.wind_speed_ms
            wind_deg = noise_cfg.wind_direction_deg
        else:
            temp_C, press_kPa, wind_ms, wind_deg = 20.0, 101.325, 0.0, 0.0

        turb = config.environment.turbulence
        self.drone = DroneSource(
            config.drone,
            absorption=absorption,
            refraction=refraction,
            scintillation_enabled=(
                self.env.enabled and turb.amplitude_scintillation
            ),
            scintillation_strength=(
                turb.scintillation_strength if self.env.enabled else 0.0
            ),
            temperature_C=temp_C,
            pressure_kPa=press_kPa,
            wind_speed_ms=wind_ms,
            wind_direction_deg=wind_deg,
            speed_sound=self.speed_sound,
            turbulence_tau_std_s=turb.phase_jitter_std_us * 1e-6,
            turbulence_tau_corr_s=turb.phase_jitter_corr_ms * 1e-3,
            scintillation_tau_corr_s=turb.scintillation_corr_ms * 1e-3,
            source_spl_db=(config.signal.drone_spl_db if self.calibrated
                           else None),
        )

        self.srp = SRPPhatProcessor(
            array=self.array,
            fs=config.signal.fs,
            fft_size=config.srpphat.fft_size,
            hop_length=config.srpphat.hop_length,
            search_config=config.srpphat.search,
            max_freq=config.srpphat.max_freq,
            min_freq=config.srpphat.min_freq,
            mode=config.srpphat.mode,
            frequency_weight=config.srpphat.frequency_weight,
            detection_config=config.srpphat.detection,
        )

    def run(self):
        cfg = self.config
        fs = cfg.signal.fs
        duration = cfg.signal.duration

        # Signal/noise generation uses the global numpy RNG throughout.
        if cfg.signal.seed is not None:
            np.random.seed(cfg.signal.seed)

        snr_db = effective_snr_db(
            cfg, absorption=self.env.absorption if self.env.enabled else None
        )

        tilt_deg = cfg.environment.ground.tilt_deg if cfg.environment.enabled else 0.0
        if tilt_deg != 0:
            self.array.set_tilt(tilt_deg)

        if self.env.has_ground:
            mic_world = self.array.get_mic_positions_world()
            self.drone.set_ground(self.env.ground, mic_world)

        print("Generating microphone signals...")
        mic_signals, source_positions = self.drone.generate_mic_signals(
            self.array, fs, duration
        )
        self._wind_dir = None
        if self.calibrated:
            # Acoustic noise is pressure at the diaphragm: it enters the
            # mic chain (HPF, clip, EIN, Pa→FS, quantization) with the signal.
            if self.env.has_noise:
                print("Adding environmental noise...")
                mic_pos = self.array.get_mic_positions_world()
                env_noise = self.env.generate_noise(mic_pos)
                if env_noise is not None:
                    mic_signals += env_noise[:, :mic_signals.shape[1]]
                self._wind_dir = self.env.wind_coherence_directionality(mic_pos)
            mic_signals = self.sensor.apply(mic_signals, absolute=True)
        else:
            # Legacy order preserved bit-for-bit (snr_db override path).
            mic_signals = self.sensor.apply(mic_signals, snr_db)
            if self.env.has_noise:
                print("Adding environmental noise...")
                mic_pos = self.array.get_mic_positions_world()
                env_noise = self.env.generate_noise(mic_pos)
                if env_noise is not None:
                    mic_signals += env_noise[:, :mic_signals.shape[1]]
                self._wind_dir = self.env.wind_coherence_directionality(mic_pos)

        if self.env.has_ground and hasattr(self.array, "world_to_array_coords"):
            source_positions = self.array.world_to_array_coords(source_positions)

        fft_size = cfg.srpphat.fft_size
        hop = cfg.srpphat.hop_length
        n_samples = mic_signals.shape[1]

        frame_starts = np.arange(0, n_samples - fft_size + 1, hop)
        n_frames = len(frame_starts)
        center_samples = frame_starts + fft_size // 2
        timestamps = center_samples / fs

        # Gate 1: band-limited RMS + spectral flatness (post-noise)
        gate1, gate1_rms, gate1_flatness = compute_gate1(mic_signals, fs, fft_size, hop)

        true_doas = np.zeros((n_frames, 2))
        estimated_doas = np.full((n_frames, 2), np.nan)
        srp_maps = []
        peak_values = np.zeros(n_frames)
        detections = np.zeros(n_frames, dtype=bool)
        frame_snrs = np.full(n_frames, np.nan)

        print(f"Processing {n_frames} frames...")
        for i, start in enumerate(frame_starts):
            pos = source_positions[center_samples[i]]
            direction = pos / (np.linalg.norm(pos) + EPS_NORM)
            true_az, true_el = cartesian_to_angles(direction)
            true_doas[i] = [true_az, true_el]

            frame = mic_signals[:, start:start + fft_size]
            result = self.srp.process_frame(frame)

            estimated_doas[i] = result["estimated_doa"]
            srp_maps.append(result["srp_map"])
            peak_values[i] = result["peak_value"]
            detections[i] = result["detected"]

            frame_snrs[i] = snr_db

            if (i + 1) % max(1, n_frames // 10) == 0:
                print(f"  Frame {i + 1}/{n_frames}")

        srp_maps = np.array(srp_maps)

        results = {
            "true_doas": true_doas,
            "estimated_doas": estimated_doas,
            "srp_maps": srp_maps,
            "peak_values": peak_values,
            "detections": detections,
            "gate1": gate1,
            "gate1_rms_db": gate1_rms,
            "gate1_flatness": gate1_flatness,
            "timestamps": timestamps,
            "mic_signals": mic_signals,
            "source_positions": source_positions,
            "center_samples": center_samples,
            "n_frames": n_frames,
            "fs": fs,
            "frame_snrs": frame_snrs,
            "wind_coherence_directionality": self._wind_dir,
        }

        print("Computing metrics...")
        metrics = compute_metrics(results, self.array, self.srp)

        results["metrics"] = metrics
        return results

    def save_results(self, results, output_dir):
        output_dir = output_dir / "data"
        output_dir.mkdir(parents=True, exist_ok=True)
        np.savez(
            output_dir / "simulation_results.npz",
            true_doas=results["true_doas"],
            estimated_doas=results["estimated_doas"],
            srp_maps=results["srp_maps"],
            peak_values=results["peak_values"],
            detections=results["detections"],
            timestamps=results["timestamps"],
            frame_snrs=results["frame_snrs"],
        )
        print(f"Data saved to {output_dir / 'simulation_results.npz'}")

    def plot_results(self, results, output_dir):
        save_anim = self.config.output.save_animation or self.config.output.save_3d_animation

        if save_anim:
            print("Creating beamsphere animation...")
            anim = create_beamsphere_animation(results, self.config, self.array, self.srp)
            anim_path = output_dir / "animations" / "beamforming_3d.mp4"
            anim_path.parent.mkdir(parents=True, exist_ok=True)
            anim.save(str(anim_path), fps=self.config.output.animation_fps)
            print(f"Animation saved to {anim_path}")

        print("Saving summary figures...")
        save_summary_figures(results, self.config, self.array, self.srp, output_dir / "figures")
        print(f"Figures saved to {output_dir / 'figures'}")
