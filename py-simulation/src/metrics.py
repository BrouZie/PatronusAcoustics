import numpy as np
from dataclasses import dataclass, field


@dataclass
class MetricsResult:
    angular_errors_deg: np.ndarray = field(default_factory=lambda: np.array([]))
    peak_to_sidelobe_ratios_db: np.ndarray = field(default_factory=lambda: np.array([]))
    beamwidths_3db: np.ndarray = field(default_factory=lambda: np.array([]))
    frame_times: np.ndarray = field(default_factory=lambda: np.array([]))
    mean_angular_error_deg: float = 0.0
    std_angular_error_deg: float = 0.0
    max_angular_error_deg: float = 0.0
    mean_psr_db: float = 0.0
    mean_beamwidth_deg: float = 0.0
    n_detected: int = 0
    n_total: int = 0
    detection_rate: float = 0.0


def angular_error(true_doas, estimated_doas):
    true_doas = np.asarray(true_doas)
    estimated_doas = np.asarray(estimated_doas)

    true_az, true_el = true_doas[:, 0], true_doas[:, 1]
    est_az, est_el = estimated_doas[:, 0], estimated_doas[:, 1]

    u_true = np.column_stack([
        np.sin(true_el) * np.cos(true_az),
        np.sin(true_el) * np.sin(true_az),
        np.cos(true_el),
    ])

    u_est = np.column_stack([
        np.sin(est_el) * np.cos(est_az),
        np.sin(est_el) * np.sin(est_az),
        np.cos(est_el),
    ])

    dot = np.clip(np.sum(u_true * u_est, axis=1), -1.0, 1.0)
    return np.degrees(np.arccos(dot))


def peak_to_sidelobe_ratio(srp_map, exclude_radius_px=3):
    peak_idx = np.unravel_index(np.argmax(srp_map), srp_map.shape)
    peak_val = srp_map[peak_idx]

    mask = np.ones_like(srp_map, dtype=bool)
    yy, xx = np.ogrid[:srp_map.shape[0], :srp_map.shape[1]]
    dist = np.sqrt((xx - peak_idx[1]) ** 2 + (yy - peak_idx[0]) ** 2)
    mask[dist <= exclude_radius_px] = False

    sidelobe_val = np.max(srp_map[mask]) if np.any(mask) else peak_val * 0.5
    return 10.0 * np.log10(peak_val / (sidelobe_val + 1e-10))


def beamwidth_3db(srp_map, az_range_deg, el_range_deg):
    peak_val = np.max(srp_map)
    threshold = peak_val / 2.0

    above = srp_map >= threshold

    az_deg = np.degrees(az_range_deg) if np.any(az_range_deg > np.pi / 2) else np.degrees(az_range_deg)
    el_deg = np.degrees(el_range_deg) if np.any(el_range_deg > np.pi / 2) else np.degrees(el_range_deg)

    az_above = np.any(above, axis=1)
    el_above = np.any(above, axis=0)

    az_width = np.sum(az_above) * (az_deg[1] - az_deg[0]) if np.any(az_above) else 0.0
    el_width = np.sum(el_above) * (el_deg[1] - el_deg[0]) if np.any(el_above) else 0.0

    return np.sqrt(az_width * el_width)


def compute_metrics(results, array, srp_processor):
    true_doas = results["true_doas"]
    estimated_doas = results["estimated_doas"]
    srp_maps = results["srp_maps"]
    n_frames = results["n_frames"]
    detections = results.get("detections", np.ones(n_frames, dtype=bool))

    n_detected = int(np.sum(detections))
    n_total = n_frames
    detection_rate = n_detected / n_total if n_total > 0 else 0.0

    ang_errors = np.full(n_frames, np.nan)
    valid_mask = detections & ~np.any(np.isnan(estimated_doas), axis=1)
    if np.any(valid_mask):
        ang_errors[valid_mask] = angular_error(
            true_doas[valid_mask], estimated_doas[valid_mask]
        )

    psrs = np.array([
        peak_to_sidelobe_ratio(srp_maps[i])
        for i in range(n_frames)
    ])
    bws = np.array([
        beamwidth_3db(srp_maps[i], srp_processor.az_range, srp_processor.el_range)
        for i in range(n_frames)
    ])

    valid_ang = ang_errors[~np.isnan(ang_errors)]
    if len(valid_ang) > 0:
        mean_ang = float(np.mean(valid_ang))
        std_ang = float(np.std(valid_ang))
        max_ang = float(np.max(valid_ang))
    else:
        mean_ang = std_ang = max_ang = 0.0

    return MetricsResult(
        angular_errors_deg=ang_errors,
        peak_to_sidelobe_ratios_db=psrs,
        beamwidths_3db=bws,
        frame_times=results.get("timestamps", np.array([])),
        mean_angular_error_deg=mean_ang,
        std_angular_error_deg=std_ang,
        max_angular_error_deg=max_ang,
        mean_psr_db=float(np.mean(psrs)),
        mean_beamwidth_deg=float(np.mean(bws)),
        n_detected=n_detected,
        n_total=n_total,
        detection_rate=detection_rate,
    )
