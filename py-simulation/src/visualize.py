import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401

from pathlib import Path


def _draw_array_geometry(ax, array, highlighted_mic=None):
    ax.clear()
    pos = array.positions

    is_dual_ring = hasattr(array, "ring1_radius")
    if is_dual_ring:
        colors = ["#1f77b4"] * array.n_mics_ring1 + ["#ff7f0e"] * array.n_mics_ring2
    else:
        colors = ["#1f77b4"] * array.n_mics

    ax.scatter(pos[:, 0], pos[:, 1], pos[:, 2], c=colors, s=40, alpha=0.9)

    if highlighted_mic is not None:
        ax.scatter([pos[highlighted_mic, 0]], [pos[highlighted_mic, 1]], [pos[highlighted_mic, 2]],
                   c="red", s=80, marker="*")

    if is_dual_ring:
        ring_angles = np.linspace(0, 2 * np.pi, 100)
        for radius, z in [(array.ring1_radius, -array.ring_spacing / 2),
                          (array.ring2_radius, array.ring_spacing / 2)]:
            ax.plot(radius * np.cos(ring_angles), radius * np.sin(ring_angles),
                    z * np.ones_like(ring_angles), "gray", alpha=0.4, linewidth=1)

    # Boresight arrow
    ax.quiver(0, 0, 0, 0, 0, 0.3, color="green", alpha=0.7, linewidth=2, arrow_length_ratio=0.2)

    max_extent = max(float(np.max(np.abs(pos))), 0.1) * 1.5
    ax.set_xlim(-max_extent, max_extent)
    ax.set_ylim(-max_extent, max_extent)
    ax.set_zlim(-max_extent, max_extent)
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.set_zlabel("Z (m)")
    ax.set_title("Array Geometry", fontsize=11)
    ax.view_init(elev=25, azim=45)


def _draw_srp_heatmap(ax, srp_map, az_range_deg, el_range_deg, true_doa=None, est_doa=None, detected=True):
    ax.clear()
    az_deg = np.degrees(az_range_deg)
    el_deg = np.degrees(el_range_deg)

    srp_db = 10 * np.log10(srp_map - np.min(srp_map) + 1e-10)
    vmin = np.percentile(srp_db, 10)
    vmax = np.max(srp_db)

    extent = [az_deg[0], az_deg[-1], el_deg[0], el_deg[-1]]
    ax.imshow(srp_db.T, origin="lower", aspect="auto", extent=extent,
              cmap="inferno", vmin=vmin, vmax=vmax)

    if true_doa is not None:
        ax.scatter(np.degrees(true_doa[0]), np.degrees(true_doa[1]),
                   c="cyan", marker="x", s=100, linewidths=2, label="True DOA", zorder=5)

    if est_doa is not None and detected and not np.any(np.isnan(est_doa)):
        ax.scatter(np.degrees(est_doa[0]), np.degrees(est_doa[1]),
                   edgecolors="lime", facecolors="none", marker="o", s=80,
                   linewidths=2, label="Est. DOA", zorder=5)

    ax.set_xlabel("Azimuth from boresight (deg)")
    ax.set_ylabel("Elevation from boresight (deg)")
    ax.set_title("SRP-PHAT Map")
    has_labels = true_doa is not None or (est_doa is not None and detected and not np.any(np.isnan(est_doa)))
    if has_labels:
        ax.legend(loc="upper right", fontsize=8)


