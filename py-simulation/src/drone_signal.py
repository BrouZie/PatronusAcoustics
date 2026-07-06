import numpy as np
from scipy.signal import butter, lfilter

from .constants import EPS_DISTANCE, EPS_NORM, SPEED_OF_SOUND_REF, spl_to_pa
from .trajectory import make_trajectory

# Attempt to load C++ accelerated propagation routines
try:
    from . import _propagate
    _HAS_CPP = True
except ImportError:
    _HAS_CPP = False

# The C++ extension must implement the same windowed-sinc interpolator;
# older builds (linear interpolation) are detected and bypassed.
_CPP_HAS_SINC = _HAS_CPP and getattr(_propagate, "SINC_TAPS", 0) == 16

# Windowed-sinc fractional delay (Laakso et al. 1996, "Splitting the Unit
# Delay"): 16 taps, Kaiser β = 8.6. Values are mirrored in propagate.cpp —
# keep them in sync, including the I0 series, for bitwise parity.
SINC_TAPS = 16
KAISER_BETA = 8.6


def _i0(x):
    """Modified Bessel I0 by power series to machine precision.

    Deliberately NOT np.i0 (polynomial fit, ~1e-8 relative error): the C++
    port runs the identical series, so both paths agree to ~1e-15.
    """
    x = np.asarray(x, dtype=float)
    half2 = (x / 2.0) ** 2
    term = np.ones_like(x)
    total = np.ones_like(x)
    for k in range(1, 60):
        term = term * half2 / (k * k)
        total = total + term
        if np.all(term < 1e-18 * total):
            break
    return total


_KAISER_I0_BETA = float(_i0(np.array(KAISER_BETA)))


def _sinc_kernel(x):
    """Kaiser-windowed sinc, zero outside |x| ≤ SINC_TAPS/2."""
    half = SINC_TAPS / 2.0
    inside = np.abs(x) <= half
    arg = np.clip(1.0 - (x / half) ** 2, 0.0, None)
    window = _i0(KAISER_BETA * np.sqrt(arg)) / _KAISER_I0_BETA
    return np.where(inside, np.sinc(x) * window, 0.0)


# Fixed-point iterations for the retarded emission time t_e = t − d(t_e)/c.
# Convergence is geometric at rate v/c (< 0.1 for drones); three passes
# leave the delay exact past the (v/c)² Doppler term. Mirrored in C++.
RETARDED_TIME_ITERS = 3


def _retarded_distances(positions, mic_pos, i_idx, fs, speed_sound):
    """Per-sample source–mic distance evaluated at emission time.

    Evaluating at reception time instead loses the (v/c)² Doppler term
    (measured 3.4 Hz at 1 kHz / 20 m/s, the analytic-test tolerance).
    """
    d = np.linalg.norm(positions - mic_pos, axis=1)
    for _ in range(RETARDED_TIME_ITERS):
        t_e = i_idx - (d / speed_sound) * fs
        pos_e = np.empty_like(positions)
        for c in range(3):
            pos_e[:, c] = np.interp(t_e, i_idx, positions[:, c])
        d = np.linalg.norm(pos_e - mic_pos, axis=1)
    return d


def _fractional_delay_read(source, read_pos):
    """source sampled at fractional positions read_pos via windowed sinc.

    read_pos and the return value have the same shape; positions whose
    taps fall outside the source are treated as zero-padded.
    """
    n = len(source)
    idx_int = np.floor(read_pos).astype(np.int64)
    frac = read_pos - idx_int

    half = SINC_TAPS // 2
    offsets = np.arange(-half + 1, half + 1)          # 16 integer taps
    taps_idx = idx_int[..., None] + offsets           # (..., 16)
    x = frac[..., None] - offsets.astype(float)
    weights = _sinc_kernel(x)

    valid = (taps_idx >= 0) & (taps_idx < n)
    gathered = source[np.clip(taps_idx, 0, n - 1)]
    return np.sum(weights * gathered * valid, axis=-1)


