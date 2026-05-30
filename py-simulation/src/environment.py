import numpy as np
from scipy.signal import butter, sosfilt

from .absorption import AtmosphericAbsorption
from .refraction import RefractionModel

try:
    from . import _noise
    _HAS_CPP_NOISE = True
except ImportError:
    _HAS_CPP_NOISE = False

RHO0 = 1.2
C0 = 343.0


class GroundReflector:
    def __init__(self, height_m, reflection_coefficient,
                 model="constant", flow_resistivity=200000.0):
        self.height_m = height_m
        self.reflection_coefficient = reflection_coefficient
        self.model = model
        self.flow_resistivity = flow_resistivity
        self._cache = {}

    def get_image_source(self, drone_pos):
        x, y, z = drone_pos
        return np.array([x, y, -(z + 2 * self.height_m)])

    def get_reflection_coefficient(self, f, theta_i):
        """Frequency- and angle-dependent reflection coefficient.

        Parameters
        ----------
        f : ndarray
            Frequencies in Hz.
        theta_i : float
            Incidence angle from the normal (radians).

        Returns
        -------
        R : ndarray
            Complex reflection coefficient.
        """
        if self.model == "constant":
            return np.full_like(f, self.reflection_coefficient, dtype=complex)

        if self.model == "delany_bazley":
            sigma = self.flow_resistivity
            f = np.asarray(f, dtype=float)
            E = np.where(f > 0, RHO0 * f / sigma, 1e-15)
            E = np.maximum(E, 1e-15)

            Z = 1.0 + 0.0571 * E ** (-0.754) + 1j * 0.0871 * E ** (-0.732)

            cos_theta = np.cos(theta_i)
            R = (Z * cos_theta - 1.0) / (Z * cos_theta + 1.0)
            R[~np.isfinite(R)] = 1.0
            return R

        return np.full_like(f, self.reflection_coefficient, dtype=complex)


class DirectionalNoiseSource:
    speed_sound = 343.0

    def __init__(self, position, fs, n_mics, n_samples):
        self.position = np.array(position, dtype=float)
        self.fs = fs
        self.n_mics = n_mics
        self.n_samples = n_samples

    def _generate(self):
        raise NotImplementedError

    def _colored_noise(self, n, exponent=2.0):
        white = np.random.randn(n)
        freq = np.fft.rfftfreq(n, 1.0 / self.fs)
        freq[0] = freq[1] if len(freq) > 1 else 1.0
        scaling = 1.0 / (freq ** (exponent / 2.0))
        S = np.fft.rfft(white) * scaling
        colored = np.fft.irfft(S, n=n)
        return colored / (np.std(colored) + 1e-10)

    def propagate(self, mic_positions):
        signal = self._generate()
        n = len(signal)
        n_pad = 2 ** int(np.ceil(np.log2(n + n)))
        signal_pad = np.pad(signal, (0, n_pad - n))
        S = np.fft.fft(signal_pad)
        freqs = np.fft.fftfreq(n_pad, 1 / self.fs)

        dists = np.linalg.norm(mic_positions - self.position, axis=1)
        delays = dists / self.speed_sound
        attens = 1.0 / (dists + 1e-6)

        result = np.zeros((self.n_mics, n))
        for m in range(self.n_mics):
            H = np.exp(-1j * 2 * np.pi * freqs * delays[m])
            result[m] = attens[m] * np.fft.ifft(S * H).real[:n]
        return result


