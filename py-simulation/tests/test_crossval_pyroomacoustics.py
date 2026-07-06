"""Cross-validation of propagation physics against pyroomacoustics.

Checks that the simulator's free-field delays/spreading and single-bounce
ground reflection agree with an independent image-source implementation.
Sign convention note: our ground model inverts the reflected pressure
(pressure-release / grazing-incidence convention), pyroomacoustics' rigid
floor does not — comparisons are on magnitudes and arrival times, and the
convention difference is documented in docs/realism.md.

Skipped when pyroomacoustics is not installed (dev dependency group).
"""

import unittest

import numpy as np
import pytest

pra = pytest.importorskip("pyroomacoustics")

from src.config import DroneConfig, SingleRingArrayConfig
from src.constants import SPEED_OF_SOUND_REF
from src.drone_signal import DroneSource
from src.environment import GroundReflector
from src.geometry import SingleRingArray

FS = 48000


def _subsample_peak(x):
    """Index of max |x| with parabolic interpolation."""
    k = int(np.argmax(np.abs(x)))
    if 0 < k < len(x) - 1:
        y0, y1, y2 = np.abs(x[k - 1]), np.abs(x[k]), np.abs(x[k + 1])
        denom = y0 - 2 * y1 + y2
        if abs(denom) > 1e-30:
            return k + 0.5 * (y0 - y2) / denom
    return float(k)


