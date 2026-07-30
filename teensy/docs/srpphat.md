# SRP-PHAT on the Teensy 4.1

Design notes for the on-station SRP-PHAT DOA pipeline, and the benchmark
methodology that feeds measured numbers back into
`../py-simulation/docs/mcu.md` (`mcu.calibrations`).

## Pipeline

```
AudioInputTDM (SAI1, ICS-52000 startup patch)
  └── even channels 0,2,..,14 = mic 0..7 (16-bit high word of 32-bit slot)
        └── AudioCapture (N-ch ring buffer, frame=1024, hop=512)
              └── loop(): per mic  Hann → arm_rfft_fast_f32 → PHAT normalize
                    └── SrpPhat::Processor::process() → az/el, p2m, gate
```

Composition lives in the sketch (`src/main.cpp`); `lib/` provides the
app-agnostic pieces per the README rules:

| Module | Concern |
|---|---|
| `AudioCapture` | audio-graph sink → overlapping N-channel float frames |
| `Dsp` | Hann window, f32 RFFT wrapper, PHAT normalization |
| `SrpPhat` | steering tables + power map → az/el + detection gate |
| `CycleBench` | DWT cycle counter + stats |
| `include/ArrayGeometry.hpp` | hand-maintained mic XYZ tables (edit to match build) |

## Conventions (shared with py-simulation)

- Array frame: **+z = boresight**, mics in x/y plane(s). Elevation is the
  polar angle from +z (0 = boresight, 90 = array plane). Direction unit
  vector `d = [sin e cos a, sin e sin a, cos e]`.
- Steering delay `τ[m][d] = (pos_m · d) / c`; steering phase `e^{-jωτ}`;
  `srp[d] = Σ_k |Σ_m X[m][k] · e^{-jω_k τ[m][d]}|²` after PHAT whitening
  `X ← X/(|X|+ε)`.
- Grid: inclusive endpoints à la `arange(min, max + res/2, res)`; a
  full-circle azimuth span drops the duplicate ±180° seam point.
- fs is the *actual* Teensy rate `AUDIO_SAMPLE_RATE_EXACT` = 44117.647 Hz,
  not the sim's 48 kHz. Delays are in seconds, so only bin frequencies move.
- Samples are the 16-bit high word of the 24-bit ICS-52000 slot. Enough for
  slice 1: PHAT discards magnitude anyway. Full 24-bit recombine (even+odd
  TDM channel) is a possible later upgrade.

## The load-bearing constraint: steering-table memory

The sim precomputes `phase[f, m, d]` (complex64). On the MCU that is
`n_bins · n_mics · n_dirs · 8 B`, streamed once per frame - both too big and
bandwidth-bound:

| config (100–1000 Hz, fft 1024 → 21 bins) | dirs | full table | recurrence |
|---|---|---|---|
| 5 mics, hemisphere @10° | 360 | 295 KB | 28 KB |
| 8 mics, hemisphere @10° | 360 | 472 KB | 45 KB |
| 8 mics, hemisphere @6°  | 960 | 1.26 MB | 120 KB |
| 16 mics, hemisphere @6° | 960 | 2.52 MB | 240 KB |

RAM budget: 512 KB RAM1 (DTCM, statics) + 512 KB RAM2 (OCRAM2: DMAMEM +
heap). The full table only fits for small grids.

**Recurrence kernel (the default).** Per (mic, dir) store only
`base = e^{-jω_first τ}` and `inc = e^{-jΔω τ}` (16 B), and rotate across
bins in registers: `ph ← ph · inc`. Memory ÷(n_bins/2), compute-bound
instead of bandwidth-bound, ~2 effective cmacs per (bin, mic, dir). f32
drift over ≤64 bins is negligible (measured parity vs full table: ~5e-7
max relative power-map error).

The full-table kernel is kept as the correctness reference and as the
*bandwidth-bound calibration workload* the sim's MCU model assumes.

Both tables are built in `init()` for the launch-selected geometry/mic
count/grid - the only allocation site; `process()` is allocation-free.

## Detection gate: must be calibrated per array

Measured on synthetic data (host + device): with the small ring
(r = 8.5 cm) and 100–1000 Hz, clean-signal peak-to-mean over the hemisphere
grid is only **~1.6 dB** (broad beam: aperture ≪ λ), while noise-only
frames reach ~1.9 dB. The dual-ring 16-mic geometry gives ~3.0 dB signal vs
~2.0 dB noise. The sim's 5 dB default assumes its much larger geometry and
4 kHz band. Consequences:

- `peak_to_mean_threshold_db` defaults to 3 dB but is essentially
  informational for the small array; the raw p2m is always printed.
- Proper gating needs either a bigger aperture/band, PSR with mainlobe
  exclusion (sim's `peak_to_sidelobe`), or temporal integration -
  **open item**, calibrate against the live noise floor.

## Benchmarks → `mcu.calibrations`

`make build TEST=bench-dsp && make upload TEST=bench-dsp` - runs with **no
mics attached** and prints every table below; `make monitor` to capture.
Mapping to `py-simulation` config (`mcu.calibrations.<target>`):

| bench section | calibration field |
|---|---|
| `rfft_cycles` table (256…4096) | `rfft_cycles: {N: median}` |
| steering rows, `cmacs/cycle` (full-table = the model's workload; recurrence = what we actually run) | `steering_cmacs_per_cycle` |
| `region_bytes_per_cycle` rows (dtcm / ocram2 / flash_xip) | `region_bytes_per_cycle` |
| `sqrtf` / `fdiv` per-op | `sqrt_cycles` / `div_cycles` |
| `[perf]` line in `main` (audio ISR % + scheduling) | `overhead_cycles_per_frame` |

PSRAM rows are absent (chips not fitted); add a PSRAM streaming test if
they ever are.

The bench also validates correctness on synthetic plane waves (exact
fractional delay injected in the frequency domain): clean max angular error
≈ 2.8° on a 10° grid with 8 mics, ≈ 6° with the 5-mic partial ring; and
checks recurrence-vs-full-table parity.

## Live pipeline (`main` env)

Launch prompts: geometry (from `ArrayGeometry.hpp`), mic count (1–8, one
TDM bus), grid resolution (6/10/15°), kernel. Prints DOA at 5 Hz and every
2 s a `[perf]` line: per-stage cycles (fft+phat / steering / peak), average
and max total vs the frame budget (`hop/fs · F_CPU` = ~6.96 M cycles at
600 MHz), capture overruns, audio-ISR load, audio memory high-water.

Defaults: fft 1024 (43 Hz bins, 23 ms window), hop 512 (11.6 ms), band
100–1000 Hz (bins 3–23), front hemisphere. Change the `k`-constants at the
top of `src/main.cpp`.

## Future work

- PSR (peak-to-sidelobe with mainlobe exclusion) gate; temporal smoothing
  of the DOA track.
- TDM2/SAI2 bring-up with the same BCLK-warmup patch → 16 mics.
- 24-bit sample recombine; log-mel features + C2 telemetry stage.
- If tables ever outgrow RAM: PSRAM (capacity, not bandwidth - the
  recurrence kernel keeps the hot loop compute-bound anyway).
