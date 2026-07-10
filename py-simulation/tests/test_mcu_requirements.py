"""Tests for the multi-target MCU requirements engine.

Anchors the TDM mic-ingest math to the ICS-52000 datasheet rules, pins
the log-mel uplink payload and the phase-table footprint, checks that
verdicts name their binding constraints, and covers the cycle model:
memory placement/bandwidth-boundedness, calibration overrides, and the
modeled scheduler/ISR overhead.
"""

import math
import unittest

from pydantic import ValidationError

from src.analysis.mcu_profiles import (
    BUILTIN_PROFILES,
    mics_per_bus,
    required_tdm_buses,
    resolve_profiles,
)
from src.analysis.mcu_requirements import (
    PHASE_TABLE_BYTES,
    compute_requirements,
    evaluate_from_config,
    evaluate_profile,
    reference_stage_cycles,
)
from src.config import (
    Config,
    McuAudioIO,
    McuCalibration,
    McuConfig,
    McuCoreModel,
    McuMemoryRegion,
    McuProfile,
)


def _config(**mcu_overrides):
    mcu = {"enabled": True, "targets": ["stm32h753"]}
    mcu.update(mcu_overrides)
    return Config.from_dict({"mcu": mcu})


def _profile(**overrides):
    """A permissive baseline profile for targeted constraint tests."""
    kwargs = dict(
        name="test", clock_hz=1e9,
        sram_bytes=512 * 2**20, flash_bytes=512 * 2**20,
        audio=McuAudioIO(n_tdm_buses=4, max_slots_per_bus=16,
                         max_frame_bits=512, max_bit_clock_hz=24.576e6),
    )
    kwargs.update(overrides)
    return McuProfile(**kwargs)