def _draw_doa_tracking(ax, timestamps, true_doas, estimated_doas, detections=None):
    ax.clear()
    t = timestamps

    true_az = np.degrees(true_doas[:, 0])
    true_el = np.degrees(true_doas[:, 1])
    est_az = np.degrees(estimated_doas[:, 0])
    est_el = np.degrees(estimated_doas[:, 1])

    ax.plot(t, true_az, "c-", linewidth=1.5, label="True Azimuth")
    ax.plot(t, true_el, "m-", linewidth=1.5, label="True Elevation")
    ax.plot(t, est_az, "c--", linewidth=1, alpha=0.7, label="Est. Azimuth")
    ax.plot(t, est_el, "m--", linewidth=1, alpha=0.7, label="Est. Elevation")

    if detections is not None:
        undetected = ~detections
        if np.any(undetected):
            switches = np.diff(np.concatenate([[False], undetected, [False]]).astype(int))
            starts = np.where(switches == 1)[0]
            ends = np.where(switches == -1)[0]
            for s, e in zip(starts, ends):
                ax.axvspan(t[s] if s < len(t) else t[-1],
                           t[e - 1] if e - 1 < len(t) else t[-1],
                           alpha=0.15, color="red", zorder=0)

    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Angle (deg)")
    ax.set_title("DOA Tracking")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, alpha=0.3)


def _array_summary(array_cfg):
    kind = getattr(array_cfg, "type", "dual_ring")
    if kind == "dual_ring":
        return (
            f"Array: R1={array_cfg.ring1_radius:.2f}m, "
            f"R2={array_cfg.ring2_radius:.2f}m, "
            f"d={array_cfg.ring_spacing:.2f}m\n"
            f"Mics: {array_cfg.n_mics_ring1}+{array_cfg.n_mics_ring2}"
        )
    if kind == "single_ring":
        return (
            f"Array: single ring R={array_cfg.radius:.2f}m\n"
            f"Mics: {array_cfg.n_mics}"
        )
    n = len(array_cfg.positions) if array_cfg.positions is not None else "?"
    return f"Array: custom XYZ\nMics: {n}"


def _draw_metrics_panel(ax, metrics, config):
    ax.clear()
    ax.axis("off")

    text_lines = [
        f"Mean Angular Error:  {metrics.mean_angular_error_deg:.2f}°",
        f"Std Angular Error:   {metrics.std_angular_error_deg:.2f}°",
        f"Max Angular Error:   {metrics.max_angular_error_deg:.2f}°",
        f"Mean PSR:            {metrics.mean_psr_db:.1f} dB",
        f"Mean Beamwidth:      {metrics.mean_beamwidth_deg:.2f}°",
    ]

    cfg_text = (
        f"{_array_summary(config.array)}\n"
        f"Drone: {config.drone.rpm} RPM, "
        f"SNR={config.signal.snr_db} dB"
    )

    ax.text(0.05, 0.95, "Performance Metrics", transform=ax.transAxes,
            fontsize=12, fontweight="bold", verticalalignment="top")
    for i, line in enumerate(text_lines):
        ax.text(0.05, 0.78 - i * 0.08, line, transform=ax.transAxes,
                fontsize=10, verticalalignment="top", fontfamily="monospace")

    ax.text(0.05, 0.35, "Configuration", transform=ax.transAxes,
            fontsize=12, fontweight="bold", verticalalignment="top")
    ax.text(0.05, 0.25, cfg_text, transform=ax.transAxes,
            fontsize=8, verticalalignment="top", fontfamily="monospace")


