import numpy as np

from .config import Config
from .geometry import DualRingArray
from .drone_signal import DroneSource
from .srpphat import SRPPhatProcessor
from .metrics import compute_metrics
from .visualize import save_summary_figures
from .visualize_3d import create_beamsphere_animation
from .environment import Environment


class Simulation:
    def __init__(self, config: Config):
        self.config = config
        self.array = DualRingArray(config.array)
        self.drone = DroneSource(config.drone)
        self.srp = SRPPhatProcessor(
            array=self.array,
            fs=config.signal.fs,
            fft_size=config.srpphat.fft_size,
            hop_length=config.srpphat.hop_length,
            search_config=config.srpphat.search,
            max_freq=config.srpphat.max_freq,
            mode=config.srpphat.mode,
            frequency_weight=config.srpphat.frequency_weight,
            detection_config=config.srpphat.detection,
        )
        self.env = Environment(
            config.environment,
            config.signal.fs,
            self.array.n_mics,
            config.signal.duration,
            array_center=np.array([0.0, 0.0, 0.0]),
        )

    def run(self):
        cfg = self.config
        fs = cfg.signal.fs
        duration = cfg.signal.duration

        # Compute SNR: manual override or derive from ICS-52000 EIN + drone SPL
        snr_db = cfg.signal.snr_db
        if snr_db is None:
            mic = cfg.mic
            ref_spl = 94.0  # dB SPL reference for SNR spec
            ein_db = ref_spl - mic.snr_dba  # Equivalent Input Noise (dBA)
            dist = cfg.drone.distance
            spl_at_mic = cfg.signal.drone_spl_db - 20 * np.log10(max(dist, 0.1))
            snr_db = float(spl_at_mic - ein_db)

        tilt_deg = cfg.environment.ground.tilt_deg if cfg.environment.enabled else 0.0
        if tilt_deg != 0:
            self.array.set_tilt(tilt_deg)

        if self.env.has_ground:
            mic_world = self.array.get_mic_positions_world()
            self.drone.set_ground(self.env.ground, mic_world)

        print("Generating microphone signals...")
        mic_signals, source_positions = self.drone.generate_mic_signals(
            self.array, fs, duration, snr_db
        )

        if self.env.has_noise:
            print("Adding environmental noise...")
            mic_pos = self.array.get_mic_positions_world()
            env_noise = self.env.generate_noise(mic_pos)
            if env_noise is not None:
                env_noise = env_noise[:, :mic_signals.shape[1]]
                mic_signals += env_noise

        if self.env.has_ground and hasattr(self.array, "world_to_array_coords"):
            source_positions = self.array.world_to_array_coords(source_positions)

        fft_size = cfg.srpphat.fft_size
        hop = cfg.srpphat.hop_length
        n_samples = mic_signals.shape[1]

        frame_starts = np.arange(0, n_samples - fft_size + 1, hop)
        n_frames = len(frame_starts)
        center_samples = frame_starts + fft_size // 2
        timestamps = center_samples / fs

        true_doas = np.zeros((n_frames, 2))
        estimated_doas = np.full((n_frames, 2), np.nan)
        srp_maps = []
        peak_values = np.zeros(n_frames)
        detections = np.zeros(n_frames, dtype=bool)

        print(f"Processing {n_frames} frames...")
        for i, start in enumerate(frame_starts):
            pos = source_positions[center_samples[i]]
            direction = pos / (np.linalg.norm(pos) + 1e-10)
            true_az, true_el = DualRingArray.cartesian_to_angles(direction)
            true_doas[i] = [true_az, true_el]

            frame = mic_signals[:, start:start + fft_size]
            result = self.srp.process_frame(frame)

            estimated_doas[i] = result["estimated_doa"]
            srp_maps.append(result["srp_map"])
            peak_values[i] = result["peak_value"]
            detections[i] = result["detected"]

            if (i + 1) % max(1, n_frames // 10) == 0:
                print(f"  Frame {i + 1}/{n_frames}")

        srp_maps = np.array(srp_maps)

        results = {
            "true_doas": true_doas,
            "estimated_doas": estimated_doas,
            "srp_maps": srp_maps,
            "peak_values": peak_values,
            "detections": detections,
            "timestamps": timestamps,
            "mic_signals": mic_signals,
            "source_positions": source_positions,
            "center_samples": center_samples,
            "n_frames": n_frames,
            "fs": fs,
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
