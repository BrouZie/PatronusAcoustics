"""Tests for the multi-target MCU requirements engine.

Anchors the TDM mic-ingest math to the ICS-52000 datasheet rules, pins
the log-mel uplink payload, checks that verdicts name their binding
constraints, and guards backward compatibility of the legacy H753 budget.
"""

import unittest

from pydantic import ValidationError

from src.analysis.mcu_budget import estimate
from src.analysis.mcu_profiles import (
    BUILTIN_PROFILES,
    mics_per_bus,
    required_tdm_buses,
    resolve_profiles,
)
from src.analysis.mcu_requirements import (
    compute_requirements,
    evaluate_from_config,
    evaluate_profile,
)
from src.config import Config, McuAudioIO, McuConfig, McuProfile


def _config(**mcu_overrides):
    mcu = {"enabled": True, "targets": ["stm32h753"]}
    mcu.update(mcu_overrides)
    return Config.from_dict({"mcu": mcu})


class TestTdmCapacity(unittest.TestCase):
    """ICS-52000 frame rule: n × 32 SCK, n ∈ {2,4,8,16} ≥ mics on bus."""

    h753 = BUILTIN_PROFILES["stm32h753"].audio
    esp = BUILTIN_PROFILES["esp32s3"].audio
    rt = BUILTIN_PROFILES["imxrt1176"].audio

    def test_stm32_sai_frame_limit_binds_at_48k(self):
        # 256-bit SAI frame → 8 × 32-bit slots, although the mic's SCK
        # ceiling (24.576 MHz) would allow a 16-deep chain.
        self.assertEqual(mics_per_bus(self.h753, 48000, 32, 24.576e6), 8)

    def test_stm32_sai_still_frame_limited_at_24k(self):
        # Halving fs does not help SAI: the frame-length limit is not
        # a clock limit.
        self.assertEqual(mics_per_bus(self.h753, 24000, 32, 24.576e6), 8)

    def test_esp32s3_32bit_rx_capped_at_4_slots(self):
        self.assertEqual(mics_per_bus(self.esp, 48000, 32, 24.576e6), 4)

    def test_imxrt_takes_full_chain(self):
        # 512-bit frames + 24.576 MHz SCK = the datasheet-validated
        # 16-mic chain at 48 kHz.
        self.assertEqual(mics_per_bus(self.rt, 48000, 32, 24.576e6), 16)

    def test_mic_sck_ceiling_binds_when_peripheral_is_fast(self):
        wide = McuAudioIO(n_tdm_buses=1, max_slots_per_bus=16,
                          max_frame_bits=512, max_bit_clock_hz=100e6)
        # 16 × 32 × 96 kHz = 49.2 MHz > 24.576 → drop to 8 slots.
        self.assertEqual(mics_per_bus(wide, 96000, 32, 24.576e6), 8)

    def test_returns_zero_when_nothing_fits(self):
        tiny = McuAudioIO(n_tdm_buses=1, max_slots_per_bus=16,
                          max_frame_bits=32, max_bit_clock_hz=1e6)
        self.assertEqual(mics_per_bus(tiny, 48000, 32, 24.576e6), 0)

    def test_required_buses(self):
        self.assertEqual(required_tdm_buses(16, 8), 2)
        self.assertEqual(required_tdm_buses(16, 16), 1)
        self.assertEqual(required_tdm_buses(12, 8), 2)
        self.assertIsNone(required_tdm_buses(16, 0))


class TestRequirements(unittest.TestCase):
    def test_logmel_payload_pin(self):
        # 64 mels × (48000/512) fps × 8 bit = 48 kbps payload; +20 % link.
        cfg = _config()
        req = compute_requirements(cfg, n_mics=16)
        transmit = next(s for s in req.stages if s.name == "transmit")
        self.assertAlmostEqual(transmit.link_bps, 48000 * 1.2, delta=1e-6)

    def test_logmel_disabled_drops_stages(self):
        cfg = _config(logmel={"enabled": False})
        req = compute_requirements(cfg, n_mics=16)
        self.assertEqual([s.name for s in req.stages], ["srp_phat"])
        self.assertEqual(req.link_bps, 0.0)

    def test_separate_logmel_fft_costs_more(self):
        reuse = compute_requirements(_config(), 16)
        separate = compute_requirements(
            _config(logmel={"fft_size": 1024, "hop_length": 256}), 16)
        lm_reuse = next(s for s in reuse.stages if s.name == "log_mel")
        lm_sep = next(s for s in separate.stages if s.name == "log_mel")
        self.assertGreater(lm_sep.macs_per_second, lm_reuse.macs_per_second)

    def test_headroom_scales_required_clock(self):
        base = compute_requirements(_config(headroom_pct=0), 16)
        padded = compute_requirements(_config(headroom_pct=50), 16)
        self.assertAlmostEqual(padded.required_mhz, base.required_mhz * 1.5,
                               places=6)

    def test_phase_table_matches_legacy_budget(self):
        cfg = _config()
        req = compute_requirements(cfg, n_mics=16)
        srp = next(s for s in req.stages if s.name == "srp_phat")
        legacy = estimate(
            n_mics=16, fft_size=cfg.srpphat.fft_size,
            hop_length=cfg.srpphat.hop_length, fs=cfg.signal.fs,
            n_directions=3721, max_freq=cfg.srpphat.max_freq,
        )
        # New RAM = legacy phase table + named working buffers.
        self.assertGreater(srp.ram_bytes / 2**20, legacy.phase_tensor_mb)
        self.assertLess(srp.ram_bytes / 2**20, legacy.phase_tensor_mb + 1.0)