def save_summary_figures(results, config, array, srp_processor, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    srp_maps = results["srp_maps"]
    true_doas = results["true_doas"]
    estimated_doas = results["estimated_doas"]
    timestamps = results["timestamps"]
    metrics = results["metrics"]
    detections = results.get("detections", np.ones(len(timestamps), dtype=bool))

    az_range = srp_processor.az_range
    el_range = srp_processor.el_range

    # Average SRP map
    fig, ax = plt.subplots(figsize=(8, 6))
    avg_srp = np.mean(srp_maps, axis=0)
    _draw_srp_heatmap(ax, avg_srp, az_range, el_range)
    ax.set_title("Average SRP-PHAT Map")
    fig.tight_layout()
    fig.savefig(output_dir / "srp_heatmap_average.png", dpi=150)
    plt.close(fig)

    # DOA error over time (with detection shading)
    fig, ax = plt.subplots(figsize=(10, 5))
    ang = metrics.angular_errors_deg
    ax.plot(timestamps, ang, "r-", linewidth=1.5)
    ax.axhline(y=metrics.mean_angular_error_deg, color="gray", linestyle="--",
               label=f"Mean: {metrics.mean_angular_error_deg:.2f}°")
    std = metrics.std_angular_error_deg
    ax.fill_between(timestamps,
                     metrics.mean_angular_error_deg - std,
                     metrics.mean_angular_error_deg + std,
                     alpha=0.2, color="red")
    undetected = ~detections
    if np.any(undetected):
        switches = np.diff(np.concatenate([[False], undetected, [False]]).astype(int))
        starts = np.where(switches == 1)[0]
        ends = np.where(switches == -1)[0]
        for s, e in zip(starts, ends):
            ax.axvspan(timestamps[s] if s < len(timestamps) else timestamps[-1],
                       timestamps[e - 1] if e - 1 < len(timestamps) else timestamps[-1],
                       alpha=0.12, color="red", zorder=0)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Angular Error (deg)")
    ax.set_title("DOA Estimation Error Over Time")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_dir / "doa_error_over_time.png", dpi=150)
    plt.close(fig)

    # Metrics summary
    psr_thresh = 3.0
    if hasattr(config.srpphat, "detection") and config.srpphat.detection is not None:
        psr_thresh = config.srpphat.detection.psr_threshold_db

    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    axes[0].plot(timestamps, metrics.peak_to_sidelobe_ratios_db, "g-", linewidth=1)
    axes[0].axhline(y=metrics.mean_psr_db, color="gray", linestyle="--",
                    label=f"Mean: {metrics.mean_psr_db:.1f} dB")
    axes[0].axhline(y=psr_thresh, color="red", linestyle=":",
                    label=f"Threshold: {psr_thresh:.1f} dB")
    if np.any(undetected):
        switches = np.diff(np.concatenate([[False], undetected, [False]]).astype(int))
        starts = np.where(switches == 1)[0]
        ends = np.where(switches == -1)[0]
        for s, e in zip(starts, ends):
            axes[0].axvspan(timestamps[s] if s < len(timestamps) else timestamps[-1],
                            timestamps[e - 1] if e - 1 < len(timestamps) else timestamps[-1],
                            alpha=0.12, color="red", zorder=0)
    axes[0].set_xlabel("Time (s)")
    axes[0].set_ylabel("PSR (dB)")
    axes[0].set_title("Peak-to-Sidelobe Ratio")
    axes[0].legend(fontsize=8)
    axes[0].grid(True, alpha=0.3)

    axes[1].plot(timestamps, metrics.beamwidths_3db, "b-", linewidth=1)
    axes[1].axhline(y=metrics.mean_beamwidth_deg, color="gray", linestyle="--",
                    label=f"Mean: {metrics.mean_beamwidth_deg:.2f}°")
    axes[1].set_xlabel("Time (s)")
    axes[1].set_ylabel("Beamwidth (deg)")
    axes[1].set_title("3 dB Beamwidth")
    axes[1].legend(fontsize=8)
    axes[1].grid(True, alpha=0.3)

    axes[2].axis("off")
    summary_text = (
        f"Detection Rate:      {metrics.detection_rate:.0%} "
        f"({metrics.n_detected}/{metrics.n_total})\n"
        f"Mean Angular Error:  {metrics.mean_angular_error_deg:.2f}°\n"
        f"Std Angular Error:   {metrics.std_angular_error_deg:.2f}°\n"
        f"Max Angular Error:   {metrics.max_angular_error_deg:.2f}°\n"
        f"Mean PSR:            {metrics.mean_psr_db:.1f} dB\n"
        f"Mean Beamwidth:      {metrics.mean_beamwidth_deg:.2f}°"
    )
    axes[2].text(0.15, 0.6, summary_text, fontsize=11, fontfamily="monospace",
                 verticalalignment="center")
    axes[2].set_title("Summary")

    fig.tight_layout()
    fig.savefig(output_dir / "metrics_summary.png", dpi=150)
    plt.close(fig)

    print(f"  → {output_dir / 'srp_heatmap_average.png'}")
    print(f"  → {output_dir / 'doa_error_over_time.png'}")
    print(f"  → {output_dir / 'metrics_summary.png'}")
