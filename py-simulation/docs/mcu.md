# MCU Requirement Estimation

`src/analysis/mcu_requirements.py` + `src/analysis/mcu_profiles.py` turn a
simulation configuration into a hardware requirement statement — *what clock
speed, RAM, flash, uplink bandwidth, and audio I/O the station firmware would
need* — and match it against a library of MCU profiles. Each stage emits a
profile-independent **work statement** (op counts, streamed bytes, named RAM
contributions); verdicts convert work to **cycles per profile** using the
profile's core op-cost model, its memory regions, and any measured
calibration data.

Enable via config:

```yaml
mcu:
  enabled: true
  targets: [teensy41, stm32h753]    # preference order
  headroom_pct: 30.0                # pure safety margin for unmodeled costs
  sched_overhead_cycles: 2000       # modeled RTOS tick + control loop / frame
  isr_cycles: 400                   # per DMA half/complete interrupt
  logmel: {n_mels: 64, bits_per_bin: 8, channels: 1}
  link_overhead_pct: 20.0
```

```python
from src.analysis import evaluate_from_config
report = evaluate_from_config(config, n_mics=16)
for v in report.verdicts:
    print(v.profile.name, v.summary())   # names the binding constraint
print(report.recommended)
```

Surfaces: the compare report gains an **MCU feasibility** section per geometry
(when `mcu.enabled`) plus a summary-table column for the first configured
target, and every sweep CSV row carries `mcu_required_mhz`,
`mcu_required_ram_mb`, `mcu_link_kbps`, `mcu_recommended`, `mcu_target`, and
`mcu_target_ok` (the last two name and judge the first configured target, so
the boolean stays interpretable across sweeps).

## The cycle model

`required_mhz` on the requirement object is a **cross-config reference
metric**: cycles on a reference Cortex-M7 core model (0.25 complex MACs/cycle
— the M7 FPU issues one `VFMA.F32` per cycle and a complex MAC is 4 real
FMAs) with unbounded memory bandwidth. Per-profile verdicts use each
profile's own numbers.

Per-frame cycles per stage, on a profile with core model `core` and merged
calibration `cal`:

| Term | Cost |
|---|---|
| Real FFTs | `cal.rfft_cycles[N]` if measured, else nearest measured size scaled by the `N·log2 N` ratio, else `core.rfft_cycles_per_nlogn · N · log2 N` (default k = 1.7, CMSIS-DSP `arm_rfft_fast_f32` class) |
| Steering einsum | `cmacs / eff`, where `eff = min(core.cmacs_per_cycle, eff_bw / 8)` — see memory model — or `cal.steering_cmacs_per_cycle` when measured |
| Real FMAs | `rmacs / core.rmacs_per_cycle` |
| Division / sqrt / log | per-op cycle costs (M7 defaults: 14 / 14 / 25), calibration overrides field-wise |
| Overhead | `sched_overhead_cycles + 2 · required_buses · isr_cycles` per SRP frame, or `cal.overhead_cycles_per_frame` when measured |

`required_clock_hz = cycles_per_second × (1 + headroom_pct/100)`. Overheads
are *known modeled* costs; `headroom_pct` remains a pure margin for
*unknowns* — don't double-count.

Firmware code size is *not* modeled — it is discounted in each profile's
`sram_bytes`/`flash_bytes` "usable" figures.

**SRP-PHAT work statement** (per frame of `hop_length` samples):

| Contribution | Formula |
|---|---|
| Phase table RAM | `n_freqs × n_mics × n_dirs × 8 B` (complex64, const, streamed) |
| Sample ring buffer | `n_mics × fft_size × 4 B` |
| DMA double buffer | `2 × n_mics × hop_length × 4 B` |
| Per-mic spectra | `n_mics × (fft_size/2+1) × 8 B` |
| Complex MACs | `n_freqs · n_mics · n_dirs` (streams the whole table) |
| PHAT weighting | per (freq, mic): 4 FMAs + 1 sqrt + 1 div |

**Log-mel** (cost model only — the classifier lives in the C2 codebase):
reuses the SRP FFT when `logmel.fft_size`/`hop_length` are unset; otherwise
adds its own FFT per channel. Power spectrum + sparse triangular filterbank
(≤ 2 mel weights per bin) = `4 × n_bins` FMAs/channel; `n_mels` log() calls;
weights live in flash (`2 × n_bins × 4 B`).

**Transmission**: `payload_bps = n_mels × (fs / hop) × bits_per_bin × channels`,
inflated by `link_overhead_pct` for framing/protocol. Default
(64 mels, hop 512 @ 48 kHz, 8 bit): 48 kbps payload → 57.6 kbps link.

## Memory regions and boundedness

The steering einsum streams the phase table once per frame with zero reuse —
the table dwarfs any cache or TCM, so sustained throughput is
`min(compute-bound, bandwidth-bound)`. Each profile lists memory regions
(`name`, `size_bytes`, `read_bytes_per_cycle`, `writable`); placement is
greedy, fastest region first:

1. Working buffers (ring/DMA/spectra) go to **writable** regions only.
2. The const phase table takes the remaining space and **may span regions**,
   including read-only flash-XIP space (those bytes count against the flash
   budget, not RAM). Effective bandwidth over a span is the size-weighted
   harmonic mean.

