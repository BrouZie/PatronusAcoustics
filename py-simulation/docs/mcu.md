# MCU Requirement Estimation

`src/analysis/mcu_requirements.py` + `src/analysis/mcu_profiles.py` turn a
simulation configuration into a hardware requirement statement — *what clock
speed, RAM, flash, uplink bandwidth, and audio I/O the station firmware would
need* — and match it against a library of MCU profiles. The legacy single-target
H753 budget (`src/analysis/mcu_budget.py`, [analysis.md](analysis.md)) is kept
unchanged; this module supersedes it for multi-target work.

Enable via config:

```yaml
mcu:
  enabled: true
  targets: [stm32h753, imxrt1176]   # preference order
  headroom_pct: 30.0                # clock margin for control/comms/ISRs
  logmel: {n_mels: 64, bits_per_bin: 8, channels: 1}
  link_overhead_pct: 20.0
```

```python
from src.analysis import evaluate_from_config
report = evaluate_from_config(config, n_mics=16)
for v in report.verdicts:
    print(v.profile.name, v.summary())
print(report.recommended)
```

Surfaces: the compare report gains an **MCU feasibility** section per geometry
(when `mcu.enabled`), and every sweep CSV row carries `mcu_required_mhz`,
`mcu_required_ram_mb`, `mcu_link_kbps`, `mcu_recommended`, and `mcu_h753_ok`
(the last always judged against the built-in stm32h753 profile so the column
is comparable across sweeps).

## Pipeline stages and formulas

All MACs are complex-MAC equivalents. `required_mhz` on the requirement object
assumes 1 MAC/cycle; per-profile verdicts divide by the profile's
`macs_per_cycle`. Firmware code size and RTOS overhead are *not* modeled —
they are discounted in each profile's `sram_bytes`/`flash_bytes` "usable"
figures.

**SRP-PHAT** (per frame of `hop_length` samples):

| Contribution | Formula |
|---|---|
| Phase table RAM | `n_freqs × n_mics × n_dirs × 8 B` (complex64) |
| Sample ring buffer | `n_mics × fft_size × 4 B` |
| DMA double buffer | `2 × n_mics × hop_length × 4 B` |
| Per-mic spectra | `n_mics × (fft_size/2+1) × 8 B` |
| MACs | `n_freqs·n_mics·n_dirs + n_mics·N·log2(N) + 2·n_freqs·n_mics` |

**Log-mel** (cost model only — the classifier lives in the C2 codebase):
reuses the SRP FFT when `logmel.fft_size`/`hop_length` are unset; otherwise
adds its own FFT per channel. Filterbank is the sparse triangular form
(≤ 2 mel weights per bin → `2 × n_bins` MACs/channel), log costs
`~10 cycles × n_mels`, weights live in flash (`2 × n_bins × 4 B`).

**Transmission**: `payload_bps = n_mels × (fs / hop) × bits_per_bin × channels`,
inflated by `link_overhead_pct` for framing/protocol. Default
(64 mels, hop 512 @ 48 kHz, 8 bit): 48 kbps payload → 57.6 kbps link.

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
takes all 16 on a single SAI1 data line.

## Profile provenance

Built-ins live in `src/analysis/mcu_profiles.py`; numbers marked `# VERIFY`
must be re-checked against the datasheet revision of the exact part before
committing to hardware (especially `macs_per_cycle`, usable SRAM splits, and
SAI/I2S electrical limits). Sources used: TDK DS-000121 (ICS-52000) and
AN-000099; ST RM0433/RM0399 + STM32H753 datasheet SAI characteristics;
ESP-IDF I2S TDM documentation; NXP IMXRT1170RM and community confirmations on
SAI1 multi-line TDM. Override or extend via `mcu.custom_profiles` (same name
replaces a built-in).

Caveat: changing any `mcu:` value changes the config hash, so cached
simulation results are re-run even though the acoustics are identical — keep
MCU-only experiments in thin override YAMLs to limit churn.
