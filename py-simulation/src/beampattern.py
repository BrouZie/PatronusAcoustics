"""
Far-field array beampattern analysis — analytical, no simulation needed.

Computes the conventional (delay-and-sum) beamformer response of the
dual-ring array as a function of frequency and direction.  All functions
operate on a DualRingArray instance and return numpy arrays.

Usage:
    python -m src.beampattern               # default geometry → figures/
"""

import numpy as np
from pathlib import Path

from .geometry import DualRingArray
from .config import Config

C = 343.0


def steering_vector(array, f, az_rad, el_rad):
    """Steering vector a(θ,φ) for plane wave(s) from direction(s) (az, el).

    a_m = exp(-j · 2πf · (p_m · u) / c)

    Parameters
    ----------
    array : DualRingArray
    f : float
        Frequency in Hz.
    az_rad, el_rad : float or ndarray
        Scalar or array direction angles in radians (broadcast-compatible).

    Returns
    -------
    a : ndarray complex, shape (n_mics,) for scalars, (n_mics, *grid) for arrays.
    """
    az_rad = np.asarray(az_rad)
    el_rad = np.asarray(el_rad)
    scalar = az_rad.ndim == 0
    # Ravel directions for uniform 2D phase computation
    ux = np.sin(el_rad).ravel() * np.cos(az_rad).ravel()
    uy = np.sin(el_rad).ravel() * np.sin(az_rad).ravel()
    uz = np.cos(el_rad).ravel()
    pos = array.positions  # (n_mics, 3)
    phase = 2 * np.pi * f / C * (
        pos[:, None, 0] * ux[None, :]
        + pos[:, None, 1] * uy[None, :]
        + pos[:, None, 2] * uz[None, :]
    )  # (n_mics, n_dir)
    a = np.exp(-1j * phase)
    if scalar:
        return a[:, 0]
    shape = np.broadcast_arrays(az_rad, el_rad)[0].shape
    return a.reshape(array.n_mics, *shape)


def array_response(array, f, az_rad, el_rad):
    """Conventional delay-and-sum beampattern |B(θ,φ)|² normalised.

    The beamformer is steered at boresight (Z-axis).
    Returns power response in linear units, normalised to 1 at boresight.

    Parameters
    ----------
    array : DualRingArray
    f : float
        Frequency in Hz.
    az_rad, el_rad : ndarray
        Angle grid(s) (radians), broadcast-compatible.

    Returns
    -------
    B : ndarray, shape (*grid)
        Power response |B|².
    """
    a = steering_vector(array, f, az_rad, el_rad)  # (n_mics, *grid)
    n_mics = array.n_mics
    a_bore = steering_vector(array, f, 0.0, 0.0)   # (n_mics,)
    w = np.conj(a_bore) / n_mics                   # DAS weights, w^H · a(0) = 1
    beam = np.sum(w[:, None, None] * a, axis=0)
    B = np.abs(beam) ** 2
    return B / np.max(B)