class TestVerdicts(unittest.TestCase):
    def test_research_grid_fails_h753_names_sram(self):
        report = evaluate_from_config(_config(), n_mics=16)
        verdict = report.verdicts[0]
        self.assertFalse(verdict.fits)
        self.assertIn("SRAM", verdict.summary())
        self.assertTrue(verdict.summary().startswith("fails:"))
        self.assertIsNone(report.recommended)

    def test_esp32s3_16_mics_fails_audio_io(self):
        cfg = _config(targets=["esp32s3"])
        report = evaluate_from_config(cfg, n_mics=16)
        verdict = report.verdicts[0]
        self.assertFalse(verdict.fits_audio_io)
        self.assertIn("audio", verdict.summary())

    def test_coarse_station_grid_fits_h753(self):
        # A station-class setup: smaller FFT, 300–2000 Hz band, 12° grid.
        # 16 mics leave ~0.5 MB for the phase table on the H753, so the
        # research defaults (2048-FFT, 4 kHz, 2°) can never fit.
        cfg = Config.from_dict({
            "srpphat": {
                "fft_size": 1024,
                "max_freq": 2000.0, "min_freq": 300.0,
                "search": {"resolution_deg": 12.0},
            },
            "mcu": {"enabled": True, "targets": ["stm32h753"]},
        })
        report = evaluate_from_config(cfg, n_mics=16)
        verdict = report.verdicts[0]
        self.assertTrue(verdict.fits, verdict.summary())
        self.assertEqual(report.recommended, "stm32h753")
        self.assertTrue(verdict.summary().startswith("OK:"))

    def test_recommendation_respects_target_order(self):
        cfg = Config.from_dict({
            "srpphat": {
                "fft_size": 1024,
                "max_freq": 2000.0, "min_freq": 300.0,
                "search": {"resolution_deg": 12.0},
            },
            "mcu": {"enabled": True,
                    "targets": ["esp32s3", "imxrt1176", "stm32h753"]},
        })
        report = evaluate_from_config(cfg, n_mics=16)
        # esp32s3 fails audio I/O at 16 mics; first passing target wins.
        self.assertEqual(report.recommended, "imxrt1176")

    def test_audio_io_alone_disqualifies(self):
        profile = McuProfile(
            name="fast_but_deaf", clock_hz=2e9, macs_per_cycle=2.0,
            sram_bytes=512 * 2**20, flash_bytes=512 * 2**20,
            audio=McuAudioIO(n_tdm_buses=1, max_slots_per_bus=16,
                             max_frame_bits=128, max_bit_clock_hz=24.576e6),
        )
        req = compute_requirements(_config(logmel={"enabled": False},
                                           headroom_pct=0), 16)
        verdict = evaluate_profile(req, profile)
        self.assertTrue(verdict.fits_compute)
        self.assertTrue(verdict.fits_ram)
        self.assertFalse(verdict.fits_audio_io)
        self.assertFalse(verdict.fits)


class TestConfigSchema(unittest.TestCase):
    def test_unknown_target_raises_with_known_names(self):
        with self.assertRaises(KeyError) as ctx:
            resolve_profiles(McuConfig(targets=["stm32h999"]))
        self.assertIn("stm32h753", str(ctx.exception))

    def test_custom_profile_overrides_builtin(self):
        custom = McuProfile(
            name="stm32h753", clock_hz=550e6, macs_per_cycle=1.0,
            sram_bytes=10, flash_bytes=10,
            audio=McuAudioIO(n_tdm_buses=1, max_slots_per_bus=16,
                             max_frame_bits=256, max_bit_clock_hz=27e6),
        )
        mcu = McuConfig(targets=["stm32h753"], custom_profiles=[custom])
        self.assertEqual(resolve_profiles(mcu)[0].clock_hz, 550e6)

    def test_logmel_fft_must_be_power_of_two(self):
        with self.assertRaises(ValidationError):
            Config.from_dict({"mcu": {"logmel": {"fft_size": 1000}}})

    def test_mcu_defaults_off(self):
        cfg = Config()
        self.assertFalse(cfg.mcu.enabled)
        self.assertEqual(cfg.mcu.targets, ["stm32h753"])


class TestLegacyBudgetUnchanged(unittest.TestCase):
    def test_default_estimate_values(self):
        # Pin the legacy estimator so extending beside it never drifts it:
        # 171 bins in [0, 4 kHz] at 2048/48k, ±60° @ 2° grid = 3721 dirs.
        b = estimate(n_mics=16, fft_size=2048, hop_length=512, fs=48000,
                     n_directions=3721, max_freq=4000.0)
        self.assertEqual(b.n_freqs_used, 171)
        self.assertAlmostEqual(b.phase_tensor_mb, 77.67, delta=0.01)
        self.assertAlmostEqual(b.frame_period_ms, 10.667, delta=0.001)
        self.assertFalse(b.fits_h753)
        self.assertIn("[MEMORY]", b.summary())
