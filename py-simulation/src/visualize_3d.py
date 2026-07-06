import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.colors import Normalize
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401

from .visualize import _draw_srp_heatmap, _draw_doa_tracking, _draw_metrics_panel


def create_beamsphere_animation(results, config, array, srp_processor):
    n_frames = results["n_frames"]
    srp_maps = results["srp_maps"]
    estimated_doas = results["estimated_doas"]
    true_doas = results["true_doas"]
    timestamps = results["timestamps"]
    metrics = results["metrics"]
    detections = results.get("detections", np.ones(n_frames, dtype=bool))

    az_grid = srp_processor.az_grid
    el_grid = srp_processor.el_grid
    az_range = srp_processor.az_range
    el_range = srp_processor.el_range

    d_x = np.cos(el_grid) * np.cos(az_grid)
    d_y = np.cos(el_grid) * np.sin(az_grid)
    d_z = np.sin(el_grid)

    stride = 2
    d_x_s = d_x[::stride, ::stride]
    d_y_s = d_y[::stride, ::stride]
    d_z_s = d_z[::stride, ::stride]

    beam_scale = 0.8

    fig = plt.figure(figsize=(14, 10))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.2, 1], height_ratios=[1.2, 1])
    ax_beam = fig.add_subplot(gs[0, 0], projection="3d")
    ax_srp = fig.add_subplot(gs[0, 1])
    ax_track = fig.add_subplot(gs[1, 0])
    ax_metrics = fig.add_subplot(gs[1, 1])
    fig.tight_layout(rect=[0, 0, 1, 0.96])

    norm = Normalize(vmin=0, vmax=1)

    pos = array.positions
    rings = []
    if hasattr(array, "ring1_radius"):
        ring_angles = np.linspace(0, 2 * np.pi, 100)
        rings = [
            (array.ring1_radius * np.cos(ring_angles),
             array.ring1_radius * np.sin(ring_angles),
             -array.ring_spacing / 2 * np.ones_like(ring_angles)),
            (array.ring2_radius * np.cos(ring_angles),
             array.ring2_radius * np.sin(ring_angles),
             array.ring_spacing / 2 * np.ones_like(ring_angles)),
        ]

    def update(frame):
        for ax in [ax_beam, ax_srp, ax_track]:
            ax.clear()

        # ----- 3D Beamsphere -----
        srp = srp_maps[frame]
        srp_max = float(np.max(srp))
        srp_norm = srp / srp_max if srp_max > 0 else srp

        s = np.maximum(srp_norm[::stride, ::stride], 0.01)
        bx = beam_scale * s * d_x_s
        by = beam_scale * s * d_y_s
        bz = beam_scale * s * d_z_s

        ax_beam.plot_wireframe(bx, by, bz, rstride=2, cstride=2,
                               color="gray", alpha=0.12, linewidth=0.3)

        flat_s = s.ravel()
        ax_beam.scatter(bx.ravel(), by.ravel(), bz.ravel(),
                        c=flat_s, cmap="inferno", norm=norm,
                        s=5, alpha=0.35)

        ax_beam.scatter(pos[:, 0], pos[:, 1], pos[:, 2],
                        c="#1f77b4", s=80, edgecolors="white", linewidths=1.5,
                        zorder=12, label="Mics")
        for rx, ry, rz in rings:
            ax_beam.plot(rx, ry, rz, "gray", alpha=0.4, linewidth=2, zorder=11)

        ax_beam.quiver(0, 0, 0, 0, 0, beam_scale * 0.4,
                       color="green", alpha=0.5, linewidth=1.5,
                       arrow_length_ratio=0.15, zorder=11)

        true_az, true_el = true_doas[frame]
        az_idx = np.argmin(np.abs(az_range - true_az))
        el_idx = np.argmin(np.abs(el_range - true_el))
        srp_at_true = srp_norm[az_idx, el_idx]

        true_r = max(beam_scale * srp_at_true, beam_scale * 0.02)
        true_x = true_r * np.cos(true_el) * np.cos(true_az)
        true_y = true_r * np.cos(true_el) * np.sin(true_az)
        true_z = true_r * np.sin(true_el)

        ax_beam.plot([0, true_x], [0, true_y], [0, true_z],
                     "c--", linewidth=1.5, alpha=0.4, zorder=15)
        ax_beam.scatter([true_x], [true_y], [true_z],
                        c="cyan", marker="x", s=100, linewidths=2,
                        zorder=16, label="True DOA")

        if detections[frame]:
            est_az, est_el = estimated_doas[frame]
            est_r = beam_scale
            est_x = est_r * np.cos(est_el) * np.cos(est_az)
            est_y = est_r * np.cos(est_el) * np.sin(est_az)
            est_z = est_r * np.sin(est_el)

            ax_beam.plot([0, est_x], [0, est_y], [0, est_z],
                         "lime", linewidth=1.5, alpha=0.6, zorder=15)
            ax_beam.scatter([est_x], [est_y], [est_z],
                            facecolors="lime", edgecolors="white", marker="o",
                            s=80, linewidths=1.5, zorder=16, label="Est. DOA")

        bound = beam_scale * 1.2
        ax_beam.set_xlim(-bound, bound)
        ax_beam.set_ylim(-bound, bound)
        ax_beam.set_zlim(-bound, bound)
        ax_beam.set_xlabel("X (m)")
        ax_beam.set_ylabel("Y (m)")
        ax_beam.set_zlabel("Z (m)")

        angle = 360.0 * frame / n_frames
        ax_beam.view_init(elev=25, azim=angle)

        # ----- 2D SRP Heatmap -----
        _draw_srp_heatmap(ax_srp, srp, az_range, el_range,
                          true_doa=true_doas[frame],
                          est_doa=estimated_doas[frame],
                          detected=detections[frame])
        ax_srp.set_title(f"SRP-PHAT Map  (t = {timestamps[frame]:.2f}s)")

        # ----- DOA Tracking -----
        n_plot = min(frame + 1, n_frames)
        _draw_doa_tracking(ax_track, timestamps[:n_plot],
                           true_doas[:n_plot], estimated_doas[:n_plot],
                           detections=detections[:n_plot])
        ax_track.axvline(x=timestamps[frame], color="gray", linestyle=":", alpha=0.5)

        # ----- Metrics Panel (static) -----
        _draw_metrics_panel(ax_metrics, metrics, config)

        fig.suptitle(f"{srp_processor.label}  |  Frame {frame + 1}/{n_frames}",
                     fontsize=14, fontweight="bold")
        return ax_beam, ax_srp, ax_track, ax_metrics

    anim = FuncAnimation(fig, update, frames=n_frames,
                         interval=1000 / config.output.animation_fps,
                         blit=False, repeat=False)
    return anim