def _compute_robust(array, freqs, az_deg_range=(-90, 90), el_deg_range=(0, 90),
                    az_step=0.5, el_step=0.5):
    """Compute beampattern metrics over a range of frequencies."""
    az_rad = np.radians(np.arange(*az_deg_range, az_step))
    el_rad = np.radians(np.arange(*el_deg_range, el_step))

    results = []
    for f in freqs:
        AZ, EL = np.meshgrid(az_rad, el_rad, indexing="ij")
        B = array_response(array, f, AZ, EL)
        B_dB = 10 * np.log10(np.maximum(B, 1e-15))

        az_deg = np.degrees(AZ)
        el_deg = np.degrees(EL)

        # 3 dB beamwidth
        half_max = 0.5
        above = B >= half_max
        az_above = np.any(above, axis=1)
        el_above = np.any(above, axis=0)

        bw_az = np.sum(az_above) * az_step if np.any(az_above) else np.nan
        bw_el = np.sum(el_above) * el_step if np.any(el_above) else np.nan

        # Front-back: forward = az in [-90, 90], el in [0, 90]
        # (Forward hemisphere in array coordinates = positive Z hemisphere)
        forward = (np.abs(az_deg) <= 90)  # all forward in visible range
        rear = False  # not visible in our grid (we only scan forward)
        # Actually for front-back, we need to scan the full sphere
        # For now: max in rear (az beyond ±90) / max in forward
        # But our grid is [-90, 90] az × [0, 90] el (forward only)
        # So we can't compute front-back with this grid
        # We'll need a separate full-sphere computation

        # Sidelobe level: exlude ±15° around boresight (az=0, el=0)
        mainlobe = (np.abs(az_deg) <= 15) & (np.abs(el_deg) <= 15)
        peak_for = np.max(B)
        sidelobe_for = np.max(B[~mainlobe]) if np.any(~mainlobe) else 0.0
        msll_db = 10 * np.log10(sidelobe_for / peak_for) if sidelobe_for > 0 else -np.inf

        results.append({
            "f_hz": f,
            "bw_az_deg": bw_az,
            "bw_el_deg": bw_el,
            "msll_db": msll_db,
        })
    return results