class WindSource:
    def __init__(self, speed_ms, direction_deg, fs, n_mics, n_samples, array_center):
        self.speed_ms = speed_ms
        self.direction_deg = direction_deg
        self.fs = fs
        self.n_mics = n_mics
        self.n_samples = n_samples
        self.array_center = np.array(array_center, dtype=float)
        self.alpha = 0.15  # Corcos constant

    def generate(self, mic_positions):
        n = self.n_samples
        n_pad = 2 ** int(np.ceil(np.log2(2 * n)))
        n_mics = self.n_mics

        freqs = np.fft.fftfreq(n_pad, 1 / self.fs)
        pos_idx = np.where(freqs > 0)[0]

        # Mic pairwise distances (for coherence)
        dists = np.zeros((n_mics, n_mics))
        for i in range(n_mics):
            for j in range(n_mics):
                dists[i, j] = np.linalg.norm(mic_positions[i] - mic_positions[j])

        # Spectral envelope: brown noise (1/f) with LPF at 500 Hz
        env = np.ones(n_pad, dtype=float)
        f_pos = freqs[pos_idx]
        env_pos = 1.0 / np.maximum(f_pos, 1.0)
        env_pos /= np.sqrt(1.0 + (f_pos / 500.0) ** 2)
        env[pos_idx] = env_pos
        env[freqs == 0] = env[pos_idx[0]]
        for idx in np.where(freqs < 0)[0]:
            env[idx] = env[n_pad - idx]

        # Generate spectrum for each mic
        X_fft = np.zeros((n_mics, n_pad), dtype=complex)

        # DC (real-valued)
        X_fft[:, 0] = np.random.randn(n_mics) * env[0]

        # Nyquist (real-valued, if even length)
        nyq = n_pad // 2
        if n_pad % 2 == 0:
            X_fft[:, nyq] = np.random.randn(n_mics) * env[nyq]

        U = max(self.speed_ms, 0.1)

        if _HAS_CPP_NOISE:
            _noise.generate_wind_frequencies(
                np.ascontiguousarray(dists, dtype=np.float64),
                np.ascontiguousarray(freqs, dtype=np.float64),
                np.ascontiguousarray(env, dtype=np.float64),
                np.ascontiguousarray(pos_idx, dtype=np.int64),
                self.alpha, U, n_mics,
                np.random.randint(0, 2**32, dtype=np.int64),
                X_fft,
            )
        else:
            for idx in pos_idx:
                f = freqs[idx]
                Gamma = np.exp(-self.alpha * f * dists / U)
                Gamma += 1e-8 * np.eye(n_mics)
                try:
                    L = np.linalg.cholesky(Gamma)
                except np.linalg.LinAlgError:
                    L = np.eye(n_mics)
                Z = (np.random.randn(n_mics) + 1j * np.random.randn(n_mics)) / np.sqrt(2)
                X_fft[:, idx] = L @ Z * env[idx]

        # Negative frequencies (conjugate symmetric) — vectorised numpy
        neg_cols = (n_pad - pos_idx).astype(int)
        X_fft[:, neg_cols] = np.conj(X_fft[:, pos_idx])

        result = np.fft.ifft(X_fft, axis=1).real[:, :n]
        gain = self.speed_ms * 0.008
        return gain * result / (np.std(result) + 1e-10)


class TrafficSource(DirectionalNoiseSource):
    def __init__(self, density, direction_deg, fs, n_mics, n_samples, array_center):
        dist = 50.0
        az_rad = np.deg2rad(direction_deg)
        pos = array_center + np.array([
            dist * np.cos(az_rad),
            dist * np.sin(az_rad),
            0.0,
        ])
        super().__init__(pos, fs, n_mics, n_samples)
        density_factors = {"light": 0.02, "moderate": 0.05, "heavy": 0.10}
        self.amp = density_factors.get(density, 0.0)

    def _generate(self):
        sos = butter(4, [200 / (self.fs / 2), 2000 / (self.fs / 2)], btype="band", output="sos")
        t = np.arange(self.n_samples) / self.fs
        mod = 1.0 + 0.5 * np.sin(2 * np.pi * 0.1 * t)
        raw = np.random.randn(self.n_samples)
        traffic = sosfilt(sos, raw)
        return self.amp * mod * traffic


class BirdSource(DirectionalNoiseSource):
    def __init__(self, activity, fs, n_mics, n_samples, array_center):
        az = np.random.uniform(-60, 60)
        el = np.random.uniform(50, 80)
        az_rad = np.deg2rad(az)
        el_rad = np.deg2rad(el)
        dist = 10.0
        pos = array_center + np.array([
            dist * np.cos(el_rad) * np.cos(az_rad),
            dist * np.cos(el_rad) * np.sin(az_rad),
            dist * np.sin(el_rad),
        ])
        super().__init__(pos, fs, n_mics, n_samples)
        self.activity = activity
        self.chirp_rate = activity * 2.0

    def _generate(self):
        signal = np.zeros(self.n_samples)
        n_chirps = np.random.poisson(self.chirp_rate * (self.n_samples / self.fs))
        for _ in range(n_chirps):
            start_s = np.random.uniform(0, self.n_samples / self.fs - 0.3)
            start = int(start_s * self.fs)
            dur = np.random.uniform(0.08, 0.25)
            length = int(dur * self.fs)
            if start + length > self.n_samples:
                continue
            f0 = np.random.uniform(2000, 4000)
            f1 = np.random.uniform(4000, 8000)
            phase = 2 * np.pi * np.cumsum(
                np.linspace(f0, f1, length) / self.fs
            )
            envelope = np.sin(np.linspace(0, np.pi, length))
            signal[start:start + length] += 0.005 * envelope * np.sin(phase)
        return signal


