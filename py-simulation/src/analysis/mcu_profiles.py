"""Built-in MCU target profiles and the TDM mic-ingest capacity model.

Audio I/O is a first-class constraint: an MCU that fits the compute and
memory budget but cannot physically clock N ICS-52000 mics into its
SAI/I2S peripherals is not a valid recommendation. The capacity model
follows the ICS-52000 datasheet (DS-000121): mics daisy-chain on one TDM
bus, the frame is n × 32 SCK cycles where n is a power of two (2/4/8/16)
equal to or greater than the number of mics on the bus, and 16 mics per
chain at 24.576 MHz SCK is the validated maximum.

The peripheral side is captured per profile: number of TDM-capable RX
buses (independent SD lines), slots per bus, maximum frame length in bit
clocks (the binding limit on STM32 SAI: 256), and maximum bit clock.

Numbers marked VERIFY should be re-checked against the datasheet revision
for the exact part ordered before committing to hardware.
"""

import math

from ..config import McuAudioIO, McuCoreModel, McuMemoryRegion, McuProfile

TDM_CHAIN_LIMIT = 16  # ICS-52000 WS daisy-chain maximum (DS-000121 §TDM)
# ICS-52000 frames must contain 64/128/256/512 SCK cycles → n ∈ {2,4,8,16}.
_TDM_SLOT_COUNTS = (16, 8, 4, 2)

# Core op-cost models. Cortex-M7: FPU issues 1 VFMA.F32/cycle and a
# complex MAC is 4 real FMAs → 0.25 cmac/cycle compute ceiling (ARM
# Cortex-M7 TRM); VDIV/VSQRT.F32 ≈ 14 cycles, non-pipelined. The old
# profile value of 1.0 cmac/cycle was ~4x optimistic.
_CORE_M7 = McuCoreModel()  # M7 defaults live in the schema
# Cortex-M4F: VFMA.F32 is 3 cycles, no dual-issue → ~0.08 cmac/cycle.
_CORE_M4F = McuCoreModel(
    cmacs_per_cycle=0.08, rmacs_per_cycle=0.33,
    rfft_cycles_per_nlogn=4.0, log_cycles=40.0,
)
# Xtensa LX7 (ESP32-S3): pipelined FPU madd.s but no CMSIS-class
# kernels; ESP-DSP narrows the gap some. VERIFY against ESP-DSP
# benchmarks before trusting for hardware selection.
_CORE_LX7 = McuCoreModel(
    cmacs_per_cycle=0.15, rmacs_per_cycle=0.7, rfft_cycles_per_nlogn=6.0,
)


def _teensy41(name: str, extra_regions: list[McuMemoryRegion] = (),
              extra_notes: str = "") -> McuProfile:
    """Teensy 4.1 (i.MX RT1062, Cortex-M7 @ 600 MHz).

    Provenance: PJRC store page (pjrc.com/store/teensy41.html), PJRC
    PSRAM page + forum thread 68841 (PSRAM sustained bandwidth),
    IMXRT1060 reference manual table 37-2 (SAI pin muxing), NXP
    community thread on RT1062 multi-channel SAI input.
    """
    return McuProfile(
        name=name,
        clock_hz=600e6,               # ships at 600 MHz sustained, no
                                      # heatsink (~100 mA typical)
        core=_CORE_M7,
        sram_bytes=851_968,           # legacy fallback: DTCM + OCRAM2 below
        flash_bytes=8_126_464,        # 7936 KB usable of 8 MB QSPI
                                      # (W25Q64JV), code runs XIP via cache
        memory_regions=[
            # 512 KB FlexRAM splits ITCM/DTCM in 32 KB banks; assume
            # 128 KB ITCM for hot code + stack → 384 KB DTCM.
            # VERIFY against the firmware link map.
            McuMemoryRegion(name="dtcm", size_bytes=393_216,
                            read_bytes_per_cycle=8.0),
            # OCRAM2 512 KB minus 64 KB DMA/heap; 64-bit AXI @ 150 MHz,
            # D-cached. VERIFY/calibrate streaming bandwidth.
            McuMemoryRegion(name="ocram2", size_bytes=458_752,
                            read_bytes_per_cycle=2.0),
            # Const tables may stream from QSPI flash XIP (cached, zero
            # reuse): FlexSPI quad SDR ≈ 50-60 MB/s sustained
            # → ~0.09 B/cycle @ 600 MHz. VERIFY.
            McuMemoryRegion(name="flash_xip", size_bytes=6 * 2**20,
                            read_bytes_per_cycle=0.09, writable=False),
            *extra_regions,
        ],
        audio=McuAudioIO(
            n_tdm_buses=5,            # SAI1 RX_DATA0-3 (pins 8/32/9/6; data
                                      # lines 1-3 shared with TX_DATA1-3,
                                      # IMXRT1060RM table 37-2) + SAI2 RX
                                      # (pin 5). VERIFY: Teensy Audio lib
                                      # only drives SAI1-D0 and SAI2 today;
                                      # extra lines need a custom SAI driver.
            max_slots_per_bus=16,     # SAI does 32 words/frame; ICS-52000
                                      # chain limit (16) binds first
            max_frame_bits=512,       # 16 × 32-bit slots
            max_bit_clock_hz=24.576e6,  # VERIFY: SAI BCLK from audio PLL
        ),
        notes="600 MHz sustained without heatsink. TDM beyond SAI1-D0 and "
              "SAI2 requires a custom SAI driver (Teensy Audio library "
              "drives only those two)." + extra_notes,
    )


BUILTIN_PROFILES = {
    "stm32h753": McuProfile(
        name="stm32h753",
        clock_hz=480e6,               # Cortex-M7 @ 480 MHz
        core=_CORE_M7,
        sram_bytes=859_832,           # ~0.82 MiB usable (AXI+SRAM1-3 minus stack)
        flash_bytes=2 * 2**20,
        memory_regions=[
            # RM0433 §2.3 memory map; bandwidths are sustained streaming
            # estimates (core 480 MHz, AXI 240 MHz). VERIFY bandwidths.
            McuMemoryRegion(name="dtcm", size_bytes=131_072,
                            read_bytes_per_cycle=8.0),
            McuMemoryRegion(name="axi_sram", size_bytes=524_288,
                            read_bytes_per_cycle=4.0),
            McuMemoryRegion(name="sram_d2", size_bytes=294_912,
                            read_bytes_per_cycle=2.0),
        ],
        audio=McuAudioIO(
            n_tdm_buses=8,            # 4 SAI × 2 sub-blocks, each own SD pin
                                      # VERIFY: RM0433 §51, pin availability on board
            max_slots_per_bus=16,     # SLOTR NBSLOT limit (RM0433)
            max_frame_bits=256,       # SAI frame ≤ 256 bit clocks → 8 × 32-bit slots
            max_bit_clock_hz=27e6,    # VERIFY: DS SAI characteristics table
        ),
    ),
    "stm32h747": McuProfile(
        name="stm32h747",
        clock_hz=480e6,               # CM7 core (CM4 @ 240 MHz free for comms)
        core=_CORE_M7,
        sram_bytes=859_832,           # VERIFY: D1/D2 SRAM split usable by CM7
        flash_bytes=2 * 2**20,
        memory_regions=[
            # Same memory system as H753. VERIFY bandwidths.
            McuMemoryRegion(name="dtcm", size_bytes=131_072,
                            read_bytes_per_cycle=8.0),
            McuMemoryRegion(name="axi_sram", size_bytes=524_288,
                            read_bytes_per_cycle=4.0),
            McuMemoryRegion(name="sram_d2", size_bytes=294_912,
                            read_bytes_per_cycle=2.0),
        ],
        audio=McuAudioIO(
            n_tdm_buses=8,            # same SAI IP as H753. VERIFY: RM0399
            max_slots_per_bus=16,
            max_frame_bits=256,
            max_bit_clock_hz=27e6,    # VERIFY
        ),
    ),
    "stm32f446": McuProfile(
        name="stm32f446",
        clock_hz=180e6,               # Cortex-M4F
        core=_CORE_M4F,
        sram_bytes=114_688,           # 128 KB total minus stacks/buffers
        flash_bytes=512 * 2**10,
        audio=McuAudioIO(
            n_tdm_buses=4,            # SAI1+SAI2 × 2 sub-blocks. VERIFY: RM0390
            max_slots_per_bus=16,
            max_frame_bits=256,
            max_bit_clock_hz=12.5e6,  # VERIFY: DS SAI characteristics
        ),
    ),
    "esp32s3": McuProfile(
        name="esp32s3",
        clock_hz=240e6,
        core=_CORE_LX7,
        sram_bytes=327_680,           # 512 KB minus Wi-Fi/RTOS working set
        flash_bytes=8 * 2**20,        # external flash, typical module
        audio=McuAudioIO(
            n_tdm_buses=2,            # I2S0 + I2S1 in TDM RX
            max_slots_per_bus=16,
            max_frame_bits=128,       # HW limit: 4 slots @ 32-bit width
                                      # (ESP-IDF I2S TDM docs)
            max_bit_clock_hz=24.576e6,  # VERIFY: BCLK derivation limits
        ),
    ),
    "imxrt1176": McuProfile(
        name="imxrt1176",
        clock_hz=996e6,               # Cortex-M7 @ ~1 GHz
        core=_CORE_M7,
        sram_bytes=1_572_864,         # ~1.5 MB of 2 MB OCRAM. VERIFY: FlexRAM split
        flash_bytes=16 * 2**20,       # external flash, typical board
        memory_regions=[
            McuMemoryRegion(name="dtcm", size_bytes=262_144,
                            read_bytes_per_cycle=8.0),  # VERIFY FlexRAM split
            McuMemoryRegion(name="ocram", size_bytes=1_310_720,
                            read_bytes_per_cycle=2.0),  # VERIFY
        ],
        audio=McuAudioIO(
            n_tdm_buses=4,            # SAI1 has 4 RX data lines (RX-only use).
                                      # VERIFY: IMXRT1170RM; SAI2-4 single-line
            max_slots_per_bus=16,
            max_frame_bits=512,       # up to 32 words per frame per data line
            max_bit_clock_hz=24.576e6,  # VERIFY: SAI bit clock ≤ bus clk / 2
        ),
    ),
    "teensy41": _teensy41("teensy41"),
    # PSRAM buys capacity, not throughput: a phase table streamed from
    # QSPI PSRAM is bandwidth-bound to ~0.006 cmac/cycle (~3.8 M cmac/s
    # @ 600 MHz). Low fidelity until calibrated on hardware.
    "teensy41_psram": _teensy41(
        "teensy41_psram",
        extra_regions=[
            # 8 MB QSPI PSRAM @ 88 MHz FlexSPI2; measured 25-28 MB/s
            # sustained streaming (PJRC forum 68841) → ~0.05 B/cycle.
            McuMemoryRegion(name="psram", size_bytes=8 * 2**20,
                            read_bytes_per_cycle=0.05),
        ],
        extra_notes=" PSRAM adds capacity, not throughput: tables placed "
                    "there are bandwidth-bound to ~0.006 cmac/cycle.",
    ),
}


