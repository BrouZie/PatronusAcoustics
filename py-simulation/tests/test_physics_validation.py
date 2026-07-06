"""Known-answer physics validation.

Each test pins the simulation to an external reference (ISO tables, plane-wave
geometry, aperture scaling laws) so the numbers the geometry decision rests on
can be trusted — and so refactors that silently change physics fail loudly.
"""

import unittest

import numpy as np

from src.absorption import AtmosphericAbsorption
from src.beampattern import array_response
from src.config import DualRingArrayConfig, SingleRingArrayConfig
from src.constants import SPEED_OF_SOUND_REF, speed_of_sound
from src.geometry import DualRingArray, SingleRingArray, direction_vectors
from src.srpphat import SRPPhatProcessor


class TestSpeedOfSound(unittest.TestCase):
    def test_reference_values(self):
        self.assertAlmostEqual(speed_of_sound(20.0), 343.2, delta=0.3)
        self.assertAlmostEqual(speed_of_sound(0.0), 331.3, delta=0.2)
        self.assertAlmostEqual(SPEED_OF_SOUND_REF, 343.0)


class TestIso9613Absorption(unittest.TestCase):
    """Anchors from the ISO 9613-1 table at 20 °C, 70 % RH, 1 atm.

    Bands are generous (±~35%) — they catch unit errors (dB/m vs dB/km,
    h in percent vs fraction) and broken frequency dependence, not
    last-digit differences."""

    def setUp(self):
        self.a = AtmosphericAbsorption(20.0, 70.0, 101.325)

    def _alpha_db_per_km(self, f):
        return float(self.a.coefficient(np.array([f]))[0]) * 1000.0

    def test_low_frequency_anchor(self):
        self.assertLess(self._alpha_db_per_km(125.0), 0.7)
        self.assertGreater(self._alpha_db_per_km(125.0), 0.15)

    def test_1khz_anchor(self):
        alpha = self._alpha_db_per_km(1000.0)
        self.assertGreater(alpha, 3.0)
        self.assertLess(alpha, 7.0)

    def test_4khz_anchor(self):
        alpha = self._alpha_db_per_km(4000.0)
        self.assertGreater(alpha, 15.0)
        self.assertLess(alpha, 35.0)

    def test_monotonic_in_frequency(self):
        freqs = np.array([100.0, 250.0, 500.0, 1000.0, 2000.0, 4000.0, 8000.0])
        alphas = self.a.coefficient(freqs)
        self.assertTrue(np.all(np.diff(alphas) > 0))

    def test_relaxation_frequencies_in_physical_range(self):
        # Oxygen relaxation: tens of kHz; nitrogen: hundreds of Hz at 20 °C.
        self.assertGreater(self.a._f_rO, 10_000.0)
        self.assertLess(self.a._f_rO, 200_000.0)
        self.assertGreater(self.a._f_rN, 100.0)
        self.assertLess(self.a._f_rN, 2000.0)


class TestSteeringTdoaConsistency(unittest.TestCase):
    def test_far_field_limit(self):
        """TDOA to a distant source equals -(steering delay), up to a
        common offset."""
        array = DualRingArray(DualRingArrayConfig())
        az, el = np.radians(35.0), np.radians(50.0)
        u = direction_vectors(np.array([[az]]), np.array([[el]]))[0]

        steer = array.get_steering_delays(u.reshape(1, 3)).ravel()
        tdoa = array.get_tdoa(u * 5000.0)

        steer_rel = steer - steer.mean()
        tdoa_rel = tdoa - tdoa.mean()
        np.testing.assert_allclose(tdoa_rel, -steer_rel, atol=2e-8)


