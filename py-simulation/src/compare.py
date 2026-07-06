"""Geometry comparison report — the fabrication-decision artifact.

Usage:
    python -m src.compare config/compare/dual_ring_s20.yaml \\
                          config/compare/single_ring_16.yaml \\
                          --distances 10 20 30 50 70

Each positional file is a thin override merged onto --base (default
config/default.yaml), typically changing only the `array:` section. Output:
a report.md plus PNGs under --out. Runs are cached by config hash, so
re-running with overlapping settings is cheap.
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import yaml

from .analysis import (
    RangeCurve,
    estimate_from_config,
    range_at_rate,
    run_range_curve,
)
from .analysis.mcu_requirements import evaluate_from_config as mcu_evaluate
from .beampattern import array_response
from .config import Config, deep_merge
from .geometry import make_array

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


PITCH_TARGET_RANGE = (10.0, 50.0)  # single-station goal from the pitch


def _load_configs(base_path, fragment_paths, quick):
    """Merge each fragment onto the base and force compare-mode settings.

    A fragment changing the array *type* replaces the whole array section
    (deep-merging across union variants would mix incompatible keys).
    """
    with open(base_path) as f:
        base_dict = yaml.safe_load(f) or {}

    configs = []
    for frag in fragment_paths:
        with open(frag) as f:
            frag_dict = yaml.safe_load(f) or {}
        merged = {k: (dict(v) if isinstance(v, dict) else v)
                  for k, v in base_dict.items()}
        frag_array = frag_dict.get("array")
        if frag_array and frag_array.get("type", "dual_ring") != \
                merged.get("array", {}).get("type", "dual_ring"):
            merged["array"] = frag_dict.pop("array")
        deep_merge(merged, frag_dict)
        cfg = Config.from_dict(merged)
        station_cfg = cfg  # pre-override: what the MCU would actually run
        overrides = {
            "srpphat": {"search": {
                "coverage": "full_sphere",
                "resolution_deg": 10.0 if quick else 6.0,
            }},
            "signal": {"duration": 2.0 if quick else 4.0},
            "output": {
                "save_animation": False, "save_3d_animation": False,
                "save_figures": False, "save_data": False,
            },
        }
        configs.append((Path(frag).stem, cfg.merge(overrides), station_cfg))
    return configs


def _plot_curves(curves, attr, ylabel, title, out_path, target_lines=()):
    fig, ax = plt.subplots(figsize=(9, 5))
    for curve in curves:
        ax.plot(curve.distances, getattr(curve, attr), "o-", label=curve.label)
    ax.axvspan(*PITCH_TARGET_RANGE, alpha=0.08, color="green",
               label="pitch target 10–50 m")
    for level, style in target_lines:
        ax.axhline(level, color="gray", linestyle=style, alpha=0.6)
    ax.set_xlabel("Distance (m)")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def _plot_geometries(named_arrays, out_path):
    n = len(named_arrays)
    fig = plt.figure(figsize=(5 * n, 5))
    for i, (label, array) in enumerate(named_arrays):
        ax = fig.add_subplot(1, n, i + 1, projection="3d")
        p = array.positions
        ax.scatter(p[:, 0], p[:, 1], p[:, 2], s=40)
        ext = max(float(np.max(np.abs(p))), 0.05) * 1.3
        ax.set_xlim(-ext, ext); ax.set_ylim(-ext, ext); ax.set_zlim(-ext, ext)
        ax.set_title(f"{label} ({array.n_mics} mics)")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def _plot_beampattern_cuts(named_arrays, out_path, freqs=(400.0, 1000.0, 2000.0)):
    """Boresight-steered cuts through the xz-plane (angle from boresight)."""
    theta = np.radians(np.linspace(-90, 90, 721))
    az = np.where(theta < 0, np.pi, 0.0).reshape(-1, 1)
    el = np.abs(theta).reshape(-1, 1)

    fig, axes = plt.subplots(1, len(freqs), figsize=(6 * len(freqs), 4.5),
                             sharey=True)
    for ax, f in zip(np.atleast_1d(axes), freqs):
        for label, array in named_arrays:
            B = array_response(array, f, az, el)[:, 0]
            ax.plot(np.degrees(theta), 10 * np.log10(np.maximum(B, 1e-15)),
                    lw=1.2, label=label)
        ax.axhline(-3, color="red", ls="--", alpha=0.4)
        ax.set_title(f"{f:.0f} Hz")
        ax.set_xlabel("Angle from boresight (deg)")
        ax.set_ylim(-40, 2)
        ax.grid(True, alpha=0.3)
    np.atleast_1d(axes)[0].set_ylabel("Response (dB)")
    np.atleast_1d(axes)[0].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def _err_at(curve: RangeCurve, distance: float) -> float:
    idx = int(np.argmin(np.abs(curve.distances - distance)))
    return float(curve.angular_error_deg[idx])


def _fmt(v, unit="", nd=1):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{v:.{nd}f}{unit}"


def _mcu_feasibility_lines(named_arrays, station_configs):
    """Per-target MCU verdict section (only when mcu.enabled in the base)."""
    if not any(cfg.mcu.enabled for cfg in station_configs):
        return []

    lines = [
        "## MCU feasibility",
        "",
        "Per-stage requirements (SRP-PHAT + log-mel cost model + uplink) for "
        "the station's own search grid, matched against each target profile. "
        "A verdict fails if compute, SRAM, flash, **or** mic TDM ingest "
        "(SAI/I2S buses × slots × bit clock) does not fit — an MCU that "
        "cannot physically connect the mics is never recommended. "
        "See docs/mcu.md for formulas and profile provenance.",
        "",
    ]
    for (label, array), cfg in zip(named_arrays, station_configs):
        if not cfg.mcu.enabled:
            continue
        report = mcu_evaluate(cfg, array.n_mics)
        req = report.requirements
        lines += [
            f"### {label} ({array.n_mics} mics)",
            "",
            f"Required: {req.required_mhz:.0f} MHz (at 1 MAC/cycle, "
            f"{req.headroom_pct:.0f}% headroom) · "
            f"{req.ram_bytes / 2**20:.2f} MB RAM · "
            f"{req.flash_bytes / 2**10:.0f} KB flash · "
            f"{req.link_bps / 1e3:.1f} kbps uplink",
            "",
            "| Stage | RAM | Flash | MMACs/s |",
            "|---|---|---|---|",
        ]
        for s in req.stages:
            lines.append(
                f"| {s.name} | {s.ram_bytes / 2**20:.3f} MB "
                f"| {s.flash_bytes / 2**10:.1f} KB "
                f"| {s.macs_per_second / 1e6:.1f} |"
            )
        lines += ["", "| Target | Verdict |", "|---|---|"]
        for v in report.verdicts:
            lines.append(f"| {v.profile.name} | {v.summary()} |")
        rec = report.recommended or "none of the configured targets"
        lines += ["", f"**Recommended:** {rec}", ""]
    return lines


def _write_report(out_dir, curves, named_arrays, station_configs, args):
    rows = []
    for curve, (label, array), station_cfg in zip(
            curves, named_arrays, station_configs):
        budget = estimate_from_config(station_cfg, array.n_mics)
        rows.append((
            label,
            array.n_mics,
            _fmt(range_at_rate(curve, 0.9), " m"),
            _fmt(range_at_rate(curve, 0.5), " m"),
            _fmt(_err_at(curve, 30.0), "°"),
            _fmt(float(np.nanmean(curve.mirror_suppression_db)), " dB"),
            budget.summary(),
        ))

    lines = [
        "# Geometry Comparison Report",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"Distances: {', '.join(f'{d:g}' for d in args.distances)} m · "
        f"{args.seeds} seed(s) per point · "
        f"{'quick' if args.quick else 'full'} mode (full-sphere search)",
        "",
        "SNR at each distance follows from the EIN budget "
        "(drone SPL − spreading − absorption − mic noise floor); the drone "
        "is stationary at the configured bearing.",
        "",
        "| Geometry | Mics | Range@90% | Range@50% | Err@30 m | Mirror supp. | MCU (H753) |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append("| " + " | ".join(str(c) for c in r) + " |")
    lines += [
        "",
        "Range@X% = interpolated distance where detection rate crosses X%; "
        "'—' means the curve never crossed inside the tested distances. "
        "MCU column: phase-table memory and est. frame compute vs the frame "
        "period for the *station's own* search grid (not the research "
        "full-sphere grid used for the curves above).",
        "",
    ]
    lines += _mcu_feasibility_lines(named_arrays, station_configs)
    lines += [
        "![Detection rate](detection_rate_vs_range.png)",
        "![Angular error](angular_error_vs_range.png)",
        "![Mirror suppression](mirror_suppression_vs_range.png)",
        "![Beampattern cuts](beampattern_cuts.png)",
        "![Geometries](geometries.png)",
        "",
    ]
    (out_dir / "report.md").write_text("\n".join(lines))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Geometry comparison report")
    parser.add_argument("configs", nargs="+",
                        help="Override YAMLs (typically just an array: section)")
    parser.add_argument("--base", default="config/default.yaml")
    parser.add_argument("--distances", type=float, nargs="+",
                        default=[10, 20, 30, 50, 70])
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--out", default=None)
    parser.add_argument("--quick", action="store_true",
                        help="2 s runs at 10° resolution for fast iteration")
    args = parser.parse_args(argv)

    if args.out is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        args.out = str(Path(__file__).resolve().parent.parent
                       / "results" / f"compare_{ts}")
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    configs = _load_configs(args.base, args.configs, args.quick)
    named_arrays = [(label, make_array(cfg.array)) for label, cfg, _ in configs]
    station_configs = [station for _, _, station in configs]

    curves = []
    for label, cfg, _ in configs:
        print(f"Geometry: {label}")
        curves.append(run_range_curve(
            cfg, args.distances, n_seeds=args.seeds, label=label,
        ))

    _plot_curves(curves, "detection_rate", "Detection rate",
                 "Detection rate vs range",
                 out_dir / "detection_rate_vs_range.png",
                 target_lines=[(0.9, "--"), (0.5, ":")])
    _plot_curves(curves, "angular_error_deg", "Mean angular error (deg)",
                 "DOA error vs range",
                 out_dir / "angular_error_vs_range.png")
    _plot_curves(curves, "mirror_suppression_db", "Mirror suppression (dB)",
                 "Front/back rejection vs range",
                 out_dir / "mirror_suppression_vs_range.png")
    _plot_geometries(named_arrays, out_dir / "geometries.png")
    _plot_beampattern_cuts(named_arrays, out_dir / "beampattern_cuts.png")
    _write_report(out_dir, curves, named_arrays, station_configs, args)

    print(f"\nReport -> {out_dir / 'report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