def _xcorr_lag(a, b):
    """Sub-sample lag of a relative to b via cross-correlation peak."""
    n = len(a) + len(b) - 1
    nfft = 1 << (n - 1).bit_length()
    cc = np.fft.irfft(np.fft.rfft(a, nfft) * np.conj(np.fft.rfft(b, nfft)),
                      nfft)
    cc = np.roll(cc, nfft // 2)
    return _subsample_peak(cc) - nfft // 2


class TestFreeFieldAgainstPra(unittest.TestCase):
    """Anechoic: TDOAs and 1/r amplitude ratios must match."""

    def setUp(self):
        rng = np.random.default_rng(42)
        self.n = FS // 2
        self.source_signal = rng.standard_normal(self.n)
        self.array = SingleRingArray(
            SingleRingArrayConfig(radius=0.5, n_mics=4))
        self.source_pos = np.array([10.0, 4.0, 3.0])

        drone = DroneSource(DroneConfig(), speed_sound=SPEED_OF_SOUND_REF)
        self.ours = drone._propagate_stationary(
            self.source_signal, self.array, FS, self.source_pos, None)

        room = pra.AnechoicRoom(3, fs=FS)
        room.add_source(self.source_pos, signal=self.source_signal)
        room.add_microphone_array(
            pra.MicrophoneArray(self.array.positions_true.T, fs=FS))
        room.simulate()
        self.theirs = room.mic_array.signals

    def test_pairwise_tdoas_match(self):
        # pyroomacoustics default speed of sound must match ours for the
        # comparison to be meaningful.
        self.assertAlmostEqual(pra.constants.get("c"), SPEED_OF_SOUND_REF,
                               delta=0.5)
        n_cmp = self.n
        for i, j in [(0, 1), (0, 2), (0, 3), (1, 2)]:
            ours = _xcorr_lag(self.ours[i][:n_cmp], self.ours[j][:n_cmp])
            theirs = _xcorr_lag(self.theirs[i][:n_cmp],
                                self.theirs[j][:n_cmp])
            self.assertAlmostEqual(
                ours, theirs, delta=0.1,
                msg=f"TDOA mismatch pair ({i},{j}): "
                    f"ours {ours:.3f} vs pra {theirs:.3f} samples")

    def test_amplitude_ratios_follow_1_over_r(self):
        dists = np.linalg.norm(
            self.array.positions_true - self.source_pos, axis=1)
        for sig in (self.ours, self.theirs):
            for m in range(1, 4):
                ratio_db = 20 * np.log10(
                    np.std(sig[m][: self.n]) / np.std(sig[0][: self.n]))
                expected_db = 20 * np.log10(dists[0] / dists[m])
                self.assertAlmostEqual(ratio_db, expected_db, delta=0.2)


class TestGroundReflectionAgainstPra(unittest.TestCase):
    """Single floor bounce: arrival-time gap and level ratio must match.

    Geometry: GroundReflector(height_m=0) with true world-z mic positions
    makes our image identical to a floor mirror at z = 0, matching a
    pyroomacoustics ShoeBox whose five non-floor walls fully absorb.
    """

    R_AMP = 0.9
    MIC = np.array([0.0, 0.0, 1.5])
    SRC = np.array([8.0, 0.0, 4.0])

    def _our_two_path_response(self):
        n = FS // 2
        impulse = np.zeros(n)
        impulse[0] = 1.0
        array = SingleRingArray(SingleRingArrayConfig(radius=0.05, n_mics=2))
        mic_world = array.positions_true + self.MIC
        drone = DroneSource(DroneConfig(), speed_sound=SPEED_OF_SOUND_REF)
        drone.set_ground(GroundReflector(0.0, self.R_AMP, model="constant"),
                         mic_world)
        direct = drone._propagate_stationary(impulse, array, FS,
                                             self.SRC, None)
        refl = drone._propagate_reflected(impulse, array, FS, self.SRC, None)
        return (direct + refl)[0], mic_world[0]

    def _pra_two_path_rir(self, mic_pos):
        # Shift geometry into the room so the floor is the only reflector.
        offset = np.array([6.0, 5.0, 0.0])
        absorbing = pra.Material(energy_absorption=1.0)
        floor = pra.Material(energy_absorption=1.0 - self.R_AMP ** 2)
        room = pra.ShoeBox(
            [20.0, 10.0, 8.0], fs=FS, max_order=1,
            materials={
                "east": absorbing, "west": absorbing,
                "north": absorbing, "south": absorbing,
                "ceiling": absorbing, "floor": floor,
            },
        )
        room.add_source(self.SRC + offset)
        room.add_microphone(mic_pos + offset)
        room.compute_rir()
        return np.asarray(room.rir[0][0])

    def _gap_and_ratio(self, h):
        """Arrival gap (samples) and direct/reflected energy ratio (dB).

        The direct arrival is the global |peak| (RIR time origins differ
        between implementations, so nothing absolute is assumed); the
        reflection is the strongest arrival after it.
        """
        w = 12
        k_direct = _subsample_peak(h)
        k_d = int(round(k_direct))
        direct_win = h[max(k_d - w, 0): k_d + w]

        rest = h.copy()
        rest[: k_d + w] = 0.0
        k_refl = _subsample_peak(rest)

        e_direct = np.sqrt(np.sum(direct_win ** 2))
        refl_win = h[int(k_refl) - w: int(k_refl) + w]
        e_refl = np.sqrt(np.sum(refl_win ** 2))
        return k_refl - k_direct, 20 * np.log10(e_direct / e_refl)

    def test_arrival_gap_and_level_ratio(self):
        ours, mic = self._our_two_path_response()
        theirs = self._pra_two_path_rir(mic)

        d_direct = np.linalg.norm(self.SRC - mic)
        image = self.SRC * np.array([1.0, 1.0, -1.0])
        d_image = np.linalg.norm(image - mic)
        gap_expected = (d_image - d_direct) / SPEED_OF_SOUND_REF * FS
        ratio_expected = 20 * np.log10(
            (1.0 / d_direct) / (self.R_AMP / d_image))

        for label, h in (("ours", ours), ("pra", theirs)):
            gap, ratio = self._gap_and_ratio(h)
            self.assertAlmostEqual(
                gap, gap_expected, delta=0.5,
                msg=f"{label}: arrival gap {gap:.2f} vs "
                    f"{gap_expected:.2f} samples")
            self.assertAlmostEqual(
                ratio, ratio_expected, delta=0.7,
                msg=f"{label}: direct/reflected {ratio:.2f} vs "
                    f"{ratio_expected:.2f} dB")

    def test_sign_convention_differs_and_is_documented(self):
        # Ours inverts the reflected pressure (−R, pressure-release
        # convention); pyroomacoustics' floor reflects with +R. This is a
        # documented modeling choice, not an accident — this test pins it.
        ours, mic = self._our_two_path_response()
        theirs = self._pra_two_path_rir(mic)

        def reflected_peak_value(h):
            rest = h.copy()
            rest[: int(round(_subsample_peak(h))) + 12] = 0.0
            return rest[int(round(_subsample_peak(rest)))]

        self.assertLess(reflected_peak_value(ours), 0.0)
        self.assertGreater(reflected_peak_value(theirs), 0.0)
