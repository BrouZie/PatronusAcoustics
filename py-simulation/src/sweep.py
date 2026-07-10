"""
Parameter sweep runner — runs simulations over a Cartesian product of config
values using parallel workers, writes incremental results to CSV, and supports
checkpoint/resume.

Usage:
    python -m src.sweep config/sweep/detection_range.yaml
    python -m src.sweep config/sweep/detection_range.yaml --dry-run
    python -m src.sweep config/sweep/detection_range.yaml --workers 8
    python -m src.sweep config/sweep/detection_range.yaml --resume
"""

import argparse
import copy
import io
import itertools
import json
import os
import sys
import time
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

import csv
import numpy as np
import yaml

from .analysis.mcu_requirements import evaluate_from_config
from .config import Config, config_hash, deep_merge, parse_dotted_key
from .geometry import make_array
from .main import run_simulation


METRIC_FIELDS = [
    "detection_rate",
    "mean_angular_error_deg",
    "std_angular_error_deg",
    "max_angular_error_deg",
    "min_angular_error_deg",
    "mean_psr_db",
    "std_psr_db",
    "mean_beamwidth_deg",
    "front_back_confusion_rate",
    "mean_mirror_suppression_db",
    "n_detected",
    "n_total",
    "n_frames",
    "effective_snr_db",
    "run_time_s",
    "config_hash",
    # MCU requirement columns (analytic, appended so old CSVs stay a prefix)
    "mcu_required_mhz",
    "mcu_required_ram_mb",
    "mcu_link_kbps",
    "mcu_recommended",
    "mcu_target",
    "mcu_target_ok",
]


def _mcu_metrics(config):
    """Analytic MCU requirement columns for one sweep row.

    `mcu_target`/`mcu_target_ok` name and judge the first configured
    target profile, so the boolean is always interpretable even when
    sweeps run with different target lists.
    """
    n_mics = make_array(config.array).n_mics
    try:
        report = evaluate_from_config(config, n_mics)
    except KeyError:
        return {"mcu_recommended": None, "mcu_target": None,
                "mcu_target_ok": None}
    req = report.requirements
    first = report.verdicts[0] if report.verdicts else None
    return {
        "mcu_required_mhz": round(req.required_mhz, 1),
        "mcu_required_ram_mb": round(req.ram_bytes / 2**20, 3),
        "mcu_link_kbps": round(req.link_bps / 1e3, 1),
        "mcu_recommended": report.recommended,
        "mcu_target": first.profile.name if first else None,
        "mcu_target_ok": first.fits if first else None,
    }


def _make_results_dir():
    p = Path(__file__).resolve().parent.parent / "results"
    p.mkdir(parents=True, exist_ok=True)
    return p


def parse_sweep_config(path):
    with open(path) as f:
        data = yaml.safe_load(f)

    base_config = data.get("base_config")
    if base_config is None:
        sys.exit("Error: sweep config must include 'base_config' key")

    params = data.get("sweep", {})
    if not params:
        sys.exit("Error: sweep config must include 'sweep' key with parameters")

    overrides = data.get("overrides", {}) or {}
    output_raw = data.get("output")  # None → auto-generate timestamped path

    return base_config, params, overrides, output_raw


def _fmt(v):
    if isinstance(v, float):
        return f"{v:.4g}"
    return str(v)


def _nested_overrides(overrides):
    """Convert flat dotted-key overrides to nested dicts."""
    result = {}
    for ok, ov in overrides.items():
        if '.' in str(ok):
            deep_merge(result, parse_dotted_key(str(ok), ov))
        else:
            result[ok] = ov
    return result