class DroneSource:
    def __init__(self, config, absorption=None, refraction=None,
                 scintillation_enabled=False, scintillation_strength=0.1,
                 temperature_C=20.0, pressure_kPa=101.325,
                 wind_speed_ms=0.0, wind_direction_deg=0.0,
                 speed_sound=SPEED_OF_SOUND_REF,
                 turbulence_tau_std_s=15e-6, turbulence_tau_corr_s=0.05,
                 scintillation_tau_corr_s=0.05, source_spl_db=None):
        self.rpm = config.rpm
        self.num_blades = config.num_blades
        self.bpf = (config.rpm * config.num_blades) / 60.0
        self.num_rotors = config.num_rotors
        self.bpf_harmonics = getattr(config, 'bpf_harmonics', 6)
        self.rpm_spread_pct = getattr(config, 'rpm_spread_pct', 0.0)
        self.rpm_jitter_pct = getattr(config, 'rpm_jitter_pct', 0.0)
        self.rpm_jitter_corr_s = getattr(config, 'rpm_jitter_corr_s', 0.5)
        self.motor_whine_db = getattr(config, 'motor_whine_db', None)
        self.whine_multiple = getattr(config, 'whine_multiple', 14.0)
        self.speed_sound = speed_sound
        # Pa RMS at 1 m when set (calibrated path); None keeps the legacy
        # unit-std source used with the signal.snr_db override.
        self.source_spl_db = source_spl_db

        self.trajectory = make_trajectory(config)
        self.ground_reflector = None
        self.mic_positions_world = None

        self.absorption = absorption
        self.refraction = refraction
        self.scintillation_enabled = scintillation_enabled
        self.scintillation_strength = scintillation_strength
        self.turbulence_tau_std_s = turbulence_tau_std_s
        self.turbulence_tau_corr_s = turbulence_tau_corr_s
        self.scintillation_tau_corr_s = scintillation_tau_corr_s
        self.temperature_C = temperature_C
        self.pressure_kPa = pressure_kPa
        self.wind_speed_ms = wind_speed_ms
        self.wind_direction_deg = wind_direction_deg

    def get_position(self, t):
        return self.trajectory.get_position(t)

    def set_absorption(self, absorption):
        self.absorption = absorption

    def _rpm_wander(self, n_samples, fs):
        """Fractional RPM wander: Ornstein-Uhlenbeck, one path per call."""
        sigma = self.rpm_jitter_pct / 100.0
        if sigma <= 0:
            return np.zeros(n_samples)
        dt = 1.0 / fs
        theta = 1.0 / self.rpm_jitter_corr_s
        a = 1.0 - theta * dt
        b = sigma * np.sqrt(2 * theta * dt)
        x0 = np.random.randn() * sigma
        innovations = np.random.randn(n_samples - 1) * b
        out = np.empty(n_samples)
        out[0] = x0
        out[1:], _ = lfilter([1.0], [1.0, -a], innovations, zi=[a * x0])
        return out

    def _generate_source_signal(self, n_samples, fs):
        """Sum of per-rotor BPF harmonic stacks plus broadband flow noise.

        Each rotor gets its own RPM offset (fabrication/load spread) and a
        slow OU wander, so near-coincident BPFs beat against each other —
        the amplitude modulation characteristic of real multirotors. The
        total is normalized to unit std (spectrum shape and level are
        independent), then scaled to Pa when source_spl_db is set.
        """
        signal = np.zeros(n_samples)
        n_rotors = max(1, self.num_rotors)

        for _ in range(n_rotors):
            delta = (np.random.normal(0.0, self.rpm_spread_pct / 100.0)
                     if self.rpm_spread_pct > 0 else 0.0)
            bpf_r = self.bpf * (1.0 + delta)
            f_inst = bpf_r * (1.0 + self._rpm_wander(n_samples, fs))
            rotor_phase = 2 * np.pi * np.cumsum(f_inst) / fs

            for k in range(1, self.bpf_harmonics + 1):
                amp = 1.0 / k / np.sqrt(n_rotors)
                phase0 = np.random.uniform(0, 2 * np.pi)
                signal += amp * np.sin(k * rotor_phase + phase0)

            if self.motor_whine_db is not None:
                # Whine tracks shaft rate (= BPF / blades) at the pole-pass
                # order, at a level relative to the BPF fundamental.
                amp_w = 10.0 ** (self.motor_whine_db / 20.0) / np.sqrt(n_rotors)
                shaft_phase = rotor_phase / self.num_blades
                phase0 = np.random.uniform(0, 2 * np.pi)
                signal += amp_w * np.sin(self.whine_multiple * shaft_phase
                                         + phase0)

        noise = np.random.randn(n_samples)
        b, a = butter(4, 2000 / (fs / 2), btype="low")
        bb_noise = lfilter(b, a, noise)
        bb_noise *= 0.3
        signal += bb_noise

        signal /= np.std(signal)

        if self.source_spl_db is not None:
            # Pa RMS at 1 m; the 1/r pressure attenuation then yields the
            # correct SPL at every mic distance.
            signal *= spl_to_pa(self.source_spl_db)
        return signal

    def set_ground(self, ground_reflector, mic_positions_world):
        self.ground_reflector = ground_reflector
        self.mic_positions_world = mic_positions_world

    def _generate_turbulence(self, n_samples, fs, n_mics, tau_std=None, tau_corr=None):
        if tau_std is None:
            tau_std = self.turbulence_tau_std_s
        if tau_corr is None:
            tau_corr = self.turbulence_tau_corr_s
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
        tau_c = self.scintillation_tau_corr_s
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
                   else array.positions_true)
        dists = np.linalg.norm(mic_pos - pos, axis=1)
        delays = dists / self.speed_sound
        attens = 1.0 / (dists + EPS_DISTANCE)

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

            # Image-source amplitude is R/d_image (frequency-dependent R is
            # applied in the FFT; the time-domain scale must not double-
            # count it). Historical code used R·d_direct/d_image on the
            # UNattenuated source — a ~d_direct× overshoot compensated by
            # tiny reflection_coefficient values in old configs.
            H = np.exp(-1j * 2 * np.pi * freqs * delay_img)
            if np.isscalar(R):
                filtered = np.fft.ifft(S_ref[m] * H).real[:n]
                amp = R
            else:
                filtered = np.fft.ifft(S_ref[m] * R * H).real[:n]
                amp = 1.0
            result[m] = -amp / (dists_image[m] + 1e-6) * filtered
        return result

    def _propagate_moving_per_sample(self, source, array, fs, positions, turbulence):
        """Propagate a moving source using per-sample windowed-sinc delays.

        The changing propagation delay produces Doppler implicitly; the
        16-tap Kaiser sinc keeps high frequencies flat where the old 2-tap
        linear interpolator low-passed them.
        Returns signals with 1/r attenuation + delays but WITHOUT absorption.
        """
        n = len(source)
        n_mics = array.n_mics

        mic_pos = (self.mic_positions_world if
                   (self.ground_reflector is not None and
                    self.mic_positions_world is not None)
                   else array.positions_true)

        if _CPP_HAS_SINC:
            turb = (turbulence if turbulence is not None
                    else np.zeros((n_mics, n)))
            return _propagate.propagate_moving(
                source, mic_pos, positions, fs, self.speed_sound, turb
            )

        # Vectorized Python fallback (no extension, or a pre-sinc build)
        n_work = min(n, len(positions))
        i_idx = np.arange(n_work, dtype=float)
        result = np.zeros((n_mics, n))
        for m in range(n_mics):
            dists = _retarded_distances(positions[:n_work], mic_pos[m],
                                        i_idx, fs, self.speed_sound)
            turb = turbulence[m, :n_work] if turbulence is not None else 0.0
            atten = 1.0 / (dists + 1e-6)
            read_pos = i_idx - (dists / self.speed_sound + turb) * fs
            result[m, :n_work] = atten * _fractional_delay_read(source, read_pos)
        return result

    def _propagate_reflected_moving_per_sample(self, source, array, fs, positions, turbulence):
        """Propagate ground-reflected path (moving source, per-sample)."""
        n = len(source)
        n_mics = array.n_mics
        mic_pos = self.mic_positions_world
        R_scalar = self.ground_reflector.reflection_coefficient

        # Pre-compute all image positions in one vectorized call
        height = self.ground_reflector.height_m
        image_positions = positions.copy()
        image_positions[:, 2] = -(positions[:, 2] + 2 * height)

        if _CPP_HAS_SINC and self.ground_reflector.model == "constant":
            turb = (turbulence if turbulence is not None
                    else np.zeros((n_mics, n)))
            return _propagate.propagate_reflected_moving(
                source, mic_pos, positions, image_positions,
                fs, self.speed_sound, turb, R_scalar,
            )

        # Vectorized Python fallback
        n_work = min(n, len(positions))
        i_idx = np.arange(n_work, dtype=float)
        result = np.zeros((n_mics, n))
        for m in range(n_mics):
            dists_image = _retarded_distances(image_positions[:n_work],
                                              mic_pos[m], i_idx, fs,
                                              self.speed_sound)
            turb = (turbulence[m, :n_work] * 0.5 if turbulence is not None
                    else 0.0)

            if self.ground_reflector.model != "constant":
                # Frequency-averaged |R| over the BPF harmonics, per sample.
                cos_theta_i = (np.abs(mic_pos[m, 2] - image_positions[:n_work, 2])
                               / (dists_image + 1e-6))
                theta_i = np.arccos(np.clip(cos_theta_i, 0.0, 1.0))
                harmonics = np.array(
                    [self.bpf * k for k in range(1, self.bpf_harmonics + 1)])
                R_use = np.array([
                    float(np.mean(np.abs(
                        self.ground_reflector.get_reflection_coefficient(
                            harmonics, th))))
                    for th in theta_i
                ])
            else:
                R_use = R_scalar

            atten = R_use / (dists_image + 1e-6)
            read_pos = i_idx - (dists_image / self.speed_sound + turb) * fs
            result[m, :n_work] = -atten * _fractional_delay_read(source, read_pos)
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

    def generate_mic_signals(self, array, fs, duration):
        """Clean propagated mic signals (no sensor effects — see SensorModel)."""
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
                       else array.positions_true)
            dists = np.linalg.norm(
                mic_pos[:, None, :] - source_positions[None, :, :], axis=-1
            )
            mic_signals = self._apply_absorption_ola(mic_signals, fs, dists,
                                                       source_positions=source_positions)

        mic_signals *= scintillation

        return mic_signals, source_positions


