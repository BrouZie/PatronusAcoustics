"""
Educational ground reflection visualization — image source model, path length
difference, frequency-dependent interference, and absorption effects.
"""

import numpy as np
import streamlit as st
from matplotlib import pyplot as plt

C = 343.0


def render_ground_reflection() -> None:
    st.header("Ground Reflection Physics")

    with st.expander("How it works", expanded=True):
        st.markdown(r"""
        When a microphone array is mounted above the ground, the sound from the
        drone reaches each microphone via **two paths**:

        1. **Direct path** — straight line from drone to microphone
        2. **Reflected path** — bounces off the ground, equivalent to an
           **image source** below the ground plane

        The reflected path has:
        - A longer path length → phase shift relative to the direct path
        - A reflection coefficient $R$ (amplitude scaling, possibly complex)
        - An inverted phase at hard boundaries ($R = -1$)

        The total pressure at the microphone is:

        $$p = p_{\text{direct}} + R \cdot p_{\text{reflected}}$$

        When the path difference creates a **180° phase shift**, the two
        components cancel → destructive interference → coherence loss.
        """)

    col1, col2 = st.columns([1, 2])

    with col1:
        height = st.slider("Array height (m)", 0.5, 20.0, 5.0, 0.5, key="gr_height")
        drone_dist = st.slider("Drone distance (m)", 5, 500, 50, 5, key="gr_dist")
        drone_el = st.slider("Drone elevation (deg)", 1, 90, 30, 1, key="gr_el")
        R_mag = st.slider("|Reflection coefficient|", 0.0, 1.0, 0.5, 0.05, key="gr_R")
        R_phase = st.slider("R phase (deg)", 0, 360, 180, 5, key="gr_phase")

    drone_z = drone_dist * np.sin(np.radians(drone_el))
    drone_x = drone_dist * np.cos(np.radians(drone_el))

    with col2:
        fig = _plot_geometry(height, drone_x, drone_z)
        st.pyplot(fig)

    st.subheader("Interference at the Array")

    freqs = np.linspace(20, 3000, 2000)
    R_complex = R_mag * np.exp(1j * np.radians(R_phase))

    mic_x = 0.0
    d_direct = np.sqrt((drone_x - mic_x)**2 + drone_z**2)
    d_reflected = np.sqrt((drone_x - mic_x)**2 + (drone_z + 2 * height)**2)
    delta_d = d_reflected - d_direct

    phase_diff = 2 * np.pi * freqs * delta_d / C
    total = 1.0 + R_complex * np.exp(-1j * phase_diff)
    gain_dB = 20 * np.log10(np.maximum(np.abs(total), 1e-15))

    tab_gain, tab_path, tab_coherence = st.tabs([
        "Frequency Response", "Path Geometry", "Coherence vs Range",
    ])

    with tab_gain:
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)

        ax1.plot(freqs, gain_dB, lw=1.0)
        ax1.axhline(0, color="gray", ls="--", alpha=0.4)
        ax1.axhline(-3, color="red", ls="--", alpha=0.3, label="-3 dB")
        ax1.set_ylabel("Gain (dB)")
        ax1.set_title(f"Combined Response at Array Center (Δd = {delta_d:.2f} m)")
        ax1.set_ylim(-15, 6)
        ax1.grid(True, alpha=0.3)
        ax1.legend(loc="lower right")

        ax2.semilogy(freqs, np.maximum(np.abs(total), 1e-15), lw=1.0)
        ax2.axhline(0.5, color="red", ls="--", alpha=0.3)
        ax2.set_xlabel("Frequency (Hz)")
        ax2.set_ylabel("|Gain| (linear)")
        ax2.grid(True, alpha=0.3)

        fig.tight_layout()
        st.pyplot(fig)

        freq_notch = C / (2 * delta_d) if delta_d > 0 else None
        if freq_notch:
            st.caption(f"First notch frequency: {freq_notch:.0f} Hz "
                       f"(quarter-wavelength = {delta_d/2:.2f} m)")

    with tab_path:
        _show_path_table(height, drone_x, drone_z, d_direct, d_reflected, delta_d, freqs, gain_dB)

    with tab_coherence:
        st.subheader("Coherence Loss vs Drone Range")
        ranges = np.linspace(10, 300, 100)
        freq_fixed = st.select_slider(
            "Frequency for range scan",
            options=[200, 400, 600, 800, 1000, 1500, 2000, 2500, 3000],
            value=1000, key="gr_coherence_freq",
        )
        coherence = _compute_coherence(
            height, ranges, drone_el, freq_fixed, R_complex
        )

        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(ranges, coherence, lw=1.5)
        ax.set_xlabel("Drone range (m)")
        ax.set_ylabel("|Gain| (linear)")
        ax.set_title(f"Coherence at {freq_fixed} Hz vs Range")
        ax.axhline(0.5, color="red", ls="--", alpha=0.4, label="-6 dB")
        ax.grid(True, alpha=0.3)
        ax.legend()
        fig.tight_layout()
        st.pyplot(fig)

        st.caption(
            "At short ranges the direct and reflected paths have similar lengths, "
            "causing strong interference notches. At long ranges the paths converge → "
            "the ground acts as a coherent reflector (ground = image source)."
        )

    with st.expander("Key Takeaways", expanded=True):
        st.markdown(f"""
        - **Path difference**: Δd = {delta_d:.2f} m
        - **First notch**: {C / (2 * delta_d) if delta_d > 0 else 'N/A' :.0f} Hz
        - **Absorptive ground (R < 0.5)**: weak reflection → little interference → no coherence loss
        - **Reflective ground (R > 0.8)**: strong interference → frequency-dependent notches
        - **Delany-Bazley (grass)**: R ≈ 0.8, frequency-dependent → destroys coherence across all bands
        - **Key sweep result**: mounting height (1–20 m) with constant R=0.5 gave 47–52% det;
          Delany-Bazley grass gave 0% det (coherence fully destroyed)
        """)


