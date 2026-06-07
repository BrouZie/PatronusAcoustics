import numpy as np
from scipy.signal import butter, lfilter, sosfilt

from .trajectory import make_trajectory

# Attempt to load C++ accelerated propagation routines
try:
    from . import _propagate
    _HAS_CPP = True
except ImportError:
    _HAS_CPP = False


class DroneSource:
    def __init__(self, config, absorption=None, refraction=None,
                 scintillation_enabled=False, scintillation_strength=0.1,
                 temperature_C=20.0, pressure_kPa=101.325,
                 wind_speed_ms=0.0, wind_direction_deg=0.0):
        self.rpm = config.rpm
        self.num_blades = config.num_blades
        self.bpf = (config.rpm * config.num_blades) / 60.0
        self.num_rotors = config.num_rotors
        self.bpf_harmonics = getattr(config, 'bpf_harmonics', 6)
        self.speed_sound = 343.0

        self.trajectory = make_trajectory(config)
        self.ground_reflector = None
        self.mic_positions_world = None
        self.mic = getattr(config, 'mic', None)

        self.absorption = absorption
        self.refraction = refraction
        self.scintillation_enabled = scintillation_enabled
        self.scintillation_strength = scintillation_strength
        self.temperature_C = temperature_C
        self.pressure_kPa = pressure_kPa
        self.wind_speed_ms = wind_speed_ms
        self.wind_direction_deg = wind_direction_deg

    def get_position(self, t):
        return self.trajectory.get_position(t)

    def set_absorption(self, absorption):
        self.absorption = absorption

    def _generate_source_signal(self, n_samples, fs):
        t = np.arange(n_samples) / fs

        signal = np.zeros(n_samples)
        for k in range(1, self.bpf_harmonics + 1):
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

    def _generate_scintillation(self, n_samples, fs, n_mics):
        if not self.scintillation_enabled:
            return np.ones((n_mics, n_samples))
        dt = 1.0 / fs
        tau_c = 0.05
        theta = 1.0 / tau_c
        a = 1.0 - theta * dt
        sigma = self.scintillation_strength
        b = sigma * np.sqrt(2 * theta * dt)
        chi = np.zeros((n_mics, n_samples))
        chi[:, 0] = np.random.randn(n_mics) * sigma
        innovations = np.random.randn(n_mics, n_samples - 1) * b
        zi = a * chi[:, 0:1]
        chi[:, 1:], _ = lfilter([1.0], [1.0, -a], innovations, axis=1, zi=zi)
        return np.exp(chi)

    def _apply_absorption_filter(self, S, freqs, distances):
        """Apply atmospheric absorption in frequency domain (per-mic).

        Parameters
        ----------
        S : ndarray
            FFT of source signal, shape (n_pad,).
        freqs : ndarray
            Frequency bins, shape (n_pad,).
        distances : ndarray
            Distance to each mic, shape (n_mics,).

        Returns
        -------
        S_abs : ndarray
            Absorption-filtered FFT, shape (n_mics, n_pad).
        """
        n_mics = len(distances)
        n_pad = len(S)

        if self.absorption is None:
            S_abs = np.empty((n_mics, n_pad), dtype=complex)
            S_abs[:] = S
            return S_abs

        S_abs = np.zeros((n_mics, n_pad), dtype=complex)
        for m in range(n_mics):
            H_abs = self.absorption.pressure_filter(np.abs(freqs), distances[m])
            S_abs[m] = S * H_abs
        return S_abs

    def _apply_refraction_filter(self, S, freqs, distances, source_pos):
        """Apply refraction excess attenuation in frequency domain (per-mic).

        Parameters
        ----------
        S : ndarray
            Absorption-filtered FFT, shape (n_mics, n_pad).
        freqs : ndarray
            Frequency bins, shape (n_pad,).
        distances : ndarray
            Distance to each mic, shape (n_mics,).
        source_pos : ndarray
            Source position, shape (3,).

        Returns
        -------
        S_refr : ndarray
            Refraction-filtered FFT, shape (n_mics, n_pad).
        """
        if self.refraction is None:
            return S

        n_mics = len(distances)
        n_pad = S.shape[1]
        source_height = source_pos[2]
        u_ref = self.wind_speed_ms

        # Wind direction relative to source-to-receiver propagation
        wind_az = np.deg2rad(self.wind_direction_deg)
        wind_vec = np.array([np.sin(wind_az), np.cos(wind_az), 0.0])
        src_dir = source_pos / (np.linalg.norm(source_pos) + 1e-10)
        cos_theta = np.dot(src_dir, wind_vec)

        S_refr = S.copy()
        mic_pos = (self.mic_positions_world if
                   (self.ground_reflector is not None and
                    self.mic_positions_world is not None)
                   else None)

        for m in range(n_mics):
            recv_height = mic_pos[m, 2] if mic_pos is not None else 0.0
            excess_db = self.refraction.excess_attenuation(
                source_height, recv_height, distances[m],
                T0_C=self.temperature_C, u_ref=u_ref,
                cos_theta=cos_theta,
                frequencies=np.abs(freqs),
            )
            excess_db = np.asarray(excess_db, dtype=float)
            H_refr = 10.0 ** (-excess_db / 20.0)
            S_refr[m] *= H_refr

        return S_refr

    def _propagate_stationary(self, source, array, fs, pos, turbulence):
        n = len(source)
        n_mics = array.n_mics
        n_pad = 2 ** int(np.ceil(np.log2(n + n)))

        source_pad = np.pad(source, (0, n_pad - n))
        S = np.fft.fft(source_pad)
        freqs = np.fft.fftfreq(n_pad, 1 / fs)

        mic_pos = (self.mic_positions_world if
                   (self.ground_reflector is not None and
                    self.mic_positions_world is not None)
                   else array.positions)
        dists = np.linalg.norm(mic_pos - pos, axis=1)
        delays = dists / self.speed_sound
        attens = 1.0 / (dists + 1e-6)

        S_filt = self._apply_absorption_filter(S, freqs, dists)
        S_filt = self._apply_refraction_filter(S_filt, freqs, dists, pos)

        result = np.zeros((n_mics, n))
        for m in range(n_mics):
            turb = turbulence[m, 0] if turbulence is not None else 0.0
            H = np.exp(-1j * 2 * np.pi * freqs * (delays[m] + turb))
            filtered = np.fft.ifft(S_filt[m] * H).real[:n]
            result[m] = attens[m] * filtered
        return result

    def _propagate_reflected(self, source, array, fs, pos, turbulence):
        """Propagate ground-reflected path (stationary source, FFT-based)."""
        image_pos = self.ground_reflector.get_image_source(pos)
        mic_pos = self.mic_positions_world
        n = len(source)
        n_mics = array.n_mics
        n_pad = 2 ** int(np.ceil(np.log2(n + n)))

        source_pad = np.pad(source, (0, n_pad - n))
        S = np.fft.fft(source_pad)
        freqs = np.fft.fftfreq(n_pad, 1 / fs)

        dists_direct = np.linalg.norm(mic_pos - pos, axis=1)
        dists_image = np.linalg.norm(mic_pos - image_pos, axis=1)

        S_ref = self._apply_absorption_filter(S, freqs, dists_image)

        result = np.zeros((n_mics, n))
        for m in range(n_mics):
            turb = turbulence[m, 0] * 0.5 if turbulence is not None else 0.0
            delay_img = dists_image[m] / self.speed_sound + turb

            R = self.ground_reflector.reflection_coefficient
            if self.ground_reflector.model != "constant":
                cos_theta_i = abs(mic_pos[m, 2] - image_pos[2]) / (dists_image[m] + 1e-6)
                theta_i = np.arccos(np.clip(cos_theta_i, 0.0, 1.0))
                R = self.ground_reflector.get_reflection_coefficient(
                    np.abs(freqs), theta_i
                )

            if np.isscalar(R):
                H = np.exp(-1j * 2 * np.pi * freqs * delay_img)
                filtered = np.fft.ifft(S_ref[m] * H).real[:n]
            else:
                H = np.exp(-1j * 2 * np.pi * freqs * delay_img)
                filtered = np.fft.ifft(S_ref[m] * R * H).real[:n]

            atten = abs(R if not np.isscalar(R) else R) * dists_direct[m] / (dists_image[m] + 1e-6)
            result[m] = -atten * filtered
        return result

    def _propagate_moving_per_sample(self, source, array, fs, positions, turbulence):
        """Propagate a moving source using per-sample linear interpolation.

        Returns signals with 1/r attenuation + delays but WITHOUT absorption.
        """
        n = len(source)
        n_mics = array.n_mics

        mic_pos = (self.mic_positions_world if
                   (self.ground_reflector is not None and
                    self.mic_positions_world is not None)
                   else array.positions)

        if _HAS_CPP:
            return _propagate.propagate_moving(
                source, mic_pos, positions, fs, self.speed_sound, turbulence
            )

        # Pure-Python fallback (no _cpp extension)
        result = np.zeros((n_mics, n))
        for i in range(min(n, len(positions))):
            pos = positions[i]
            dists = np.linalg.norm(mic_pos - pos, axis=1)

            for m in range(n_mics):
                turb = turbulence[m, i] if turbulence is not None else 0.0
                atten = 1.0 / (dists[m] + 1e-6)
                delay_samp = (dists[m] / self.speed_sound + turb) * fs
                idx_float = i - delay_samp
                idx_int = int(np.floor(idx_float))
                frac = idx_float - idx_int
                if 0 <= idx_int < n - 1:
                    result[m, i] = atten * (
                        (1 - frac) * source[idx_int] + frac * source[idx_int + 1]
                    )
        return result

    def _propagate_reflected_moving_per_sample(self, source, array, fs, positions, turbulence):
        """Propagate ground-reflected path (moving source, per-sample)."""
        n = len(source)
        n_mics = array.n_mics
        mic_pos = self.mic_positions_world
        R_scalar = self.ground_reflector.reflection_coefficient

        if _HAS_CPP and self.ground_reflector.model == "constant":
            # Pre-compute all image positions in one vectorized call
            height = self.ground_reflector.height_m
            image_positions = positions.copy()
            image_positions[:, 2] = -(positions[:, 2] + 2 * height)

            return _propagate.propagate_reflected_moving(
                source, mic_pos, positions, image_positions,
                fs, self.speed_sound, turbulence, R_scalar,
            )

        # Pure-Python fallback
        result = np.zeros((n_mics, n))
        for i in range(min(n, len(positions))):
            pos = positions[i]
            image_pos = self.ground_reflector.get_image_source(pos)
            dists_direct = np.linalg.norm(mic_pos - pos, axis=1)
            dists_image = np.linalg.norm(mic_pos - image_pos, axis=1)

            for m in range(n_mics):
                turb = turbulence[m, i] * 0.5 if turbulence is not None else 0.0
                delay_img = dists_image[m] / self.speed_sound + turb

                if self.ground_reflector.model != "constant":
                    cos_theta_i = abs(mic_pos[m, 2] - image_pos[2]) / (dists_image[m] + 1e-6)
                    theta_i = np.arccos(np.clip(cos_theta_i, 0.0, 1.0))
                    R = self.ground_reflector.get_reflection_coefficient(
                        np.array([self.bpf * k for k in range(1, self.bpf_harmonics + 1)]),
                        theta_i
                    )
                    R = float(np.mean(np.abs(R)))
                    R_use = R
                else:
                    R_use = R_scalar

                atten = R_use * dists_direct[m] / (dists_image[m] + 1e-6)
                delay_samp = delay_img * fs
                idx_float = i - delay_samp
                idx_int = int(np.floor(idx_float))
                frac = idx_float - idx_int
                if 0 <= idx_int < n - 1:
                    result[m, i] = -atten * (
                        (1 - frac) * source[idx_int] + frac * source[idx_int + 1]
                    )
        return result

    def _apply_absorption_ola(self, mic_signals, fs, distances,
                               source_positions=None):
        if self.absorption is None and self.refraction is None:
            return mic_signals

        n_mics, n = mic_signals.shape
        block_size = 2048
        hop = block_size // 2
        window = np.hanning(block_size)

        freqs = np.fft.rfftfreq(block_size, 1 / fs)

        alpha = None
        if self.absorption is not None:
            alpha = self.absorption.coefficient(freqs)

        if _HAS_CPP and self.refraction is None:
            return _propagate.apply_absorption_ola(
                mic_signals, distances, fs, alpha,
                block_size, hop, window
            )

        n_freq = len(freqs)
        u_ref = self.wind_speed_ms
        wind_az = np.deg2rad(self.wind_direction_deg)
        wind_vec = np.array([np.sin(wind_az), np.cos(wind_az), 0.0])

        output = np.zeros_like(mic_signals)
        overlap_cnt = np.zeros(n)

        for start in range(0, n - block_size + 1, hop):
            end = start + block_size
            center = start + block_size // 2
            d = distances[:, center]

            S = np.fft.rfft(mic_signals[:, start:end] * window[None, :])
            H_total = np.ones((n_mics, n_freq), dtype=float)

            if alpha is not None:
                H_total *= np.exp(-alpha[None, :] * d[:, None] / 8.686)

            if self.refraction is not None and source_positions is not None:
                src_pos = source_positions[center]
                src_height = src_pos[2]
                src_dir = src_pos / (np.linalg.norm(src_pos) + 1e-10)
                cos_theta = np.dot(src_dir, wind_vec)
                mic_pos = (self.mic_positions_world if
                           (self.ground_reflector is not None and
                            self.mic_positions_world is not None)
                           else None)
                for m in range(n_mics):
                    recv_h = mic_pos[m, 2] if mic_pos is not None else 0.0
                    excess = self.refraction.excess_attenuation(
                        src_height, recv_h, d[m],
                        T0_C=self.temperature_C, u_ref=u_ref,
                        cos_theta=cos_theta,
                        frequencies=freqs,
                    )
                    H_total[m] *= 10.0 ** (-np.asarray(excess, dtype=float) / 20.0)

            out_block = np.fft.irfft(S * H_total, n=block_size)
            output[:, start:end] += out_block
            overlap_cnt[start:end] += 1.0

        for m in range(n_mics):
            output[m] /= (overlap_cnt + 1e-10)

        return output

    def generate_mic_signals(self, array, fs, duration, snr_db=None):
        n_samples = int(duration * fs)
        n_mics = array.n_mics
        t = np.arange(n_samples) / fs

        source = self._generate_source_signal(n_samples, fs)
        source_positions = np.zeros((n_samples, 3))

        turbulence = self._generate_turbulence(n_samples, fs, n_mics)
        scintillation = self._generate_scintillation(n_samples, fs, n_mics)

        has_ground_reflection = (
            self.ground_reflector is not None
            and self.mic_positions_world is not None
        )

        if self.trajectory.is_stationary:
            pos = self.trajectory.get_position(0)
            source_positions[:] = pos
            mic_signals = self._propagate_stationary(source, array, fs, pos, turbulence)
            if has_ground_reflection:
                mic_signals += self._propagate_reflected(
                    source, array, fs, pos, turbulence
                )
        else:
            for i in range(n_samples):
                source_positions[i] = self.trajectory.get_position(t[i])

            mic_signals = self._propagate_moving_per_sample(
                source, array, fs, source_positions, turbulence
            )
            if has_ground_reflection:
                mic_signals += self._propagate_reflected_moving_per_sample(
                    source, array, fs, source_positions, turbulence
                )

            mic_pos = (self.mic_positions_world if has_ground_reflection
                       else array.positions)
            dists = np.linalg.norm(
                mic_pos[:, None, :] - source_positions[None, :, :], axis=-1
            )
            mic_signals = self._apply_absorption_ola(mic_signals, fs, dists,
                                                       source_positions=source_positions)

        mic_signals *= scintillation
        mic_signals = self._apply_aop_clipping(mic_signals)

        if snr_db is not None:
            sig_power = np.mean(mic_signals ** 2, axis=1, keepdims=True)
            noise_power = sig_power / (10.0 ** (snr_db / 10.0))
            mic_signals += np.sqrt(noise_power) * np.random.randn(*mic_signals.shape)

        return mic_signals, source_positions