class TestSrpPhatKnownAnswer(unittest.TestCase):
    def _make_processor(self, res_deg=5.0):
        from src.config import SearchConfig, DetectionConfig
        array = DualRingArray(DualRingArrayConfig())
        search = SearchConfig(azimuth_range=[-60, 60],
                              elevation_range=[0.1, 60],
                              resolution_deg=res_deg)
        return array, SRPPhatProcessor(
            array=array, fs=48000, fft_size=2048, hop_length=512,
            search_config=search, max_freq=4000.0,
            detection_config=DetectionConfig(enabled=False),
        )

    def _frame_from_direction(self, array, az, el, fs=48000, n=2048, seed=0):
        """Broadband plane wave via exact fractional delays in freq domain."""
        rng = np.random.default_rng(seed)
        source = rng.normal(size=n)
        u = direction_vectors(np.array([[az]]), np.array([[el]]))[0]
        delays = -array.get_steering_delays(u.reshape(1, 3)).ravel()
        freqs = np.fft.rfftfreq(n, 1.0 / fs)
        S = np.fft.rfft(source)
        frame = np.array([
            np.fft.irfft(S * np.exp(-2j * np.pi * freqs * d), n=n)
            for d in delays
        ])
        return frame

    def test_noise_free_peak_on_grid_direction(self):
        array, srp = self._make_processor()
        az, el = np.radians(20.0), np.radians(30.1)  # on-grid points
        # Use the exact grid values to avoid off-grid quantization.
        az = srp.az_range[np.argmin(np.abs(srp.az_range - az))]
        el = srp.el_range[np.argmin(np.abs(srp.el_range - el))]

        frame = self._frame_from_direction(array, az, el)
        result = srp.process_frame(frame)
        est_az, est_el = result["estimated_doa"]
        self.assertAlmostEqual(np.degrees(est_az), np.degrees(az), delta=1e-6)
        self.assertAlmostEqual(np.degrees(est_el), np.degrees(el), delta=1e-6)

    def test_20db_snr_within_one_cell(self):
        array, srp = self._make_processor()
        az = srp.az_range[np.argmin(np.abs(srp.az_range - np.radians(-15)))]
        el = srp.el_range[np.argmin(np.abs(srp.el_range - np.radians(40)))]

        frame = self._frame_from_direction(array, az, el, seed=1)
        rng = np.random.default_rng(2)
        noise_std = np.std(frame) * 10 ** (-20 / 20)
        frame = frame + rng.normal(scale=noise_std, size=frame.shape)

        result = srp.process_frame(frame)
        est_az, est_el = result["estimated_doa"]
        self.assertLessEqual(abs(np.degrees(est_az - az)), 5.0)
        self.assertLessEqual(abs(np.degrees(est_el - el)), 5.0)


class TestApertureScalingLaws(unittest.TestCase):
    """Beamwidth ∝ λ/D: doubling frequency or radius halves the beamwidth."""

    @staticmethod
    def _beamwidth_deg(array, freq):
        theta = np.radians(np.linspace(-90, 90, 1441))
        az = np.where(theta < 0, np.pi, 0.0).reshape(-1, 1)
        el = np.abs(theta).reshape(-1, 1)
        B = array_response(array, freq, az, el)[:, 0]
        above = np.where(B >= 0.5)[0]
        return np.degrees(theta[above[-1]] - theta[above[0]])

    def test_beamwidth_halves_with_frequency(self):
        array = SingleRingArray(SingleRingArrayConfig(radius=0.25, n_mics=16))
        ratio = self._beamwidth_deg(array, 1000.0) / self._beamwidth_deg(array, 2000.0)
        self.assertAlmostEqual(ratio, 2.0, delta=0.5)

    def test_beamwidth_shrinks_with_radius(self):
        small = SingleRingArray(SingleRingArrayConfig(radius=0.1, n_mics=16))
        large = SingleRingArray(SingleRingArrayConfig(radius=0.3, n_mics=16))
        self.assertGreater(
            self._beamwidth_deg(small, 1000.0),
            self._beamwidth_deg(large, 1000.0) * 1.5,
        )

    def test_more_mics_do_not_widen_beam(self):
        few = SingleRingArray(SingleRingArrayConfig(radius=0.25, n_mics=4))
        many = SingleRingArray(SingleRingArrayConfig(radius=0.25, n_mics=16))
        self.assertGreaterEqual(
            self._beamwidth_deg(few, 1000.0) + 1e-9,
            self._beamwidth_deg(many, 1000.0),
        )


