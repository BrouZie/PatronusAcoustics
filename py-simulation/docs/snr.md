# SNR Budget and Sensor Model

Sensor behaviour lives in `src/sensor.py`: the SNR budget (`effective_snr_db()`) and the mic-chain effects (`SensorModel`). The simulation supports two modes: **calibrated Pa-referenced** (default) and **manual snr_db override** (legacy path, used by sweeps).

## Calibrated Pa-Referenced Mode (Default)

When `signal.snr_db` is `null`, everything upstream of `SensorModel` is acoustic pressure in **Pascals at the diaphragm**: the drone source is scaled to `drone_spl_db` (Pa RMS at 1 m), the 1/r spreading, ISO 9613-1 absorption, ground reflection, and all environmental noise sources (see [environment.md](environment.md)) then carry physically meaningful levels. `SensorModel` adds the mic's absolute EIN noise floor in Pa and converts Pa → digital full scale as the final step, using the datasheet sensitivity:

```
fs_per_pa = 10^(sensitivity_dbFS / 20)        # −26 dBFS @ 1 Pa → 0.0501 FS/Pa
```

With the ICS-52000 numbers this puts 120 dB SPL (the AOP) at ≈ 1.0 FS, so digital clipping and acoustic overload coincide — as in the real part. SRP-PHAT whitens channel magnitudes, so the absolute scale does not disturb localization; what it buys is trustworthy SNR, noise-floor, and detection-range numbers. Anchors are pinned in `tests/test_physics_validation.py` (silent scene ≈ 29 dB SPL EIN floor; source SPL at distance; budget-vs-measured SNR within 1.5 dB).

`effective_snr_db()` remains the closed-form **prediction** of that budget:

```
ein_db      = REF_SPL_DB − mic.snr_dba        # ICS-52000: 94 − 65 = 29 dB SPL
spl_at_mic  = drone_spl_db − 20·log₁₀(distance) − α(f)·distance
snr_db      = spl_at_mic − ein_db
```

The absorption term uses the ISO 9613-1 coefficient averaged over the drone's BPF harmonics (applied when the environment is enabled). `REF_SPL_DB = 94` lives in `src/constants.py` — the datasheet convention that mic SNR is quoted re 94 dB SPL.

**Example** (drone SPL 70 dB @ 1 m, 15 m distance, no absorption):
```
SNR = 70 − 20·log₁₀(15) − (94 − 65) = 70 − 23.5 − 29 = 17.5 dB
```

## Manual Override (Legacy Path)

```yaml
signal:
  snr_db: 25              # fixed SNR, bypasses the Pa calibration (sweeps use this)
```

Equivalent CLI flag: `--snr 25`. In this mode the source stays in normalized units, self-noise is placed at `snr_db` relative to each mic's own signal power, and environmental noise uses the pre-v5 empirical scale factors — bit-compatible with older sweep results.

## SensorModel — the Mic Chain

`SensorModel.apply()` processes the clean propagated signals in order:

1. **Gain mismatch** — per-mic gain drawn from `N(0, gain_std_db)`
2. **Phase mismatch** — per-mic constant phase rotation, `N(0, phase_std_deg)`
3. **LF roll-off** — per-mic 1st-order Butterworth HPF; nominal 75 Hz corner, spread per mic by `hpf_corner_std_pct` (part-to-part tolerance ⇒ frequency-dependent gain *and* phase mismatch at LF)
4. **HF response** — ICS-52000 datasheet magnitude trace (mild rise to ~+3.5 dB at 20 kHz) realized as a minimum-phase filter; flat for other mic models
5. **Self-noise** — calibrated mode: absolute EIN floor in Pa; legacy mode: white noise at the budget SNR re signal power
6. **Pa → FS conversion** (calibrated mode only) via `fs_per_pa`
7. **AOP soft clipping** — tanh saturation when the peak exceeds 0.5 FS (~114 dB SPL)
8. **Dead channels** — `failed_mics` are zeroed
9. **Quantization** — round to `quantization_bits` (24 for the ICS-52000 TDM stream; now physically meaningful since 1.0 FS ≈ AOP)

Placement error is handled separately: `SensorModel.position_offsets` (drawn from `position_std_mm`) perturbs the array's **true** positions while SRP steering keeps using the **nominal** ones — see [array.md](array.md).

## Imperfection Config

```yaml
mic:
  snr_dba: 65
  imperfections:
    gain_std_db: 0.5        # ICS-52000 sensitivity tolerance ~±1 dB
    phase_std_deg: 2.0
    position_std_mm: 1.5    # PCB/assembly tolerance
    hpf_corner_std_pct: 10.0  # per-mic LF corner spread (freq-dependent mismatch)
    quantization_bits: 24
    failed_mics: []         # e.g. [3, 11] to simulate dead channels
    seed: 0                 # one "build" of the array — independent of signal.seed
```

Defaults are all zero/None (ideal array); `config/default.yaml` enables realistic ICS-52000 values. The imperfection draw is seeded separately from the acoustic realization, so the same physical build can be re-run under different noise.

**Which imperfections matter**: SRP-PHAT normalizes each channel's magnitude, so it is nearly immune to *gain* mismatch — *phase* mismatch and *placement error* are what degrade PSR and angular accuracy. Budget fabrication tolerance accordingly.

## ICS-52000 Reference Values

| Parameter | Value | Meaning |
|---|---|---|
| SNR | 65 dBA | Signal 65 dB above noise floor at 94 dB SPL |
| EIN | 29 dB SPL | Equivalent input noise floor |
| Sensitivity | −26 dBFS | Output level at 94 dB SPL, 1 kHz |
| AOP | 120 dB SPL | Acoustic overload point |

## Practical SNR Ranges (spreading only, drone 70 dB @ 1 m)

| Distance | SNR (EIN-derived) | Detection Quality |
|---|---|---|
| 5 m | 27.0 dB | Strong |
| 10 m | 21.0 dB | Moderate |
| 15 m | 17.5 dB | Marginal |
| 20 m | 15.0 dB | Weak |
| 30 m | 11.5 dB | Poor |

At these short ranges absorption subtracts ≲0.2 dB; it becomes the range-limiting term beyond ~100 m (see [environment.md](environment.md)).

## Detection Cliff: SNR + HPF + Ground

Ground-reflection comb nulls align with BPF harmonics (200, 400, 600 … Hz); the HPF removes sub-75 Hz energy; the EIN budget sets the floor. Any one factor alone is manageable — combined they push marginal scenarios below the 5 dB peak-to-mean threshold, producing a sharp detection cliff rather than graceful degradation. See [environment.md](environment.md) for the ground-reflection numbers.