def _run_combo(keys, combo, base_dict, overrides):
    """Execute a single sweep combination."""
    try:
        combo_nested = {}
        for k, v in zip(keys, combo):
            deep_merge(combo_nested, parse_dotted_key(k, v))

        d = copy.deepcopy(base_dict)
        deep_merge(d, _nested_overrides(overrides))
        deep_merge(d, combo_nested)
        config = Config.from_dict(d)

        h = config_hash(config)

        t0 = time.time()
        with redirect_stdout(io.StringIO()):
            results = run_simulation(config, run_dir=None, profile=False)
        elapsed = time.time() - t0
        metrics = results["metrics"]

        row = dict(zip(keys, combo))
        row["config_hash"] = h
        row["detection_rate"] = metrics.detection_rate
        row["mean_angular_error_deg"] = metrics.mean_angular_error_deg
        row["std_angular_error_deg"] = metrics.std_angular_error_deg
        row["max_angular_error_deg"] = metrics.max_angular_error_deg
        row["mean_psr_db"] = metrics.mean_psr_db
        row["mean_beamwidth_deg"] = metrics.mean_beamwidth_deg
        row["front_back_confusion_rate"] = metrics.front_back_confusion_rate
        row["mean_mirror_suppression_db"] = metrics.mean_mirror_suppression_db
        row["n_detected"] = metrics.n_detected
        row["n_total"] = metrics.n_total
        row["run_time_s"] = round(elapsed, 3)

        # Extra metrics
        n_frames = results.get("n_frames", 0)
        row["n_frames"] = n_frames
        frame_snrs = results.get("frame_snrs", None)
        if frame_snrs is not None and len(frame_snrs) > 0:
            row["effective_snr_db"] = round(float(frame_snrs[0]), 2)
        else:
            row["effective_snr_db"] = None

        if len(metrics.angular_errors_deg) > 0:
            valid = metrics.angular_errors_deg[~np.isnan(metrics.angular_errors_deg)]
            row["min_angular_error_deg"] = float(np.min(valid)) if len(valid) > 0 else None
        else:
            row["min_angular_error_deg"] = None

        if len(metrics.peak_to_sidelobe_ratios_db) > 0:
            row["std_psr_db"] = float(np.std(metrics.peak_to_sidelobe_ratios_db))
        else:
            row["std_psr_db"] = None

        row.update(_mcu_metrics(config))

        return row
    except Exception as e:
        import traceback
        return {"_error": str(e), "_traceback": traceback.format_exc(), "_combo": combo}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Parameter sweep runner")
    parser.add_argument("config", help="Sweep YAML configuration file")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print parameter combinations without running",
    )
    parser.add_argument(
        "--workers", type=int, default=None,
        help="Number of parallel worker processes (default: CPU count)",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Resume from last checkpoint (skips completed combinations)",
    )
    args = parser.parse_args(argv)

    base_path, params, overrides, output_raw = parse_sweep_config(args.config)

    if output_raw is not None:
        output_path = output_raw
    else:
        stem = Path(args.config).stem
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = _make_results_dir() / f"{stem}_{ts}"
        output_path = str(out_dir / "sweep_results.csv")

    param_items = list(params.items())
    keys = [item[0] for item in param_items]
    values_lists = [item[1] for item in param_items]
    combos = list(itertools.product(*values_lists))

    n = len(combos)
    print(f"Sweep: {n} combinations over {len(keys)} parameters")
    for k, v_list in param_items:
        print(f"  {k}: {v_list}")

    if args.dry_run:
        print()
        header = "  " + "  ".join(f"{k:>20}" for k in keys)
        print(header)
        print("  " + "-" * len(header))
        for combo in combos:
            print("  " + "  ".join(f"{_fmt(v):>20}" for v in combo))
        return 0

    with open(base_path) as f:
        base_dict = yaml.safe_load(f)

    # Load checkpoint state for resume
    state_path = Path(output_path + ".state.json")
    completed_hashes = set()
    if args.resume and state_path.exists():
        with open(state_path) as f:
            state = json.load(f)
        completed_hashes = {entry["hash"] for entry in state.get("completed", [])}
        print(f"Resume: {len(completed_hashes)} already completed, {n - len(completed_hashes)} remaining")
    elif args.resume:
        print("Resume: no checkpoint found, starting fresh")

    # Pre-compute hashes for all combos to check which are completed
    pending = []
    skipped = 0
    for combo in combos:
        combo_nested = {}
        for k, v in zip(keys, combo):
            deep_merge(combo_nested, parse_dotted_key(k, v))
        d = copy.deepcopy(base_dict)
        deep_merge(d, _nested_overrides(overrides))
        deep_merge(d, combo_nested)
        config = Config.from_dict(d)
        h = config_hash(config)
        if h in completed_hashes:
            skipped += 1
            continue
        pending.append(combo)

    if skipped:
        print(f"Skipping {skipped} already-completed combinations")

    if not pending:
        print("All combinations already completed!")
        return 0

    # Prepare output CSV and state file
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = list(keys) + METRIC_FIELDS
    is_new = not out.exists()

    if is_new or not args.resume:
        with open(out, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
    else:
        # Appending rows under a stale header silently misaligns columns
        # (e.g. a CSV started before the MCU columns existed).
        with open(out, newline="") as f:
            existing = next(csv.reader(f), [])
        if existing != fieldnames:
            sys.exit(
                f"Error: cannot resume into {out}: its header does not match "
                f"the current sweep columns (schema changed since the sweep "
                f"started). Re-run without --resume to start a fresh CSV."
            )

    if args.resume and state_path.exists():
        with open(state_path) as f:
            state = json.load(f)
    else:
        state = {
            "sweep_config": str(Path(args.config).resolve()),
            "started": datetime.now(timezone.utc).isoformat(),
            "output_path": str(out.resolve()),
            "completed": [],
        }

    print(f"Processing {len(pending)} combination(s) sequentially")

    total_pending = len(pending)
    results = []

    for done_count, combo in enumerate(pending, 1):
        try:
            row = _run_combo(keys, combo, copy.deepcopy(base_dict), overrides)
        except Exception as e:
            row = {"_error": str(e), "_combo": combo}

        if "_error" in row:
            tags = ", ".join(f"{k}={_fmt(v)}" for k, v in zip(keys, combo))
            print(f"[{done_count}/{total_pending}] FAILED {tags}: {row['_error']}")
            continue

        tags = ", ".join(f"{k}={_fmt(v)}" for k, v in row.items() if k in keys)
        det_str = f"{row['detection_rate']:.0%}" if row.get('n_total', 0) > 0 else "N/A"
        err_str = f"{row.get('mean_angular_error_deg', 0):.1f}°" if row.get('mean_angular_error_deg') is not None else "N/A"
        print(f"[{done_count}/{total_pending}] {tags}  det={det_str}  err={err_str}  {row.get('run_time_s', 0):.1f}s")

        with open(out, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writerow({k: row.get(k) for k in fieldnames})

        h = row.get("config_hash", "")
        combo_values = [row.get(k) for k in keys]
        state["completed"].append({"combo": combo_values, "hash": h, "status": "ok"})
        with open(state_path, "w") as f:
            json.dump(state, f, indent=2)

        results.append(row)

    print(f"\nResults → {out.resolve()}")
    print(f"\n=== Sweep Complete: {len(results)}/{total_pending} successful ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
