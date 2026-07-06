# Evaluation Metrics

Metrics are computed frame-by-frame and aggregated into a `MetricsResult` dataclass. The summary appears in the terminal output, is cached with results, and is saved to CSV in sweep runs.

## Per-Frame Metrics

| Metric | Function | Description |
|---|---|---|
| Angular error | `angular_error()` | Great-circle angle (deg) between true and estimated DOA for detected frames |
| PSR | `peak_to_sidelobe_ratio()` | `10·log₁₀(peak / max_sidelobe)` — excludes a 3-pixel radius around the peak; the exclusion wraps across the azimuth seam on full-circle grids (`wrap_az`) |
| Beamwidth | `beamwidth_3db()` | Geometric mean of azimuth/elevation 3 dB widths |
| Mirror suppression | `front_back_metrics()` | SRP at the true lobe over SRP at its mirror about the ring plane `(az, 180° − el)`, in dB. Positive = mirror rejected |
| Confused | `front_back_metrics()` | True when the global SRP peak is spherically closer to the mirror direction than to the truth |
| Detected | P2M/PSR gate | Boolean flag per frame |

## Aggregate Metrics

| Field | Description |
|---|---|
| `detection_rate` | `n_detected / n_total` |
| `mean/std/max_angular_error_deg` | Statistics over detected frames only; **NaN when nothing was detected** (an error of 0.0 would read as "perfect") |
| `mean_psr_db` | Mean peak-to-sidelobe ratio across all frames |
| `mean_beamwidth_deg` | Mean 3 dB beamwidth |
| `front_back_confusion_rate` | Fraction of frames whose global peak landed on the wrong hemisphere. **NaN unless the search grid spans past el = 90°** (use `coverage: full_sphere`) |
| `mean_mirror_suppression_db` | Mean mirror-lobe suppression; ~0 dB for a planar array (which cannot break the symmetry), NaN for front-only grids |
| `n_detected` / `n_total` | Gate statistics |

## Front/Back Metrics — Why They Exist

The dual-ring axial separation exists solely to break front/back mirror symmetry. These metrics are the only way to score that design choice: sweep `array.ring_spacing` with `srpphat.search.coverage: full_sphere` (`config/sweep/ring_spacing_frontback.yaml`) and watch `mean_mirror_suppression_db` grow with spacing while `front_back_confusion_rate` falls.

**Comparability caveat**: PSR and beamwidth values shift when the grid coverage changes (a bigger map has a different sidelobe field). Only compare these metrics between runs with identical `coverage`.

## Detection Gate

The `detection_rate` is the primary metric for assessing system viability. Frames that fail the gate:
- Are excluded from angular error statistics (avoids averaging in large outlier values)
- Are shown in red in DOA tracking plots
- Still contribute to PSR and beamwidth means (these are computed regardless)

This is intentional — a real system would suppress reports when confidence is low, not report garbage bearings.

## CSV Column Reference (Sweep Output)

When running `sweep.py`, the output CSV contains all swept parameters plus:

| Column | Source |
|---|---|
| `detection_rate` | `MetricsResult.detection_rate` |
| `mean/std/max/min_angular_error_deg` | `MetricsResult` |
| `mean_psr_db`, `std_psr_db` | `MetricsResult` |
| `mean_beamwidth_deg` | `MetricsResult` |
| `front_back_confusion_rate` | `MetricsResult` (NaN unless full-sphere/back coverage) |
| `mean_mirror_suppression_db` | `MetricsResult` (NaN unless full-sphere/back coverage) |
| `n_detected`, `n_total`, `n_frames` | Gate statistics |
| `effective_snr_db` | EIN-budget SNR of the run (see [snr.md](snr.md)) |
| `run_time_s` | Wall-clock time for that configuration |
| `config_hash` | Fingerprint linking the row to the cached run |

Note: the two front/back columns were added later — resuming an old CSV written before they existed will misalign columns; start a fresh sweep output instead.

## Decision-Grade Summaries

Raw sweep CSVs answer "what happened at each point"; `src/analysis` turns them into decisions:

- `run_range_curve(config, distances, n_seeds)` → detection rate / error / mirror suppression vs distance, seed-averaged
- `range_at_rate(curve, 0.9)` → interpolated distance where detection crosses 90 % (NaN when the curve never crosses inside the tested range)
- `python -m src.compare` → side-by-side geometry report with `range@90%`, `range@50%`, error at 30 m, mirror suppression, and MCU feasibility ([analysis.md](analysis.md))
