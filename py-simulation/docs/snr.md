# SNR Computation

The simulation supports two SNR modes: **EIN-derived** (default) and **manual override**.

## EIN-Derived SNR (Default)

When `signal.snr_db` is `null` (not set), the SNR is computed from the microphone's Equivalent Input Noise and the drone's SPL at distance:

```
ein_db = 94 - mic.snr_dba          # ICS-52000: 94 - 65 = 29 dBA
spl_at_mic = drone_spl_db - 20·log₁₀(distance)
snr_db = spl_at_mic - ein_db
```

**Example** (default config, 15m distance):
```
SNR = 70 - 20·log₁₀(15) - (94 - 65)
    = 70 - 23.5 - 29
    = 17.5 dB
```

## Manual Override

Set `signal.snr_db` to any value to bypass the EIN derivation:

```yaml
signal:
  snr_db: 25              # fixed SNR, ignores mic EIN
```

Equivalent CLI flag: `--snr 25`

## Parameters

| Parameter | Default | Effect |
|---|---|---|
| `mic.snr_dba` | 65 | Mic SNR in dBA (94 dB SPL ref). Higher value → lower noise floor → higher SNR. |
| `signal.drone_spl_db` | 70 | Drone acoustic output at 1 m (dBA). Adjust to match specific UAV model. |
| `signal.snr_db` | null | Manual override. Non-null disables EIN computation. |

## ICS-52000 Defaults

| Parameter | Value | Meaning |
|---|---|---|
| SNR | 65 dBA | Signal is 65 dB above noise floor at 94 dB SPL |
| EIN | 29 dBA | Equivalent input noise floor |
| Sensitivity | −26 dBFS | Output level at 94 dB SPL, 1 kHz |
| AOP | 120 dB SPL | Acoustic overload point (tanh soft-clip above this) |

## Practical SNR Ranges

| Distance | Drone SPL | SNR (EIN-derived) | Detection Quality |
|---|---|---|---|---|
| 5 m | 70 dB | 27.0 dB | Strong |
| 7 m | 70 dB | 24.1 dB | Good |
| 10 m | 70 dB | 21.0 dB | Moderate |
| 15 m | 70 dB | 17.5 dB | Marginal |
| 20 m | 70 dB | 15.0 dB | Weak |
| 30 m | 70 dB | 11.5 dB | Poor |

## ICS-52000 HPF

The source signal passes through a **first-order Butterworth HPF at 75 Hz** to match the ICS-52000's low-frequency roll-off (6 dB/octave below 75 Hz). This removes sub-75 Hz broadband rotor noise.

**Impact**: ~0.8 dB P2M reduction vs a flat-response microphone. The HPF attenuates low-frequency BPF harmonics near the cutoff, reducing the total energy the SRP processor integrates.

## AOP (Acoustic Overload Point) Clipping

When the peak signal exceeds 0.5 FS (equivalent to ~114 dB SPL, or −6 dBFS), **tanh soft-clipping** is applied to emulate MEMS nonlinear distortion. This only activates for very close/loud drones (≤2 m at 70 dBA@1m) and is negligible at typical detection ranges.

## Detection Cliff: SNR + HPF + Ground

The combination creates a sharp threshold behavior:

| Configuration | P2M | Detection Rate |
|---|---|---|
| No ground, no HPF, SNR=25 | 6.3 dB | ~99% |
| No ground, HPF @ 75 Hz, SNR=25 | 5.5 dB | ~95% |
| No ground, HPF, EIN-SNR (17.5 dB) | 5.3 dB | ~96% |
| coeff=0.05, HPF, EIN-SNR | 4.4 dB | ~1% |
| coeff=0.03, HPF, EIN-SNR (oscillating) | 3.5–5.5 dB | ~50% |

The cliff exists because ground-reflection comb nulls align with BPF harmonics (200, 400, 600 … Hz). The HPF adds ~0.8 dB offset. The EIN-derived SNR at 15m (17.5 dB vs the old manual 25 dB) adds another ~0.2 dB shift. Any one factor alone is manageable; the combination pushes many scenarios below the 5 dB P2M threshold.