def _plot_geometry(height, drone_x, drone_z):
    fig, ax = plt.subplots(figsize=(8, 5))

    ax.plot([0], [height], marker="v", markersize=12, color="blue", zorder=5)
    ax.annotate("Array", (0, height), xytext=(0.3, height + 2), fontsize=9)

    ax.plot([drone_x], [drone_z], marker="^", markersize=10, color="red", zorder=5)
    ax.annotate("Drone", (drone_x, drone_z), xytext=(drone_x + 2, drone_z + 2), fontsize=9)

    image_z = -(drone_z + 2 * height)
    ax.plot([drone_x], [image_z], marker="s", markersize=8, color="gray",
            alpha=0.5, zorder=4)
    ax.annotate("Image Source", (drone_x, image_z),
                xytext=(drone_x + 2, image_z - 3), fontsize=9, alpha=0.6)

    ax.plot([-5, max(drone_x + 10, 50)], [0, 0], color="brown", lw=4, zorder=3)
    ax.fill_between([-5, max(drone_x + 10, 50)], -5, 0,
                    color="saddlebrown", alpha=0.15)

    ax.plot([0, drone_x], [height, drone_z], "g-", lw=2, alpha=0.8, label="Direct path")
    ax.plot([0, drone_x], [height, image_z], "orange", lw=2, alpha=0.6,
            label="Reflected path", ls="--")
    ax.plot([drone_x, drone_x], [drone_z, image_z], "gray", lw=1, alpha=0.3, ls=":")

    rfl_x = np.interp(0, [drone_z, image_z], [drone_x, drone_x])
    ax.scatter([drone_x * height / (height - image_z)], [0],
               marker="o", s=50, c="orange", alpha=0.7, zorder=6)
    ax.annotate("Reflection point", (drone_x * height / (height - image_z), 0),
                xytext=(drone_x * height / (height - image_z) + 2, -2), fontsize=8, alpha=0.7)

    ax.set_xlabel("Horizontal distance (m)")
    ax.set_ylabel("Height (m)")
    ax.set_title("Direct and Reflected Path Geometry")
    ax.set_xlim(-5, max(drone_x + 10, 50))
    ax.set_ylim(min(image_z, -5) - 2, max(drone_z, height) + 10)
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)
    ax.set_aspect("equal")
    fig.tight_layout()
    return fig


def _show_path_table(height, drone_x, drone_z, d_direct, d_reflected, delta_d,
                     freqs, gain_dB):
    st.write("**Path Geometry**")
    st.write(f"- Direct path length: {d_direct:.2f} m")
    st.write(f"- Reflected path length: {d_reflected:.2f} m")
    st.write(f"- Path difference: {delta_d:.2f} m")

    notch_freqs = []
    for n in range(1, 6):
        fn = (2 * n - 1) * C / (2 * delta_d) if delta_d > 0 else np.inf
        if fn <= 3000:
            notch_freqs.append(fn)
    if notch_freqs:
        st.write("**Interference notches:**")
        for i, fn in enumerate(notch_freqs):
            st.write(f"  {i+1}. {fn:.0f} Hz ({(2*(i+1)-1)}× λ/4 path diff)")

    idx = np.argmin(np.abs(freqs - 1000))
    st.write(f"\n**At 1000 Hz:** gain = {gain_dB[idx]:.1f} dB, "
             f"|gain| = {10**(gain_dB[idx]/20):.3f}")


def _compute_coherence(height, ranges, elevation_deg, freq, R_complex):
    el_rad = np.radians(elevation_deg)
    drone_z = ranges * np.sin(el_rad)
    drone_x = ranges * np.cos(el_rad)

    d_direct = np.sqrt(drone_x**2 + drone_z**2)
    d_reflected = np.sqrt(drone_x**2 + (drone_z + 2 * height)**2)
    delta_d = d_reflected - d_direct

    phase_diff = 2 * np.pi * freq * delta_d / C
    total = 1.0 + R_complex * np.exp(-1j * phase_diff)
    return np.abs(total)
