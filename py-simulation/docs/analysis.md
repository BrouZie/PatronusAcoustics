# Analysis Tools — Decision-Grade Outputs

`src/analysis/` and `src/compare.py` turn simulation runs into the artifacts a fabrication decision is made on. All heavy computation reuses the versioned results cache, so repeated/overlapping analyses are cheap.

## Detection-Range Curves (`src/analysis/detection_range.py`)

```python
from src.analysis import run_range_curve, range_at_rate
from src.config import Config

base = Config.from_yaml("config/default.yaml")
curve = run_range_curve(base, distances=[10, 20, 30, 50, 70], n_seeds=3)
print(range_at_rate(curve, 0.9))   # distance where detection crosses 90 %
```

- The drone is placed **stationary** at each distance (the base config's trajectory is cleared — a moving trajectory would make "distance" ill-defined) and `signal.snr_db` is forced to `None` so SNR follows the EIN budget.
- Each (distance, seed) point is an independent config → cached individually, resumable for free.
- `range_at_rate` interpolates the crossing; NaN when the curve never crosses inside the tested distances (always above → true range beyond the tested span; always below → target unreachable).

## Geometry Comparison Report (`src/compare.py`)

```bash
# The standing fabrication trade (dual ring at 3 spacings vs 16-mic planar ring)
make compare-baseline          # ~tens of minutes cold, cheap when cached
make compare-baseline-quick    # coarse/fast variant

# Custom comparison
python -m src.compare config/compare/dual_ring_s20.yaml my_candidate.yaml \
    --distances 10 20 30 50 70 --seeds 3 [--quick] [--base config/default.yaml]
```

Each positional file is a thin override merged onto `--base` (typically just an `array:` section; changing `array.type` replaces the section wholesale). Compare mode forces full-sphere search so the front/back metrics are populated.

Output under `results/compare_<timestamp>/`:

| File | Content |
|---|---|
| `report.md` | Summary table: mics, `range@90%`, `range@50%`, error @ 30 m, mirror suppression, **MCU feasibility for the first configured target** |
| `detection_rate_vs_range.png` | One line per geometry, 90 %/50 % guides, shaded 10–50 m pitch target |
| `angular_error_vs_range.png` / `mirror_suppression_vs_range.png` | Accuracy and front/back rejection vs distance |
| `beampattern_cuts.png` | Analytical boresight cuts at 400/1000/2000 Hz per geometry |
| `geometries.png` | 3D mic-position scatter per candidate |

## MCU Feasibility (`src/analysis/mcu_requirements.py`)

Per-stage requirements (SRP-PHAT + log-mel + uplink), multi-target verdicts with named binding constraints, memory placement/bandwidth modeling, and the mic TDM ingest check — see [mcu.md](mcu.md) for the cycle model, calibration hooks, and profile provenance.

The compare report evaluates this against each geometry's **station** search config (not the full-sphere research grid). Key standing result: the default research grid (±60° @ 2°, 4 kHz band, 16 mics) is far beyond any single-MCU station — the on-station grid must be much coarser (higher `resolution_deg`, lower `max_freq`, higher `min_freq`).

## Two-Station Triangulation (`src/analysis/triangulation.py`)

Geometric Monte Carlo — no audio simulation. A single station only resolves a bearing; C2 fuses two bearings into a 3D position. Feed the single-station bearing error measured by a range curve (`curve.angular_error_deg` at the range of interest) in as `--sigma`:

```bash
python -m src.analysis.triangulation --baseline 40 --sigma 3 --extent 100 --altitude 30
```

Produces a heatmap of RMS 3D position error over the coverage area for two stations at the given baseline. `triangulate(station_positions, bearings)` (least-squares ray intersection) is also importable for C2 prototyping and supports ≥ 2 stations.

## What Is Deliberately Not Modeled Here

Two-station *acoustic* co-simulation, PPS/clock-skew effects, and the CNN/log-mel classification pipeline are out of scope — the triangulation module derisks the geometry/error question at a fraction of the cost, and classification belongs to the C2 codebase.