class TestMovingSourceFidelity(unittest.TestCase):
    """Windowed-sinc fractional delay: Doppler and HF flatness anchors."""

    FS = 48000
    C = SPEED_OF_SOUND_REF

    def _propagate_tone(self, f0, positions, n):
        from src.config import DroneConfig
        from src.drone_signal import DroneSource
        from src.geometry import SingleRingArray

        t = np.arange(n) / self.FS
        source = np.sin(2 * np.pi * f0 * t)
        array = SingleRingArray(SingleRingArrayConfig(radius=0.1, n_mics=2))
        drone = DroneSource(DroneConfig(), speed_sound=self.C)
        out = drone._propagate_moving_per_sample(
            source, array, self.FS, positions, None
        )
        return out, array.positions_true

    def test_analytic_doppler_shift(self):
        # Source approaching mic 0 radially at 20 m/s: STFT peak of the
        # received tone must sit at f0 * c / (c - v) within 0.1 %.
        f0, v = 1000.0, 20.0
        n = 4 * self.FS
        t = np.arange(n) / self.FS
        positions = np.zeros((n, 3))
        positions[:, 0] = 120.0 - v * t  # x-axis approach, stays > 40 m away

        out, _ = self._propagate_tone(f0, positions, n)
        out = out[0]
        # Analyze the middle 2 s (skip fill-in and tail transients).
        seg = out[self.FS:3 * self.FS] * np.hanning(2 * self.FS)
        spec = np.abs(np.fft.rfft(seg, n=8 * len(seg)))
        freqs = np.fft.rfftfreq(8 * len(seg), 1 / self.FS)
        f_peak = freqs[np.argmax(spec)]

        f_expected = f0 * self.C / (self.C - v)
        self.assertAlmostEqual(
            f_peak / f_expected, 1.0, delta=1e-3,
            msg=f"Doppler peak {f_peak:.2f} Hz, expected {f_expected:.2f} Hz",
        )

    def test_high_frequency_amplitude_flat(self):
        # A 6 kHz tone through the moving-source path at a worst-case
        # half-sample fractional delay must keep its amplitude within
        # 0.5 dB (the old 2-tap linear interpolator lost ~0.7 dB here).
        f0 = 6000.0
        n = self.FS
        positions = np.zeros((n, 3))
        positions[:, 0] = 30.0

        out, mic_pos = self._propagate_tone(f0, positions, n)
        # Undo 1/r with the true source-to-mic distance (the mic sits on
        # the ring, not at the origin).
        dist = float(np.linalg.norm(positions[0] - mic_pos[0]))
        seg = out[0, self.FS // 4: 3 * self.FS // 4]
        amp = np.sqrt(2.0) * np.std(seg) * dist
        loss_db = 20 * np.log10(max(amp, 1e-12))
        self.assertLess(abs(loss_db), 0.5)

    def test_cpp_python_parity(self):
        # C++ extension vs the vectorized Python fallback on the exact
        # same inputs (retarded-time distances + sinc interpolation).
        from src import drone_signal as ds
        from src.config import DroneConfig
        from src.drone_signal import DroneSource
        if not ds._CPP_HAS_SINC:
            self.skipTest("C++ extension without sinc support")

        class _StubArray:
            def __init__(self, positions):
                self.positions_true = positions
                self.n_mics = len(positions)

        rng = np.random.default_rng(11)
        n = 8000
        source = rng.standard_normal(n)
        mic_pos = rng.standard_normal((3, 3)) * 0.3
        positions = np.zeros((n, 3))
        positions[:, 0] = 15.0 - 5.0 * np.arange(n) / n
        turb = rng.standard_normal((3, n)) * 1e-5

        drone = DroneSource(DroneConfig(), speed_sound=self.C)
        array = _StubArray(mic_pos)

        cpp = drone._propagate_moving_per_sample(
            source, array, self.FS, positions, turb)
        ds._CPP_HAS_SINC = False
        try:
            py_out = drone._propagate_moving_per_sample(
                source, array, self.FS, positions, turb)
        finally:
            ds._CPP_HAS_SINC = True
        np.testing.assert_allclose(cpp, py_out, atol=1e-10)


class TestCramerSpeedOfSound(unittest.TestCase):
    """Cramer (1993) anchors; legacy dry formula preserved bit-for-bit."""

    def test_zero_c_dry_anchor(self):
        # Published value at 0 °C, 0 % RH, 101.325 kPa, 400 ppm CO2.
        self.assertAlmostEqual(
            speed_of_sound(0.0, humidity_pct=0.0), 331.45, delta=0.05)

    def test_20c_50rh_anchor(self):
        self.assertAlmostEqual(
            speed_of_sound(20.0, humidity_pct=50.0), 344.0, delta=0.1)

    def test_humidity_increases_speed(self):
        self.assertGreater(speed_of_sound(20.0, humidity_pct=100.0),
                           speed_of_sound(20.0, humidity_pct=0.0))

    def test_legacy_dry_path_unchanged(self):
        import math
        for t in (-10.0, 0.0, 20.0, 35.0):
            self.assertEqual(speed_of_sound(t),
                             331.3 * math.sqrt(1.0 + t / 273.15))


class TestAbsoluteCalibration(unittest.TestCase):
    """Pa-referenced anchors: EIN floor, source SPL, wind level, SNR."""

    def test_silent_scene_floor_is_ein(self):
        from src.config import Config
        from src.constants import pa_to_spl
        from src.sensor import SensorModel

        np.random.seed(0)
        cfg = Config()  # ICS-52000: SNR 65 dBA → EIN = 94 − 65 = 29 dB SPL
        sensor = SensorModel(cfg.mic, 4, 48000)
        out = sensor.apply(np.zeros((4, 48000)), absolute=True)
        floor_db = pa_to_spl(float(np.std(out)) / sensor.fs_per_pa)
        self.assertAlmostEqual(floor_db, 29.0, delta=1.0)

    def test_drone_spl_at_distance(self):
        from src.config import Config
        from src.constants import pa_to_spl
        from src.simulation import Simulation

        cfg = Config.from_dict({
            "signal": {"duration": 1.0, "seed": 1, "drone_spl_db": 73.0},
            "drone": {"distance": 30.0},
        })
        sim = Simulation(cfg)
        sig, _ = sim.drone.generate_mic_signals(sim.array, 48000, 1.0)
        measured = pa_to_spl(float(np.std(sig)))
        expected = 73.0 - 20 * np.log10(30.0)
        self.assertAlmostEqual(measured, expected, delta=1.0)

    def test_bare_mic_wind_level_anchor(self):
        # Strasberg-style dynamic-pressure scaling: 5 m/s bare mic lands
        # in the published ~95-100 dB SPL band.
        from src.constants import pa_to_spl
        from src.environment import WindSource

        np.random.seed(2)
        pos = np.random.randn(4, 3) * 0.2
        ws = WindSource(5.0, 0.0, 48000, 4, 48000, np.zeros(3),
                        calibrated=True)
        level = pa_to_spl(float(np.std(ws.generate(pos))))
        self.assertGreater(level, 92.0)
        self.assertLess(level, 102.0)

    def test_effective_snr_matches_measured(self):
        # The closed-form budget must agree with the measured Pa-domain
        # SNR (signal RMS vs EIN floor) within 1.5 dB, environment off.
        from src.config import Config
        from src.sensor import SensorModel, effective_snr_db
        from src.simulation import Simulation

        cfg = Config.from_dict({
            "signal": {"duration": 1.0, "seed": 3, "drone_spl_db": 73.0},
            "drone": {"distance": 30.0},
        })
        predicted = effective_snr_db(cfg)
        sim = Simulation(cfg)
        sig, _ = sim.drone.generate_mic_signals(sim.array, 48000, 1.0)
        sensor = SensorModel(cfg.mic, sig.shape[0], 48000)
        measured = 20 * np.log10(float(np.std(sig)) / sensor.ein_pa)
        self.assertAlmostEqual(measured, predicted, delta=1.5)


class TestPerRotorSource(unittest.TestCase):
    def test_rotor_spread_produces_beating(self):
        from src.config import DroneConfig
        from src.drone_signal import DroneSource
        from scipy.signal import butter, hilbert, sosfilt

        np.random.seed(3)
        fs, dur = 48000, 4
        src = DroneSource(DroneConfig())  # 4 rotors, 2 % spread
        sig = src._generate_source_signal(fs * dur, fs)
        sos = butter(4, [180 / (fs / 2), 220 / (fs / 2)], btype="band",
                     output="sos")
        env = np.abs(hilbert(sosfilt(sos, sig)))
        depth = float(np.std(env) / np.mean(env))
        self.assertGreater(depth, 0.2)  # beating, not a steady tone

    def test_single_identical_rotor_is_steady(self):
        from src.config import DroneConfig
        from src.drone_signal import DroneSource
        from scipy.signal import butter, hilbert, sosfilt

        np.random.seed(3)
        fs, dur = 48000, 4
        cfg = DroneConfig(num_rotors=1, rpm_spread_pct=0.0,
                          rpm_jitter_pct=0.0)
        src = DroneSource(cfg)
        sig = src._generate_source_signal(fs * dur, fs)
        sos = butter(4, [180 / (fs / 2), 220 / (fs / 2)], btype="band",
                     output="sos")
        env = np.abs(hilbert(sosfilt(sos, sig)))
        mid = env[fs // 2: -fs // 2]
        depth = float(np.std(mid) / np.mean(mid))
        self.assertLess(depth, 0.2)