class TestTdmCapacity(unittest.TestCase):
    """ICS-52000 frame rule: n × 32 SCK, n ∈ {2,4,8,16} ≥ mics on bus."""

    h753 = BUILTIN_PROFILES["stm32h753"].audio
    esp = BUILTIN_PROFILES["esp32s3"].audio
    rt = BUILTIN_PROFILES["imxrt1176"].audio
    teensy = BUILTIN_PROFILES["teensy41"].audio

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

    def test_teensy41_takes_full_chain(self):
        # Same SAI IP family as the i.MX RT1176: 512-bit frames, one
        # 16-mic chain per bus at 48 kHz, five usable RX data lines.
        self.assertEqual(mics_per_bus(self.teensy, 48000, 32, 24.576e6), 16)
        self.assertEqual(required_tdm_buses(16, 16), 1)
        self.assertEqual(self.teensy.n_tdm_buses, 5)

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
        self.assertGreater(
            reference_stage_cycles(lm_sep) / lm_sep.frame_period_s,
            reference_stage_cycles(lm_reuse) / lm_reuse.frame_period_s)

    def test_headroom_scales_required_clock(self):
        base = compute_requirements(_config(headroom_pct=0), 16)
        padded = compute_requirements(_config(headroom_pct=50), 16)
        self.assertAlmostEqual(padded.required_mhz, base.required_mhz * 1.5,
                               places=6)

    def test_phase_table_pin(self):
        # 171 bins in [0, 4 kHz] at 2048/48k × 16 mics × 3721 dirs
        # (±60° @ 2°) × 8 B complex64.
        req = compute_requirements(_config(), n_mics=16)
        srp = next(s for s in req.stages if s.name == "srp_phat")
        table = next(c for c in srp.ram if c.name == "phase_table")
        self.assertEqual(table.bytes, 171 * 16 * 3721 * PHASE_TABLE_BYTES)
        self.assertTrue(table.const)
        self.assertTrue(table.streamed)
        self.assertEqual(srp.work.streamed_bytes, table.bytes)


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

    def test_coarse_station_grid_fits_teensy41(self):
        cfg = Config.from_dict({
            "srpphat": {
                "fft_size": 1024,
                "max_freq": 2000.0, "min_freq": 300.0,
                "search": {"resolution_deg": 12.0},
            },
            "mcu": {"enabled": True, "targets": ["teensy41"]},
        })
        report = evaluate_from_config(cfg, n_mics=16)
        verdict = report.verdicts[0]
        self.assertTrue(verdict.fits, verdict.summary())
        self.assertLess(verdict.utilization_pct, 50.0)

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
        profile = _profile(
            name="fast_but_deaf", clock_hz=2e9,
            core=McuCoreModel(cmacs_per_cycle=2.0),
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

    def test_slower_core_needs_higher_clock(self):
        req = compute_requirements(_config(logmel={"enabled": False}), 16)
        fast = evaluate_profile(req, _profile(
            core=McuCoreModel(cmacs_per_cycle=0.25)))
        slow = evaluate_profile(req, _profile(
            core=McuCoreModel(cmacs_per_cycle=0.08, rmacs_per_cycle=0.33)))
        self.assertGreater(slow.required_clock_hz, fast.required_clock_hz)


class TestMemoryModel(unittest.TestCase):
    def test_psram_placement_is_bandwidth_bound(self):
        # ±60° @ 5° → 25×25 = 625 dirs; table = 171·16·625·8 ≈ 13.7 MB:
        # too big for the Teensy's internal RAM + flash XIP, so it spills
        # into PSRAM and the steering einsum becomes bandwidth-bound.
        cfg = Config.from_dict({
            "srpphat": {"search": {"resolution_deg": 5.0}},
            "mcu": {"enabled": True, "targets": ["teensy41_psram"]},
        })
        verdict = evaluate_from_config(cfg, n_mics=16).verdicts[0]
        self.assertTrue(verdict.fits_ram, verdict.summary())
        self.assertIn("psram", verdict.phase_table_regions)
        self.assertIn("psram", verdict.bottleneck)
        self.assertFalse(verdict.fits_compute)

    def test_flash_xip_spill_counts_against_flash(self):
        # One region: read-only flash. The const table must land there
        # and be charged to the flash budget, not RAM.
        req = compute_requirements(_config(logmel={"enabled": False}), 16)
        srp = req.stages[0]
        table = next(c for c in srp.ram if c.name == "phase_table")
        dynamic = srp.ram_bytes - table.bytes
        profile = _profile(memory_regions=[
            McuMemoryRegion(name="sram", size_bytes=int(dynamic + 1024),
                            read_bytes_per_cycle=8.0),
            McuMemoryRegion(name="flash_xip", size_bytes=100 * 2**20,
                            read_bytes_per_cycle=0.09, writable=False),
        ])
        verdict = evaluate_profile(req, profile)
        self.assertTrue(verdict.fits_ram)
        self.assertGreaterEqual(verdict.flash_bytes, table.bytes)
        self.assertLess(verdict.ram_bytes, dynamic + 2048)

    def test_working_buffers_never_go_to_readonly_regions(self):
        # Only a read-only region is big enough for the buffers → the
        # placement must fail rather than put DMA buffers in flash.
        req = compute_requirements(_config(logmel={"enabled": False}), 16)
        profile = _profile(memory_regions=[
            McuMemoryRegion(name="sram", size_bytes=1024,
                            read_bytes_per_cycle=8.0),
            McuMemoryRegion(name="flash_xip", size_bytes=512 * 2**20,
                            read_bytes_per_cycle=0.09, writable=False),
        ])
        verdict = evaluate_profile(req, profile)
        self.assertFalse(verdict.fits_ram)

    def test_legacy_profile_without_regions_uses_sram_bytes(self):
        req = compute_requirements(_config(logmel={"enabled": False}), 16)
        small = evaluate_profile(req, _profile(sram_bytes=2**20))
        big = evaluate_profile(req, _profile(sram_bytes=512 * 2**20))
        self.assertFalse(small.fits_ram)
        self.assertTrue(big.fits_ram)
        # Synthesized region is fast enough that compute binds, not memory.
        self.assertEqual(big.bottleneck, "compute")


class TestCalibration(unittest.TestCase):
    def _req(self, **mcu_overrides):
        return compute_requirements(
            _config(logmel={"enabled": False}, headroom_pct=0,
                    **mcu_overrides), 16)

    def test_rfft_calibration_exact_size(self):
        base = self._req()
        cal = McuCalibration(rfft_cycles={2048: 50_000})
        with_cal = evaluate_profile(base, _profile(calibration=cal))
        without = evaluate_profile(base, _profile())
        # 16 per-mic FFTs/frame: measured 50 k cycles each replaces the
        # analytic 1.7·N·log2(N).
        analytic = 1.7 * 2048 * math.log2(2048)
        delta_cycles = 16 * (50_000 - analytic)
        period = base.stages[0].frame_period_s
        self.assertAlmostEqual(
            with_cal.required_clock_hz - without.required_clock_hz,
            delta_cycles / period, delta=1.0)

    def test_rfft_calibration_nearest_size_scaling(self):
        # Only 1024 measured; 2048 scales by the N·log2N ratio.
        base = self._req()
        cal = McuCalibration(rfft_cycles={1024: 20_000})
        v = evaluate_profile(base, _profile(calibration=cal))
        scaled = 20_000 * (2048 * 11) / (1024 * 10)
        srp_cycles = v.cycles_by_stage["srp_phat"]
        v_exact = evaluate_profile(base, _profile(
            calibration=McuCalibration(rfft_cycles={2048: int(scaled)})))
        self.assertAlmostEqual(srp_cycles,
                               v_exact.cycles_by_stage["srp_phat"],
                               delta=16.0)

    def test_steering_calibration_overrides_bandwidth_model(self):
        base = self._req()
        cal = McuCalibration(steering_cmacs_per_cycle=0.21)
        v = evaluate_profile(base, _profile(calibration=cal))
        self.assertEqual(v.bottleneck, "calibrated")

    def test_config_calibration_beats_profile_calibration(self):
        profile_cal = McuCalibration(rfft_cycles={2048: 50_000},
                                     div_cycles=20.0)
        config_cal = {"stm32h753": {"div_cycles": 10.0}}
        req = self._req(calibrations=config_cal)
        profile = BUILTIN_PROFILES["stm32h753"].model_copy(
            update={"calibration": profile_cal})
        v = evaluate_profile(req, profile)
        # div comes from the config level, rfft stays from the profile.
        v_ref = evaluate_profile(req, BUILTIN_PROFILES["stm32h753"].model_copy(
            update={"calibration": McuCalibration(
                rfft_cycles={2048: 50_000}, div_cycles=10.0)}))
        self.assertAlmostEqual(v.required_clock_hz, v_ref.required_clock_hz,
                               delta=1.0)

    def test_overhead_model(self):
        # Overhead = sched + 2 · buses · isr cycles per SRP frame.
        base = self._req(sched_overhead_cycles=0, isr_cycles=0)
        loaded = self._req(sched_overhead_cycles=3000, isr_cycles=500)
        profile = _profile()  # 16 mics / 16 per bus → 1 bus
        v0 = evaluate_profile(base, profile)
        v1 = evaluate_profile(loaded, profile)
        period = base.stages[0].frame_period_s
        expected = (3000 + 2 * 1 * 500) / period
        self.assertAlmostEqual(
            v1.required_clock_hz - v0.required_clock_hz, expected, delta=1.0)

    def test_measured_overhead_replaces_model(self):
        loaded = self._req(sched_overhead_cycles=3000, isr_cycles=500)
        cal = McuCalibration(overhead_cycles_per_frame=0.0)
        v_cal = evaluate_profile(loaded, _profile(calibration=cal))
        base = self._req(sched_overhead_cycles=0, isr_cycles=0)
        v0 = evaluate_profile(base, _profile())
        self.assertAlmostEqual(v_cal.required_clock_hz, v0.required_clock_hz,
                               delta=1.0)


class TestConfigSchema(unittest.TestCase):
    def test_unknown_target_raises_with_known_names(self):
        with self.assertRaises(KeyError) as ctx:
            resolve_profiles(McuConfig(targets=["stm32h999"]))
        self.assertIn("stm32h753", str(ctx.exception))

    def test_custom_profile_overrides_builtin(self):
        custom = _profile(name="stm32h753", clock_hz=550e6)
        mcu = McuConfig(targets=["stm32h753"], custom_profiles=[custom])
        self.assertEqual(resolve_profiles(mcu)[0].clock_hz, 550e6)

    def test_deprecated_macs_per_cycle_maps_to_core(self):
        # Old-style YAML profile (no `core`) keeps its meaning.
        old = McuProfile.model_validate({
            "name": "legacy", "clock_hz": 480e6, "macs_per_cycle": 1.0,
            "sram_bytes": 859_832, "flash_bytes": 2 * 2**20,
            "audio": {"n_tdm_buses": 8, "max_slots_per_bus": 16,
                      "max_frame_bits": 256, "max_bit_clock_hz": 27e6},
        })
        self.assertEqual(old.core.cmacs_per_cycle, 1.0)

    def test_explicit_core_wins_over_deprecated_field(self):
        p = _profile(core=McuCoreModel(cmacs_per_cycle=0.15),
                     macs_per_cycle=2.0)
        self.assertEqual(p.core.cmacs_per_cycle, 0.15)

    def test_calibration_yaml_string_keys_coerce_to_int(self):
        cal = McuCalibration.model_validate({"rfft_cycles": {"2048": 50000}})
        self.assertEqual(cal.rfft_cycles, {2048: 50000})

    def test_logmel_fft_must_be_power_of_two(self):
        with self.assertRaises(ValidationError):
            Config.from_dict({"mcu": {"logmel": {"fft_size": 1000}}})

    def test_mcu_defaults_off(self):
        cfg = Config()
        self.assertFalse(cfg.mcu.enabled)
        self.assertEqual(cfg.mcu.targets, ["stm32h753"])

    def test_builtin_teensy_profiles_exist(self):
        self.assertIn("teensy41", BUILTIN_PROFILES)
        self.assertIn("teensy41_psram", BUILTIN_PROFILES)
        base = BUILTIN_PROFILES["teensy41"]
        psram = BUILTIN_PROFILES["teensy41_psram"]
        self.assertEqual(base.clock_hz, 600e6)
        base_regions = {r.name for r in base.memory_regions}
        psram_regions = {r.name for r in psram.memory_regions}
        self.assertEqual(psram_regions - base_regions, {"psram"})
