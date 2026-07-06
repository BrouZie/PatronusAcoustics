"""Detection-range curves: the numbers a geometry decision is made on.

`run_range_curve` sweeps a stationary drone over distances (averaging over
signal seeds) and returns detection rate, angular error, and mirror
suppression per distance. Each (distance, seed) point is an independent
config, so `results.cache.cached_run` gives free caching and resume.
"""

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from ..config import Config, config_hash
from ..results.cache import cached_run


@dataclass
class RangeCurve:
    distances: np.ndarray
    detection_rate: np.ndarray
    angular_error_deg: np.ndarray
    mirror_suppression_db: np.ndarray
    label: str = ""
    config_hash: str = ""
    n_seeds: int = 1


def _config_at(base: Config, distance: float, seed: int) -> Config:
    d = base.to_dict()
    d["drone"]["distance"] = float(distance)
    # Range curves use a stationary source at initial_bearing; a moving
    # trajectory would make "distance" ill-defined. (deep_merge cannot clear
    # a dict, so replace outright.)
    d["drone"]["trajectory"] = {}
    d["signal"]["seed"] = int(seed)
    d["signal"]["snr_db"] = None  # SNR must follow from distance + EIN budget
    return Config.from_dict(d)


def run_range_curve(base_config: Config, distances: Sequence[float],
                    n_seeds: int = 3, label: str = "",
                    verbose: bool = True) -> RangeCurve:
    distances = np.asarray(sorted(distances), dtype=float)
    rates = np.zeros(len(distances))
    errors = np.zeros(len(distances))
    suppressions = np.zeros(len(distances))

    for i, dist in enumerate(distances):
        rate_acc, err_acc, sup_acc = [], [], []
        for seed in range(n_seeds):
            cfg = _config_at(base_config, dist, seed)
            metrics = cached_run(cfg)["metrics"]
            rate_acc.append(metrics.detection_rate)
            err_acc.append(metrics.mean_angular_error_deg)
            sup_acc.append(metrics.mean_mirror_suppression_db)
        rates[i] = float(np.mean(rate_acc))
        errors[i] = (float(np.nanmean(err_acc))
                     if not np.all(np.isnan(err_acc)) else float("nan"))
        suppressions[i] = (float(np.nanmean(sup_acc))
                           if not np.all(np.isnan(sup_acc)) else float("nan"))
        if verbose:
            print(f"  [{label or 'curve'}] d={dist:g} m  "
                  f"det={rates[i]:.0%}  err={errors[i]:.1f}°")

    return RangeCurve(
        distances=distances,
        detection_rate=rates,
        angular_error_deg=errors,
        mirror_suppression_db=suppressions,
        label=label,
        config_hash=config_hash(base_config),
        n_seeds=n_seeds,
    )


def range_at_rate(curve: RangeCurve, target: float = 0.9) -> float:
    """Largest distance at which detection rate still meets `target`,
    linearly interpolating the crossing. NaN when the curve never crosses
    (always above → true range beyond tested distances; always below →
    target unreachable)."""
    d = curve.distances
    r = curve.detection_rate
    if len(d) == 0:
        return float("nan")
    if r[0] < target:
        return float("nan")
    below = np.where(r < target)[0]
    if len(below) == 0:
        return float("nan")
    j = below[0]
    i = j - 1
    if r[i] == r[j]:
        return float(d[i])
    frac = (r[i] - target) / (r[i] - r[j])
    return float(d[i] + frac * (d[j] - d[i]))
