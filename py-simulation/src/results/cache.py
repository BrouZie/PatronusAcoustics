import json
from pathlib import Path

import numpy as np

from .manifest import RESULTS_DIR
from ..config import Config, config_hash


CACHE_DIR = RESULTS_DIR / "cache"


def _cache_dir(config: Config) -> Path:
    return CACHE_DIR / config_hash(config)


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
            import shutil
            shutil.rmtree(cdir)
            return 1
        return 0

    count = 0
    if CACHE_DIR.exists():
        for entry in CACHE_DIR.iterdir():
            if entry.is_dir():
                import shutil
                shutil.rmtree(entry)
                count += 1
    return count
