import json
import shutil
from pathlib import Path

import numpy as np

from .manifest import RESULTS_DIR
from ..config import Config, config_hash


CACHE_DIR = RESULTS_DIR / "cache"

# Bump whenever simulation numerics change without a config change (e.g. a
# physics fix): cached results from older versions are then ignored.
# v2: temperature-derived speed of sound, SensorModel mic chain (Phase 1).
# v3: complex64 phase tensor, wrap-aware PSR, front/back metrics (Phase 3).
# v4: ISO 9613-1 absorption fix (h in percent, Kelvin ratios) (Phase 6).
# v5: Pa-referenced calibration (calibrated sources/noise, absolute EIN,
#     Pa→FS sensor output), per-rotor source synthesis, windowed-sinc
#     moving-source delay, mic response + humidity sound speed.
CACHE_SCHEMA_VERSION = 5


def _cache_dir(config: Config) -> Path:
    return CACHE_DIR / f"v{CACHE_SCHEMA_VERSION}" / config_hash(config)


def _meta_path(config: Config) -> Path:
    return _cache_dir(config) / "meta.json"


def _npz_path(config: Config) -> Path:
    return _cache_dir(config) / "results.npz"


def has_cached(config: Config) -> bool:
    return _meta_path(config).exists() and _npz_path(config).exists()


def _numpy_safe(obj):
    if isinstance(obj, np.ndarray):
        return obj
    if isinstance(obj, np.generic):
        return obj.item()
    return obj


def _encode_metrics(metrics) -> dict:
    return {
        "mean_angular_error_deg": float(metrics.mean_angular_error_deg),
        "std_angular_error_deg": float(metrics.std_angular_error_deg),
        "max_angular_error_deg": float(metrics.max_angular_error_deg),
        "mean_psr_db": float(metrics.mean_psr_db),
        "mean_beamwidth_deg": float(metrics.mean_beamwidth_deg),
        "n_detected": int(metrics.n_detected),
        "n_total": int(metrics.n_total),
        "detection_rate": float(metrics.detection_rate),
        "front_back_confusion_rate": float(metrics.front_back_confusion_rate),
        "mean_mirror_suppression_db": float(metrics.mean_mirror_suppression_db),
    }


def _decode_metrics(data: dict):
    from ..metrics import MetricsResult
    return MetricsResult(
        mean_angular_error_deg=data["mean_angular_error_deg"],
        std_angular_error_deg=data["std_angular_error_deg"],
        max_angular_error_deg=data["max_angular_error_deg"],
        mean_psr_db=data["mean_psr_db"],
        mean_beamwidth_deg=data["mean_beamwidth_deg"],
        n_detected=data["n_detected"],
        n_total=data["n_total"],
        detection_rate=data["detection_rate"],
        front_back_confusion_rate=data.get("front_back_confusion_rate", float("nan")),
        mean_mirror_suppression_db=data.get("mean_mirror_suppression_db", float("nan")),
    )


def save_cache(config: Config, results: dict) -> None:
    cdir = _cache_dir(config)
    cdir.mkdir(parents=True, exist_ok=True)

    meta = {
        "config_hash": config_hash(config),
        "n_frames": int(results["n_frames"]),
        "fs": int(results["fs"]),
        "metrics": _encode_metrics(results["metrics"]),
    }

    with open(_meta_path(config), "w") as f:
        json.dump(meta, f, indent=2)

    arrays = {
        "true_doas": results["true_doas"],
        "estimated_doas": results["estimated_doas"],
        "srp_maps": results["srp_maps"],
        "peak_values": results["peak_values"],
        "detections": results["detections"],
        "timestamps": results["timestamps"],
        "frame_snrs": results["frame_snrs"],
        "gate1_rms_db": results.get("gate1_rms_db", np.array([])),
        "gate1_flatness": results.get("gate1_flatness", np.array([])),
        "source_positions": results.get("source_positions", np.array([])),
        "center_samples": results.get("center_samples", np.array([])),
    }

    np.savez(_npz_path(config), **arrays)


def load_cache(config: Config) -> dict | None:
    if not has_cached(config):
        return None

    meta = json.loads(_meta_path(config).read_text())
    arrays = np.load(_npz_path(config))

    results = {
        "true_doas": arrays["true_doas"],
        "estimated_doas": arrays["estimated_doas"],
        "srp_maps": arrays["srp_maps"],
        "peak_values": arrays["peak_values"],
        "detections": arrays["detections"],
        "timestamps": arrays["timestamps"],
        "frame_snrs": arrays["frame_snrs"],
        "gate1_rms_db": arrays.get("gate1_rms_db"),
        "gate1_flatness": arrays.get("gate1_flatness"),
        "source_positions": arrays.get("source_positions"),
        "center_samples": arrays.get("center_samples"),
        "n_frames": meta["n_frames"],
        "fs": meta["fs"],
        "metrics": _decode_metrics(meta["metrics"]),
    }

    return results


def cached_run(config: Config, force: bool = False) -> dict:
    if not force and has_cached(config):
        result = load_cache(config)
        if result is not None:
            return result

    from ..main import run_simulation
    result = run_simulation(config, run_dir=None, profile=False)
    save_cache(config, result)
    return result


def clear_cache(config: Config | None = None) -> int:
    if config is not None:
        cdir = _cache_dir(config)
        if cdir.exists():
            shutil.rmtree(cdir)
            return 1
        return 0

    count = 0
    if CACHE_DIR.exists():
        for entry in CACHE_DIR.iterdir():
            if entry.is_dir():
                shutil.rmtree(entry)
                count += 1
    return count


def prune_cache(max_gb: float = 5.0) -> int:
    """Remove oldest cache entries (LRU by mtime) until total size <= max_gb."""
    if not CACHE_DIR.exists():
        return 0

    entries = []
    for vdir in CACHE_DIR.iterdir():
        if not vdir.is_dir():
            continue
        for entry in vdir.iterdir():
            if not entry.is_dir():
                continue
            files = [f for f in entry.rglob("*") if f.is_file()]
            size = sum(f.stat().st_size for f in files)
            mtime = max(
                (f.stat().st_mtime for f in files),
                default=entry.stat().st_mtime,
            )
            entries.append((mtime, size, entry))

    total = sum(size for _, size, _ in entries)
    budget = max_gb * 1024 ** 3
    removed = 0
    for _, size, entry in sorted(entries):
        if total <= budget:
            break
        shutil.rmtree(entry)
        total -= size
        removed += 1
    return removed


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Simulation results cache maintenance")
    parser.add_argument(
        "--prune", action="store_true",
        help="Remove oldest entries until cache fits in --max-gb",
    )
    parser.add_argument("--max-gb", type=float, default=5.0)
    parser.add_argument("--clear", action="store_true", help="Remove all cached results")
    args = parser.parse_args()

    if args.clear:
        print(f"Removed {clear_cache()} cache entries")
    elif args.prune:
        print(f"Pruned {prune_cache(args.max_gb)} cache entries")
    else:
        parser.print_help()
