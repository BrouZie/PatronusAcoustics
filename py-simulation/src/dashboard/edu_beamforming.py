"""
Educational beamforming visualization — interactive delay-and-sum beampattern
explorer for the dual-ring array.

Run via the "Educational" tab of the dashboard, or standalone:
    streamlit run src/dashboard/app.py
"""

import numpy as np
import streamlit as st
from matplotlib import pyplot as plt

from ..geometry import DualRingArray
from ..config import Config, ArrayConfig
from ..beampattern import steering_vector, array_response

C = 343.0


def render_beamforming_basics() -> None:
    st.header("Delay-and-Sum Beamforming Basics")

    with st.expander("How it works", expanded=True):
        st.markdown(r"""
        **Delay-and-sum beamforming** aligns microphone signals in time before
        summing them. When a plane wave arrives from direction $\mathbf{u}$, the
        signal at microphone $m$ is delayed by $\tau_m = \mathbf{p}_m \cdot \mathbf{u} / c$.

        The steering vector steers the beam toward direction $\mathbf{u}_0$:

        $$a_m(f, \mathbf{u}_0) = \exp\!\left(-j \frac{2\pi f}{c} \mathbf{p}_m \cdot \mathbf{u}_0\right)$$

        The beamformer output power for a wave from $\mathbf{u}$ is:

        $$B(f, \mathbf{u}) = \frac{1}{M} \sum_{m=1}^{M} a_m^*(f, \mathbf{u}_0) \, a_m(f, \mathbf{u})$$

        When $\mathbf{u} = \mathbf{u}_0$, all channels sum coherently → maximum output.
        """)

    # Sidebar controls
    with st.sidebar:
        st.subheader("Array Geometry")
        ring1_radius = st.slider("Outer ring radius (m)", 0.05, 1.0, 0.34, 0.01, key="edu_r1")
        ring2_radius = st.slider("Inner ring radius (m)", 0.05, 1.0, 0.17, 0.01, key="edu_r2")
        n_mics1 = st.slider("Mics on ring 1", 2, 32, 8, 1, key="edu_n1")
        n_mics2 = st.slider("Mics on ring 2", 2, 32, 8, 1, key="edu_n2")
        ring_spacing = st.slider("Ring spacing (m)", 0.01, 1.0, 0.2, 0.01, key="edu_spacing")

        st.subheader("Beamforming")
        freq = st.slider("Frequency (Hz)", 100, 3000, 1000, 50, key="edu_freq")
        steer_az = st.slider("Steer azimuth (deg)", -90, 90, 0, 1, key="edu_steer_az")
        steer_el = st.slider("Steer elevation (deg)", 0, 90, 0, 1, key="edu_steer_el")

        show_ula = st.checkbox("Show ULA comparison", value=False, key="edu_show_ula")
        if show_ula:
            ula_n = st.slider("ULA element count", 2, 32, 8, 1, key="edu_ula_n")
            ula_spacing = st.slider("ULA spacing (λ fraction)", 0.1, 2.0, 0.5, 0.05, key="edu_ula_spacing")

    cfg = ArrayConfig(
        ring1_radius=ring1_radius,
        ring2_radius=ring2_radius,
        n_mics_ring1=n_mics1,
        n_mics_ring2=n_mics2,
        ring_spacing=ring_spacing,
        mic_radius=0.005,
    )
    array = DualRingArray(cfg)

    steer_az_rad = np.radians(steer_az)
    steer_el_rad = np.radians(steer_el)

    az_grid = np.radians(np.linspace(-90, 90, 721))
    el_grid = np.radians(np.linspace(0, 90, 361))
    AZ, EL = np.meshgrid(az_grid, el_grid, indexing="ij")

    B = array_response(array, freq, AZ, EL)
    B_dB = 10 * np.log10(np.maximum(B, 1e-15))
    bore_idx = np.argmin(np.abs(el_grid))

    az_cut = B_dB[:, bore_idx]

    tab_polar, tab_rect, tab_geom, tab_compare = st.tabs([
        "Polar Plot", "Response (dB)", "Array Geometry", "Compare Frequencies",
    ])

    with tab_polar:
        fig, ax = plt.subplots(subplot_kw={"projection": "polar"}, figsize=(7, 7))
        az_deg = np.degrees(az_grid)
        theta = np.radians(az_deg)
        r_linear = 10 ** (az_cut / 20)
        ax.plot(theta, r_linear, lw=1.5)
        ax.set_thetamin(-90)
        ax.set_thetamax(90)
        ax.set_title(f"Beampattern at {freq} Hz (polar)", pad=20)
        ax.grid(True, alpha=0.3)
        st.pyplot(fig)

    with tab_rect:
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(np.degrees(az_grid), az_cut, lw=1.5)
        ax.axhline(-3, color="red", ls="--", alpha=0.5, label="-3 dB")
        ax.axvline(steer_az, color="green", ls=":", alpha=0.5, label=f"Steer {steer_az}°")
        ax.set_xlabel("Azimuth from boresight (deg)")
        ax.set_ylabel("Response (dB)")
        ax.set_title(f"Azimuth Beampattern at {freq} Hz")
        ax.set_xlim(-90, 90)
        ax.set_ylim(-40, 3)
        ax.legend()
        ax.grid(True, alpha=0.3)
        st.pyplot(fig)

        beamwidth_deg = _beamwidth(az_cut, np.degrees(az_grid))
        stats_col1, stats_col2, stats_col3 = st.columns(3)
        with stats_col1:
            st.metric("3 dB Beamwidth", f"{beamwidth_deg:.1f}°" if beamwidth_deg else "N/A")
        with stats_col2:
            p = _peak_sidelobe(B[:, bore_idx])
            st.metric("Peak Sidelobe", f"{p:.1f} dB" if p else "N/A")
        with stats_col3:
            st.metric("N mics", str(array.n_mics))

    with tab_geom:
        fig = _plot_array_geometry(array)
        st.pyplot(fig)

    with tab_compare:
        st.subheader("Beampattern vs Frequency")
        comp_freqs = st.multiselect(
            "Select frequencies to compare",
            [200, 400, 600, 800, 1000, 1500, 2000, 2500, 3000],
            default=[400, 1000, 2000],
            key="edu_comp_freqs",
        )
        if comp_freqs:
            fig, ax = plt.subplots(figsize=(10, 5))
            colors = plt.cm.viridis(np.linspace(0.2, 0.9, len(comp_freqs)))
            for f, c in zip(comp_freqs, colors):
                Bf = array_response(array, f, AZ, EL)
                Bf_dB = 10 * np.log10(np.maximum(Bf, 1e-15))
                cut = Bf_dB[:, bore_idx]
                ax.plot(np.degrees(az_grid), cut, color=c, lw=1.5, label=f"{f} Hz")
            ax.axhline(-3, color="red", ls="--", alpha=0.5)
            ax.set_xlabel("Azimuth from boresight (deg)")
            ax.set_ylabel("Response (dB)")
            ax.set_title("Beampattern Comparison")
            ax.set_xlim(-90, 90)
            ax.set_ylim(-40, 3)
            ax.legend()
            ax.grid(True, alpha=0.3)
            st.pyplot(fig)

    if show_ula:
        st.subheader("ULA Comparison")
        ula_positions = np.zeros((ula_n, 3))
        d_wavelength = ula_spacing * C / freq
        ula_positions[:, 0] = np.arange(ula_n) * d_wavelength - (ula_n - 1) * d_wavelength / 2
        fig, ax = plt.subplots(figsize=(10, 5))
        colors = ["blue", "orange"]
        for label, pos, color in zip(["Dual-Ring", f"ULA ({ula_n} els)"], [array, ula_positions], colors):
            if label == "Dual-Ring":
                B_arr = B_dB[:, bore_idx]
            else:
                ux = np.sin(steer_el_rad) * np.cos(steer_az_rad)
                uy = np.sin(steer_el_rad) * np.sin(steer_az_rad)
                uz = np.cos(steer_el_rad)
                phase = 2 * np.pi * freq / C * (pos[:, None, 0] * ux + pos[:, None, 1] * uy)
                a_steer = np.exp(-1j * phase)
                w = np.conj(a_steer) / ula_n
                ux_grid = np.sin(steer_el_rad) * np.cos(az_grid)
                uy_grid = np.sin(steer_el_rad) * np.sin(az_grid)
                phase_grid = 2 * np.pi * freq / C * (
                    pos[:, None, 0] * ux_grid[None, :]
                    + pos[:, None, 1] * uy_grid[None, :]
                )
                a_grid = np.exp(-1j * phase_grid)
                beam = np.sum(w[:, None] * a_grid, axis=0)
                B_arr = 10 * np.log10(np.maximum(np.abs(beam) ** 2, 1e-15))
            ax.plot(np.degrees(az_grid), B_arr, color=color, lw=1.5, label=label)
        ax.axhline(-3, color="red", ls="--", alpha=0.5)
        ax.set_xlabel("Azimuth from boresight (deg)")
        ax.set_ylabel("Response (dB)")
        ax.set_title("Dual-Ring vs ULA Beampattern")
        ax.set_xlim(-90, 90)
        ax.set_ylim(-40, 3)
        ax.legend()
        ax.grid(True, alpha=0.3)
        st.pyplot(fig)

    with st.expander("Key Takeaways", expanded=True):
        st.markdown(f"""
        - **Beamwidth**: {beamwidth_deg:.1f}° at {freq} Hz — narrower at higher frequencies
        - **N mics**: {array.n_mics} total across both rings
        - **Ring radii**: outer={ring1_radius:.2f}m, inner={ring2_radius:.2f}m
        - λ/2 at {freq} Hz: {0.5 * C / freq:.2f}m
        - The dual-ring gives omnidirectional coverage in azimuth, unlike a ULA
          which has 180° ambiguity
        """)