`fits_ram` means everything placed. The verdict reports where the table
landed (`phase_table_regions`) and the bottleneck (`compute` vs
`memory (<regions>)`).

Profiles without `memory_regions` synthesize a single region from
`sram_bytes` with bandwidth that never binds — exact legacy RAM semantics
for old custom-profile YAML.

## Calibration: feeding real measurements back in

Once benchmark firmware runs on real hardware, drop the numbers into config
without touching the profile library:

```yaml
mcu:
  calibrations:
    teensy41:
      measured_on: "fw abc123, 2026-07-01"
      rfft_cycles: {1024: 17400, 2048: 38000}
      steering_cmacs_per_cycle: 0.21
      region_bytes_per_cycle: {psram: 0.047, ocram2: 1.8}
      overhead_cycles_per_frame: 3100
```

Precedence, field-wise: `mcu.calibrations[name]` (config level) >
`profile.calibration` (baked into a custom profile) > analytic model.
Measured values replace only the fields they set.

## Audio I/O: the TDM ingest constraint

A profile that fits compute and memory but cannot physically clock the mics in
**fails** — this constraint has equal weight, and the recommendation logic will
never suggest such a part.

Model (from the ICS-52000 datasheet, DS-000121): mics daisy-chain on one TDM
bus; the frame is `n × 32` SCK cycles with `n ∈ {2, 4, 8, 16}` (power of two ≥
mics on the bus); chain maximum 16 mics; validated SCK ceiling 24.576 MHz
(= 16 × 32 × 48 kHz). Per bus, the largest valid `n` must satisfy:

- `n ≤ min(16, profile.audio.max_slots_per_bus)`
- `n × slot_bits ≤ profile.audio.max_frame_bits` ← **binds on STM32 SAI (256)**
- `n × slot_bits × fs ≤ min(profile.audio.max_bit_clock_hz, mic_max_sck_hz)`

Then `required_buses = ceil(n_mics / n)` vs `profile.audio.n_tdm_buses`.

Consequences at 48 kHz / 32-bit slots: STM32H7 SAI carries **8 mics per
sub-block** (256-bit frame limit — not the mic's clock), so 16 mics need 2 of
its 8 sub-blocks; ESP32-S3 TDM RX is hardware-capped at 4 × 32-bit slots per
I2S → max 8 mics total, so a 16-mic array **fails audio I/O**; i.MX RT1176
and Teensy 4.1 take all 16 on a single SAI data line.

## Teensy 4.1 (`teensy41`, `teensy41_psram`)

i.MX RT1062, Cortex-M7 @ 600 MHz sustained (no heatsink needed; PJRC ships
it at 600 MHz, ~100 mA typical).

- **RAM**: 512 KB FlexRAM split ITCM/DTCM in 32 KB banks (profile assumes
  128 KB ITCM for hot code + stack → 384 KB DTCM @ 8 B/cycle) + 512 KB
  OCRAM2 (448 KB usable, ~2 B/cycle, verify/calibrate).
- **Flash**: 8 MB QSPI (7936 KB usable), code runs XIP through the cache;
  ~6 MB modeled as a read-only region at ~0.09 B/cycle for const tables.
- **PSRAM variant**: +8 MB QSPI PSRAM @ 88 MHz FlexSPI2, measured 25–28 MB/s
  sustained streaming (~0.05 B/cycle at 600 MHz). PSRAM buys **capacity, not
  throughput**: a phase table streamed from PSRAM is bandwidth-bound to
  ~0.006 cmac/cycle. Low fidelity until calibrated on hardware.
- **Audio**: SAI1 has 4 RX data lines (RX_DATA1–3 shared with TX_DATA1–3,
  IMXRT1060RM table 37-2) + SAI2 → 5 modeled TDM buses, 512-bit frames.
  **Caveat**: the Teensy Audio library only drives SAI1-D0 and SAI2 today;
  the extra lines need a custom SAI driver.

Sources: [PJRC Teensy 4.1](https://www.pjrc.com/store/teensy41.html),
[PJRC PSRAM](https://www.pjrc.com/store/psram.html), PJRC forum thread 68841
(PSRAM bandwidth), NXP IMXRT1060 reference manual, NXP community thread on
RT1062 multi-channel SAI input.

## Profile provenance

Built-ins live in `src/analysis/mcu_profiles.py`; numbers marked `# VERIFY`
must be re-checked against the datasheet revision of the exact part before
committing to hardware (especially memory-region bandwidths, usable SRAM
splits, and SAI/I2S electrical limits). Sources used: ARM Cortex-M7 TRM
(FPU throughput); TDK DS-000121 (ICS-52000) and AN-000099; ST RM0433/RM0399
+ STM32H753 datasheet SAI characteristics; ESP-IDF I2S TDM documentation;
NXP IMXRT1170RM/IMXRT1060RM and community confirmations on SAI multi-line
TDM; PJRC documentation and forum benchmarks for Teensy 4.1. Override or
extend via `mcu.custom_profiles` (same name replaces a built-in).

Caveat: changing any `mcu:` value changes the config hash, so cached
simulation results are re-run even though the acoustics are identical — keep
MCU-only experiments in thin override YAMLs to limit churn. The schema
extension that introduced the cycle model (core/memory/calibration fields)
changed every config hash once; cached results from before that change
recompute on first use.