class AmbientSource:
    def __init__(self, ambient_db, fs, n_mics, n_samples):
        self.ambient_db = ambient_db
        self.fs = fs
        self.n_mics = n_mics
        self.n_samples = n_samples

    def generate(self):
        amp = self.ambient_db * 0.0003
        noise = np.zeros((self.n_mics, self.n_samples))
        for m in range(self.n_mics):
            pink = self._colored_noise(self.n_samples, exponent=1.0)
            noise[m] = amp * pink
        return noise

    def _colored_noise(self, n, exponent=1.0):
        white = np.random.randn(n)
        freq = np.fft.rfftfreq(n, 1.0 / self.fs)
        freq[0] = freq[1] if len(freq) > 1 else 1.0
        scaling = 1.0 / (freq ** (exponent / 2.0))
        S = np.fft.rfft(white) * scaling
        colored = np.fft.irfft(S, n=n)
        return colored / (np.std(colored) + 1e-10)


class Environment:
    def __init__(self, config, fs, n_mics, duration, array_center=None):
        self.enabled = config.enabled
        if not self.enabled:
            return
        gc = config.ground
        self.ground = GroundReflector(
            gc.height_m,
            gc.reflection_coefficient,
            model=gc.model,
            flow_resistivity=gc.flow_resistivity,
        )
        self.fs = fs
        self.n_mics = n_mics
        self.n_samples = int(duration * fs)
        self.array_center = np.zeros(3) if array_center is None else np.array(array_center)
        self.mic_positions = None

        self._wind_source = None
        self._traffic_source = None
        self._bird_source = None
        self._ambient_source = None

        self.absorption = AtmosphericAbsorption(
            temperature_C=config.atmospheric.temperature_C,
            humidity_pct=config.atmospheric.humidity_pct,
            pressure_kPa=config.atmospheric.pressure_kPa,
        )

        self.refraction = None
        if config.refraction.enabled:
            self.refraction = RefractionModel(
                wind_shear_ms_per_m=config.refraction.wind_shear_ms_per_m,
                temperature_lapse_rate=config.refraction.temperature_lapse_rate,
                roughness_length=config.refraction.roughness_length,
            )

        self.scintillation_enabled = config.turbulence.amplitude_scintillation
        self.scintillation_strength = config.turbulence.scintillation_strength

        nc = config.noise
        if nc.wind_speed_ms > 0:
            self._wind_source = WindSource(
                nc.wind_speed_ms, nc.wind_direction_deg,
                fs, n_mics, self.n_samples, self.array_center,
            )
        if nc.traffic_density != "none":
            self._traffic_source = TrafficSource(
                nc.traffic_density, nc.traffic_direction_deg,
                fs, n_mics, self.n_samples, self.array_center,
            )
        if nc.bird_activity > 0:
            self._bird_source = BirdSource(
                nc.bird_activity,
                fs, n_mics, self.n_samples, self.array_center,
            )
        if nc.ambient_db > 0:
            self._ambient_source = AmbientSource(
                nc.ambient_db, fs, n_mics, self.n_samples,
            )

    @property
    def has_ground(self):
        return self.enabled and self.ground.height_m > 0

    @property
    def has_noise(self):
        if not self.enabled:
            return False
        return any([
            self._wind_source is not None,
            self._traffic_source is not None,
            self._bird_source is not None,
            self._ambient_source is not None,
        ])

    def generate_noise(self, mic_positions):
        if not self.has_noise:
            return None
        self.mic_positions = mic_positions
        total = np.zeros((self.n_mics, self.n_samples))
        if self._wind_source is not None:
            total += self._wind_source.generate(mic_positions)
        if self._traffic_source is not None:
            total += self._traffic_source.propagate(mic_positions)
        if self._bird_source is not None:
            total += self._bird_source.propagate(mic_positions)
        if self._ambient_source is not None:
            total += self._ambient_source.generate()
        return total