def _beamwidth(cut_dB: np.ndarray, az_deg: np.ndarray) -> float | None:
    above = cut_dB >= -3
    if not np.any(above):
        return None
    idx = np.where(above)[0]
    return az_deg[idx[-1]] - az_deg[idx[0]]


def _peak_sidelobe(B: np.ndarray) -> float | None:
    half = len(B) // 2
    center_third = len(B) // 3
    main_idx = slice(half - center_third // 2, half + center_third // 2)
    mask = np.ones(len(B), dtype=bool)
    mask[main_idx] = False
    if not np.any(mask):
        return None
    peak = np.max(B[mask])
    return 10 * np.log10(max(peak, 1e-15))


def _plot_array_geometry(array) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(6, 6))
    pos = array.positions
    m1 = array.n_mics_ring1
    ax.scatter(pos[:m1, 0], pos[:m1, 1], s=60, c="blue", edgecolors="black",
               label=f"Ring 1 ({m1} mics)")
    ax.scatter(pos[m1:, 0], pos[m1:, 1], s=60, c="orange", edgecolors="black",
               label=f"Ring 2 ({array.n_mics - m1} mics)")
    r1 = array.ring1_radius
    r2 = array.ring2_radius
    theta = np.linspace(0, 2 * np.pi, 200)
    ax.plot(r1 * np.cos(theta), r1 * np.sin(theta), "b--", alpha=0.5)
    ax.plot(r2 * np.cos(theta), r2 * np.sin(theta), "orange", ls="--", alpha=0.5)
    ax.set_aspect("equal")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.set_title("Array Geometry (top view)")
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig
