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

from ..config import McuAudioIO, McuProfile

TDM_CHAIN_LIMIT = 16  # ICS-52000 WS daisy-chain maximum (DS-000121 §TDM)
# ICS-52000 frames must contain 64/128/256/512 SCK cycles → n ∈ {2,4,8,16}.
_TDM_SLOT_COUNTS = (16, 8, 4, 2)


BUILTIN_PROFILES = {
    "stm32h753": McuProfile(
        name="stm32h753",
        clock_hz=480e6,               # Cortex-M7 @ 480 MHz
        macs_per_cycle=1.0,           # complex MAC/cycle with CMSIS-DSP float32
        sram_bytes=859_832,           # ~0.82 MiB usable (AXI+SRAM1-3 minus stack)
        flash_bytes=2 * 2**20,
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
        macs_per_cycle=1.0,
        sram_bytes=859_832,           # VERIFY: D1/D2 SRAM split usable by CM7
        flash_bytes=2 * 2**20,
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
        macs_per_cycle=0.5,           # VERIFY: CM4F sustains ~half the CM7
                                      # complex-MAC throughput with CMSIS-DSP
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
        macs_per_cycle=0.25,          # VERIFY: scalar FPU, no CMSIS-class
                                      # complex-MAC path (ESP-DSP helps some)
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
        macs_per_cycle=1.0,
        sram_bytes=1_572_864,         # ~1.5 MB of 2 MB OCRAM. VERIFY: FlexRAM split
        flash_bytes=16 * 2**20,       # external flash, typical board
        audio=McuAudioIO(
            n_tdm_buses=4,            # SAI1 has 4 RX data lines (RX-only use).
                                      # VERIFY: IMXRT1170RM; SAI2-4 single-line
            max_slots_per_bus=16,
            max_frame_bits=512,       # up to 32 words per frame per data line
            max_bit_clock_hz=24.576e6,  # VERIFY: SAI bit clock ≤ bus clk / 2
        ),
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
