import numpy as np
from scipy.signal import butter, sosfilt
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


def band_rms(signal, fs, band=(500, 4000)):
    """Band-limited RMS per channel (dB).

    Parameters
    ----------
    signal : ndarray, shape (n_mics, n_samples)
    fs : int
    band : (float, float)
        Low and high frequency in Hz.

    Returns
    -------
    rms_db : float
        Mean RMS across channels in dB (arbitrary reference).
    """
    n = signal.shape[1]
    freqs = np.fft.rfftfreq(n, 1.0 / fs)
    mask = (freqs >= band[0]) & (freqs <= band[1])
    if not np.any(mask):
        return -np.inf
    X = np.fft.rfft(signal, axis=1)
    band_power = np.mean(np.abs(X[:, mask]) ** 2)
    return 10.0 * np.log10(band_power + 1e-30)


def spectral_flatness(signal, fs, band=(500, 4000)):
    """Spectral flatness in a frequency band, averaged across channels.

    Returns 0 for a pure tone, 1 for white noise.
    """
    n = signal.shape[1]
    freqs = np.fft.rfftfreq(n, 1.0 / fs)
    mask = (freqs >= band[0]) & (freqs <= band[1])
    if not np.any(mask):
        return 1.0
    X = np.fft.rfft(signal, axis=1)
    band_power = np.abs(X[:, mask]) ** 2
    geo = np.exp(np.mean(np.log(band_power + 1e-30), axis=1))
    arith = np.mean(band_power, axis=1)
    flatness = np.mean(geo / (arith + 1e-30))
    return float(np.clip(flatness, 0.0, 1.0))


def compute_gate1(mic_signals, fs, fft_size, hop_length,
                  band=(500, 4000), rms_threshold_db=5.0,
                  flatness_threshold=0.5):
    """Per-frame Gate 1 status computed from post-noise mic signals.

    Uses the spec's two-stage logic:
      1. Band-limited RMS (500 Hz – 4 kHz) above ambient floor
      2. Spectral flatness below 0.5 (tonal structure)

    The ambient floor is the 5th percentile of ALL frames' band RMS,
    approximating the quietest signal level over the recording. This
    is a substitute for the real system's long-term EMA floor (which
    would be established over minutes of quiet operation).

    Parameters
    ----------
    mic_signals : ndarray, shape (n_mics, n_samples)
    fs : int
    fft_size, hop_length : int
        Frame parameters matching SRP-PHAT.
    band : (float, float)
    rms_threshold_db : float
        RMS must exceed floor by this amount (default 5.0 dB).
    flatness_threshold : float
        Flatness must be below this value (default 0.5).

    Returns
    -------
    gate1 : ndarray bool, shape (n_frames,)
    rms_db_above_floor : ndarray float, shape (n_frames,)
    flatness_vals : ndarray float, shape (n_frames,)
    """
    n_samples = mic_signals.shape[1]
    frame_starts = np.arange(0, n_samples - fft_size + 1, hop_length)
    n_frames = len(frame_starts)

    rms_all = np.zeros(n_frames)
    flatness_vals = np.zeros(n_frames)

    for i, start in enumerate(frame_starts):
        frame = mic_signals[:, start:start + fft_size]
        rms_all[i] = band_rms(frame, fs, band)
        flatness_vals[i] = spectral_flatness(frame, fs, band)

    floor = float(np.percentile(rms_all, 5)) if n_frames > 1 else rms_all[0]
    rms_db_above_floor = rms_all - floor
    gate1 = (rms_db_above_floor > rms_threshold_db) & (flatness_vals < flatness_threshold)

    return gate1, rms_db_above_floor, flatness_vals


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