def resolve_profiles(mcu_config) -> list[McuProfile]:
    """Profiles named in `targets`, custom entries overriding built-ins."""
    custom = {p.name: p for p in mcu_config.custom_profiles}
    profiles = []
    for name in mcu_config.targets:
        profile = custom.get(name) or BUILTIN_PROFILES.get(name)
        if profile is None:
            known = sorted(set(BUILTIN_PROFILES) | set(custom))
            raise KeyError(
                f"unknown MCU target '{name}'; known profiles: {', '.join(known)}"
            )
        profiles.append(profile)
    return profiles


def mics_per_bus(audio: McuAudioIO, fs: int, slot_bits: int,
                 mic_max_sck_hz: float) -> int:
    """Largest ICS-52000 chain one TDM bus can carry at this sample rate.

    Picks the largest valid slot count n (power of two, per the mic's
    frame rule) that fits the peripheral's slot, frame-length, and bit
    clock limits and the mic's own SCK ceiling. Returns 0 if even a
    2-mic frame cannot be clocked.
    """
    sck_limit = min(audio.max_bit_clock_hz, mic_max_sck_hz)
    for n in _TDM_SLOT_COUNTS:
        if n > TDM_CHAIN_LIMIT or n > audio.max_slots_per_bus:
            continue
        if n * slot_bits > audio.max_frame_bits:
            continue
        if n * slot_bits * fs > sck_limit:
            continue
        return n
    return 0


def required_tdm_buses(n_mics: int, per_bus: int) -> int | None:
    """Buses needed to ingest n_mics, or None if a single bus fits zero."""
    if per_bus <= 0:
        return None
    return math.ceil(n_mics / per_bus)
