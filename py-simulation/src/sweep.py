"""
Parameter sweep runner — runs simulations over a Cartesian product of config
values and writes per-run aggregate metrics to a CSV.

Usage:
    python -m src.sweep config/sweep_ground.yaml
    python -m src.sweep config/sweep_ground.yaml --dry-run
"""

import argparse
import copy
import csv
import io
import itertools
import sys
import time
from contextlib import redirect_stdout
from pathlib import Path

import yaml

from .config import Config, deep_merge, parse_dotted_key
from .main import run_simulation


METRIC_FIELDS = [
    "detection_rate",
    "mean_angular_error_deg",
    "std_angular_error_deg",
    "max_angular_error_deg",
    "mean_psr_db",
    "mean_beamwidth_deg",
    "n_detected",
    "n_total",
    "run_time_s",
]


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
    output = data.get("output", str(_make_results_dir() / "sweep_results.csv"))

    return base_config, params, overrides, output


def _fmt(v):
    if isinstance(v, float):
        return f"{v:.4g}"
    return str(v)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Parameter sweep runner")
    parser.add_argument("config", help="Sweep YAML configuration file")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print parameter combinations without running",
    )
    args = parser.parse_args(argv)

    base_path, params, overrides, output_path = parse_sweep_config(args.config)

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

    rows = []
    for i, combo in enumerate(combos):
        combo_nested = {}
        for k, v in zip(keys, combo):
            deep_merge(combo_nested, parse_dotted_key(k, v))

        d = copy.deepcopy(base_dict)
        deep_merge(d, overrides)
        deep_merge(d, combo_nested)
        config = Config.from_dict(d)

        tags = ", ".join(f"{k}={_fmt(v)}" for k, v in zip(keys, combo))
        print(f"[{i+1}/{n}] {tags} ...", end=" ", flush=True)

        t0 = time.time()
        try:
            with redirect_stdout(io.StringIO()):
                results = run_simulation(config, run_dir=None, profile=False)
            elapsed = time.time() - t0
            metrics = results["metrics"]

            row = dict(zip(keys, combo))
            row["detection_rate"] = metrics.detection_rate
            row["mean_angular_error_deg"] = metrics.mean_angular_error_deg
            row["std_angular_error_deg"] = metrics.std_angular_error_deg
            row["max_angular_error_deg"] = metrics.max_angular_error_deg
            row["mean_psr_db"] = metrics.mean_psr_db
            row["mean_beamwidth_deg"] = metrics.mean_beamwidth_deg
            row["n_detected"] = metrics.n_detected
            row["n_total"] = metrics.n_total
            row["run_time_s"] = round(elapsed, 3)

            rows.append(row)
            det_str = f"{metrics.detection_rate:.0%}" if not (metrics.n_total == 0) else "N/A"
            print(f"det={det_str}  err={metrics.mean_angular_error_deg:.1f}°  {elapsed:.1f}s")
        except Exception as e:
            print(f"FAILED: {e}")
            import traceback
            traceback.print_exc()

    if rows:
        fieldnames = list(keys) + METRIC_FIELDS
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nResults → {out.resolve()}")

    print(f"\n=== Sweep Complete: {len(rows)}/{n} successful ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
