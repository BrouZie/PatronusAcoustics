import numpy as np
from scipy.signal import butter, lfilter, sosfilt

from .trajectory import make_trajectory


class DroneSource:
    def __init__(self, config):
        self.rpm = config.rpm
        self.num_blades = config.num_blades
        self.bpf = (config.rpm * config.num_blades) / 60.0
        self.num_rotors = config.num_rotors
        self.speed_sound = 343.0

        self.trajectory = make_trajectory(config)
        self.ground_reflector = None
        self.mic_positions_world = None
        self.mic = getattr(config, 'mic', None)

    def get_position(self, t):
        return self.trajectory.get_position(t)

    def _generate_source_signal(self, n_samples, fs):
        t = np.arange(n_samples) / fs

        signal = np.zeros(n_samples)
        for k in range(1, 7):
            amp = 1.0 / k
            freq = k * self.bpf
            phase = np.random.uniform(0, 2 * np.pi)
            signal += amp * np.sin(2 * np.pi * freq * t + phase)

        noise = np.random.randn(n_samples)
        b, a = butter(4, 2000 / (fs / 2), btype="low")
        bb_noise = lfilter(b, a, noise)
        bb_noise *= 0.3
        signal += bb_noise

        signal /= np.std(signal)

        if self.mic is not None:
            signal = self._apply_mic_frequency_response(signal, fs)
        return signal

    def _apply_mic_frequency_response(self, signal, fs):
        sos = butter(1, 75.0 / (fs / 2), btype="high", output="sos")
        return sosfilt(sos, signal)

    def _apply_aop_clipping(self, mic_signals):
        if self.mic is None:
            return mic_signals
        peak = np.max(np.abs(mic_signals))
        if peak > 0.5:
            mic_signals = np.tanh(mic_signals) * 0.95
        return mic_signals

    def set_ground(self, ground_reflector, mic_positions_world):
        self.ground_reflector = ground_reflector
        self.mic_positions_world = mic_positions_world

    def _generate_turbulence(self, n_samples, fs, n_mics, tau_std=15e-6, tau_corr=0.05):
        dt = 1.0 / fs
        theta = 1.0 / tau_corr
        a = 1.0 - theta * dt
        b = tau_std * np.sqrt(2 * theta * dt)
        tau = np.zeros((n_mics, n_samples))
        tau[:, 0] = np.random.randn(n_mics) * tau_std
        innovations = np.random.randn(n_mics, n_samples - 1) * b
        zi = a * tau[:, 0:1]
        tau[:, 1:], _ = lfilter([1.0], [1.0, -a], innovations, axis=1, zi=zi)
        return tau

    def _apply_delays_reflected(self, source, array, fs, pos, mic_positions_world):
        image_pos = self.ground_reflector.get_image_source(pos)
        coeff = self.ground_reflector.reflection_coefficient
        dists_direct = np.linalg.norm(mic_positions_world - pos, axis=1)
        dists_image = np.linalg.norm(mic_positions_world - image_pos, axis=1)
        n = len(source)
        n_pad = 2 ** int(np.ceil(np.log2(n + n)))
        source_pad = np.pad(source, (0, n_pad - n))
        S = np.fft.fft(source_pad)
        freqs = np.fft.fftfreq(n_pad, 1 / fs)
        result = np.zeros((array.n_mics, n))
        for m in range(array.n_mics):
            delay_img = dists_image[m] / self.speed_sound
            H = np.exp(-1j * 2 * np.pi * freqs * delay_img)
            delayed = np.fft.ifft(S * H).real[:n]
            atten = coeff * dists_direct[m] / (dists_image[m] + 1e-6)
            result[m] = -atten * delayed
        return result

    def generate_mic_signals(self, array, fs, duration, snr_db):
        n_samples = int(duration * fs)
        n_mics = array.n_mics
        t = np.arange(n_samples) / fs

        source = self._generate_source_signal(n_samples, fs)
        source_positions = np.zeros((n_samples, 3))

        turbulence = self._generate_turbulence(n_samples, fs, n_mics)

        has_ground_reflection = (
            self.ground_reflector is not None
            and self.mic_positions_world is not None
        )
        mic_pos = self.mic_positions_world if has_ground_reflection else array.positions

        if self.trajectory.is_stationary:
            pos = self.trajectory.get_position(0)
            source_positions[:] = pos
            mic_signals = self._apply_delays_stationary(source, array, fs, pos, turbulence)
            if has_ground_reflection:
                mic_signals += self._apply_delays_reflected_turbulent(
                    source, array, fs, pos, mic_pos, turbulence
                )
        else:
            mic_signals = np.zeros((n_mics, n_samples))
            for i in range(n_samples):
                pos = self.trajectory.get_position(t[i])
                source_positions[i] = pos

                dists_direct = np.linalg.norm(mic_pos - pos, axis=1)
                delays_direct = dists_direct / self.speed_sound

                if has_ground_reflection:
                    image_pos = self.ground_reflector.get_image_source(pos)
                    dists_image = np.linalg.norm(mic_pos - image_pos, axis=1)
                    delays_image = dists_image / self.speed_sound
                    coeff = self.ground_reflector.reflection_coefficient

                for m in range(n_mics):
                    turb = turbulence[m, i]
                    atten = 1.0 / (dists_direct[m] + 1e-6)
                    delay_samp = (delays_direct[m] + turb) * fs
                    idx = i - delay_samp
                    if 0 <= idx < n_samples - 1:
                        int_idx = int(np.floor(idx))
                        frac = idx - int_idx
                        mic_signals[m, i] = atten * (
                            (1 - frac) * source[int_idx] + frac * source[int_idx + 1]
                        )

                    if has_ground_reflection:
                        turb_img = turbulence[m, i] * 0.5
                        atten_img = coeff * dists_direct[m] / (dists_image[m] + 1e-6)
                        delay_samp_img = (delays_image[m] + turb_img) * fs
                        idx_img = i - delay_samp_img
                        if 0 <= idx_img < n_samples - 1:
                            int_idx = int(np.floor(idx_img))
                            frac = idx_img - int_idx
                            mic_signals[m, i] -= atten_img * (
                                (1 - frac) * source[int_idx] + frac * source[int_idx + 1]
                            )

        mic_signals = self._apply_aop_clipping(mic_signals)

        sig_power = np.mean(mic_signals ** 2, axis=1, keepdims=True)
        noise_power = sig_power / (10.0 ** (snr_db / 10.0))
        mic_signals += np.sqrt(noise_power) * np.random.randn(*mic_signals.shape)

        return mic_signals, source_positions

    def _apply_delays_reflected_turbulent(self, source, array, fs, pos, mic_positions_world, turbulence):
        image_pos = self.ground_reflector.get_image_source(pos)
        coeff = self.ground_reflector.reflection_coefficient
        dists_direct = np.linalg.norm(mic_positions_world - pos, axis=1)
        dists_image = np.linalg.norm(mic_positions_world - image_pos, axis=1)
        n = len(source)
        n_pad = 2 ** int(np.ceil(np.log2(n + n)))
        source_pad = np.pad(source, (0, n_pad - n))
        S = np.fft.fft(source_pad)
        freqs = np.fft.fftfreq(n_pad, 1 / fs)
        result = np.zeros((array.n_mics, n))
        for m in range(array.n_mics):
            turb = turbulence[m, 0] * 0.5
            delay_img = dists_image[m] / self.speed_sound + turb
            H = np.exp(-1j * 2 * np.pi * freqs * delay_img)
            delayed = np.fft.ifft(S * H).real[:n]
            atten = coeff * dists_direct[m] / (dists_image[m] + 1e-6)
            result[m] = -atten * delayed
        return result

    def _apply_delays_stationary(self, source, array, fs, pos, turbulence=None):
        n = len(source)
        n_mics = array.n_mics
        n_pad = 2 ** int(np.ceil(np.log2(n + n)))

        source_pad = np.pad(source, (0, n_pad - n))
        S = np.fft.fft(source_pad)
        freqs = np.fft.fftfreq(n_pad, 1 / fs)

        dists = np.linalg.norm(array.positions - pos, axis=1)
        delays = dists / self.speed_sound
        attens = 1.0 / (dists + 1e-6)

        result = np.zeros((n_mics, n))
        for m in range(n_mics):
            turb = turbulence[m, 0] if turbulence is not None else 0.0
            H = np.exp(-1j * 2 * np.pi * freqs * (delays[m] + turb))
            delayed = np.fft.ifft(S * H).real[:n]
            result[m] = attens[m] * delayed

        return result