def plot_beampattern(array, output_dir, freqs=None, az_range_deg=(-90, 90),
                     el_range_deg=(0, 90)):
    """Generate beampattern figures and a summary table.

    Creates:
        beampattern_<freq>hz.png       — 2D heatmaps per frequency
        beampattern_cuts.png           — 1-D azimuth/elevation cuts
        beampattern_beamwidth.png      — Beamwidth vs frequency
        beampattern_summary.txt        — Numerical summary table
    """
    if freqs is None:
        freqs = [400, 600, 800, 1000, 1500, 2000, 2500, 3000]

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    az_step = 0.5
    el_step = 0.5
    az_rad = np.radians(np.arange(*az_range_deg, az_step))
    el_rad = np.radians(np.arange(*el_range_deg, el_step))
    AZ, EL = np.meshgrid(az_rad, el_rad, indexing="ij")

    import matplotlib.pyplot as plt

    # ---- 2D heatmaps per frequency ----
    for f in freqs:
        B = array_response(array, f, AZ, EL)
        B_dB = 10 * np.log10(np.maximum(B, 1e-15))
        vmin = max(np.min(B_dB), -40)

        fig, ax = plt.subplots(figsize=(7, 5))
        extent = [az_range_deg[0], az_range_deg[1], el_range_deg[0], el_range_deg[1]]
        im = ax.imshow(B_dB.T, origin="lower", aspect="auto", extent=extent,
                       cmap="inferno", vmin=vmin, vmax=0)
        ax.set_xlabel("Azimuth from boresight (deg)")
        ax.set_ylabel("Elevation from boresight (deg)")
        ax.set_title(f"Beampattern at {f} Hz")
        fig.colorbar(im, ax=ax, label="dB")
        fig.tight_layout()
        fig.savefig(output_dir / f"beampattern_{f}hz.png", dpi=150)
        plt.close(fig)

    # ---- 1-D cuts (az main, el main) ----
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    colors = plt.cm.viridis(np.linspace(0.2, 0.9, len(freqs)))
    bore_idx_az = np.argmin(np.abs(el_rad))  # closest to el=0 (boresight)
    bore_idx_el = np.argmin(np.abs(az_rad))

    for f, c in zip(freqs, colors):
        B = array_response(array, f, AZ, EL)
        B_dB = 10 * np.log10(np.maximum(B, 1e-15))
        az_cut = B_dB[:, bore_idx_az]
        el_cut = B_dB[bore_idx_el, :]
        axes[0].plot(np.degrees(az_rad), az_cut, color=c, label=f"{f} Hz")
        axes[1].plot(np.degrees(el_rad), el_cut, color=c, label=f"{f} Hz")

    axes[0].set_xlabel("Azimuth from boresight (deg)")
    axes[0].set_ylabel("Response (dB)")
    axes[0].set_title("Azimuth cut (at boresight elevation)")
    axes[0].legend(fontsize=8)
    axes[0].grid(True, alpha=0.3)
    axes[0].axhline(-3, color="gray", ls="--", lw=0.8)

    axes[1].set_xlabel("Elevation from boresight (deg)")
    axes[1].set_ylabel("Response (dB)")
    axes[1].set_title("Elevation cut (at boresight azimuth)")
    axes[1].legend(fontsize=8)
    axes[1].grid(True, alpha=0.3)
    axes[1].axhline(-3, color="gray", ls="--", lw=0.8)

    fig.tight_layout()
    fig.savefig(output_dir / "beampattern_cuts.png", dpi=150)
    plt.close(fig)

    # ---- Full front-back coverage ----
    # Front-back requires a full sphere: el ∈ [0°, 180°] covers both hemispheres.
    fb_az = np.radians(np.arange(-180, 180, 2))
    fb_el = np.radians(np.arange(0, 181, 2))
    FBAZ, FBEL = np.meshgrid(fb_az, fb_el, indexing="ij")

    fb_ratios = []
    for f in freqs:
        B = array_response(array, f, FBAZ, FBEL)
        cos_el = np.cos(FBEL)
        forward = cos_el > 0  # u_z > 0 → front hemisphere
        rear = cos_el < 0     # u_z < 0 → rear hemisphere
        fwd_max = np.max(B[forward]) if np.any(forward) else 1.0
        rear_max = np.max(B[rear]) if np.any(rear) else 1.0
        fb_ratios.append(10 * np.log10(rear_max / fwd_max))

    # ---- Beamwidth vs frequency ----
    metrics = _compute_robust(array, freqs,
                              az_range_deg, el_range_deg, az_step, el_step)
    _f = [m["f_hz"] for m in metrics]
    bw_az = [m["bw_az_deg"] for m in metrics]
    bw_el = [m["bw_el_deg"] for m in metrics]
    msll = [m["msll_db"] for m in metrics]

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    axes[0].plot(_f, bw_az, "o-", label="Azimuth")
    axes[0].plot(_f, bw_el, "s-", label="Elevation")
    axes[0].set_xlabel("Frequency (Hz)")
    axes[0].set_ylabel("3 dB Beamwidth (deg)")
    axes[0].set_title("Beamwidth vs Frequency")
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)

    axes[1].plot(_f, msll, "o-", color="red")
    axes[1].set_xlabel("Frequency (Hz)")
    axes[1].set_ylabel("Max Sidelobe Level (dB)")
    axes[1].set_title("Sidelobe Level vs Frequency")
    axes[1].grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(output_dir / "beampattern_beamwidth.png", dpi=150)
    plt.close(fig)

    # ---- Write summary ----
    lines = [
        f"{'Freq (Hz)':>10} {'BW_az (deg)':>12} {'BW_el (deg)':>12} "
        f"{'MSLL (dB)':>10} {'FB_rej (dB)':>11}"
    ]
    lines.append("-" * len(lines[0]))
    for i, f in enumerate(freqs):
        lines.append(
            f"{f:10.0f} {bw_az[i]:12.1f} {bw_el[i]:12.1f} "
            f"{msll[i]:10.1f} {fb_ratios[i]:11.1f}"
        )
    summary = "\n".join(lines)
    (output_dir / "beampattern_summary.txt").write_text(summary)
    print(summary)

    print(f"\nFigures → {output_dir.resolve()}")
    return metrics


if __name__ == "__main__":
    cfg = Config.from_yamls("config/default.yaml")
    array = DualRingArray(cfg.array)
    out = Path(__file__).resolve().parent.parent / "figures"
    plot_beampattern(array, str(out))
