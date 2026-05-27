# Evaluation Metrics

Metrics are computed frame-by-frame and aggregated into a `MetricsResult` dataclass. The summary appears in the terminal output and is saved to CSV in sweep runs.

## Per-Frame Metrics

| Metric | Function | Description |
|---|---|---|
| Angular error | `angular_error()` | Great-circle angle (deg) between true and estimated DOA for detected frames |
| PSR | `peak_to_sidelobe_ratio()` | `10·log₁₀(peak / max_sidelobe)` — excludes 3-pixel radius around peak |
| Beamwidth | `beamwidth_3db()` | Geometric mean of azimuth/elevation 3 dB widths |
| Detected | P2M/PSR gate | Boolean flag for each frame |

## Aggregate Metrics

| Field | Description |
|---|---|
| `detection_rate` | `n_detected / n_total` |
| `mean_angular_error_deg` | Mean of angular errors (detected frames only) |
| `std_angular_error_deg` | Standard deviation of angular errors |
| `max_angular_error_deg` | Maximum angular error |
| `mean_psr_db` | Mean peak-to-sidelobe ratio across all frames |
| `mean_beamwidth_deg` | Mean 3 dB beamwidth |
| `n_detected` | Number of frames passing the detection gate |
| `n_total` | Total number of frames processed |

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
| `mean_angular_error_deg` | `MetricsResult.mean_angular_error_deg` |
| `std_angular_error_deg` | `MetricsResult.std_angular_error_deg` |
| `max_angular_error_deg` | `MetricsResult.max_angular_error_deg` |
| `mean_psr_db` | `MetricsResult.mean_psr_db` |
| `mean_beamwidth_deg` | `MetricsResult.mean_beamwidth_deg` |
| `n_detected` | `MetricsResult.n_detected` |
| `n_total` | `MetricsResult.n_total` |
| `run_time_s` | Wall-clock time for that configuration |
