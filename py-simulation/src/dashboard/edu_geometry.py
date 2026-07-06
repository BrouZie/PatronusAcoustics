"""
Educational array geometry comparison — dual-ring vs ULA vs UCA vs sparse.
"""

import numpy as np
import streamlit as st
from matplotlib import pyplot as plt

from src.geometry import DualRingArray, SingleRingArray
from src.config import ArrayConfig, SingleRingArrayConfig
from src.constants import SPEED_OF_SOUND_REF as C
from src.dashboard.utils import (
    beamwidth_from_cut,
    boresight_cut_db,
    peak_sidelobe_from_cut,
)


def render_array_geometry() -> None:
    st.header("Array Geometry Tradeoffs")

    with st.expander("How geometry affects the beampattern", expanded=True):
        st.markdown(r"""
        The beampattern of an array depends on three geometric factors:

        1. **Aperture size** — larger aperture → narrower beam
        2. **Number of elements** — more elements → better sidelobe suppression
        3. **Spatial arrangement** — determines angular coverage and ambiguity

        The array factor for $M$ elements at positions $\mathbf{p}_m$ is:

        $$B(f, \mathbf{u}) = \left| \sum_{m=1}^{M} w_m \, \exp\!\left(-j \frac{2\pi f}{c}
        \mathbf{p}_m \cdot \mathbf{u} \right) \right|^2$$

        where $\mathbf{u}$ is the direction unit vector and $w_m$ are the weights.
        """)

    st.subheader("Compare Array Types")

    freq = st.slider("Frequency (Hz)", 200, 3000, 1000, 50, key="geom_freq")
    n_elements = st.slider("Elements per geometry", 4, 32, 16, 2, key="geom_n")

    col1, col2 = st.columns(2)
    with col1:
        ring_radius = st.slider("Ring radius (m)", 0.05, 1.0, 0.34, 0.01, key="geom_radius")
    with col2:
        ula_spacing = st.slider("ULA spacing (λ)", 0.1, 2.0, 0.5, 0.05, key="geom_ula_sp")

    az_grid = np.radians(np.linspace(-90, 90, 721))

    arrays = _build_arrays(n_elements, ring_radius, ula_spacing, freq)

    patterns = {}
    for name, pos in arrays.items():
        pos = np.ascontiguousarray(pos, dtype=np.float64)
        patterns[name] = boresight_cut_db(
            pos.tobytes(), len(pos), float(freq), len(az_grid)
        )

    tab_compare, tab_metrics, tab_2d = st.tabs([
        "Beampattern Comparison", "Metrics", "2D Array Layout",
    ])

    with tab_compare:
        fig, ax = plt.subplots(figsize=(10, 5))
        colors = plt.cm.tab10(np.linspace(0, 1, len(patterns)))
        for (name, pattern), c in zip(patterns.items(), colors):
            ax.plot(np.degrees(az_grid), pattern, color=c, lw=1.5, label=name)
        ax.axhline(-3, color="red", ls="--", alpha=0.5, label="-3 dB")
        ax.set_xlabel("Angle from boresight (deg)")
        ax.set_ylabel("Response (dB)")
        ax.set_title(f"Beampattern Comparison at {freq} Hz")
        ax.set_xlim(-90, 90)
        ax.set_ylim(-40, 3)
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        st.pyplot(fig)

    with tab_metrics:
        _show_metrics_table(patterns, az_grid, arrays, freq)

    with tab_2d:
        fig, axes = plt.subplots(2, 2, figsize=(10, 10))
        for ax, (name, pos) in zip(axes.flat, arrays.items()):
            ax.scatter(pos[:, 0], pos[:, 1], s=30, alpha=0.8)
            ax.set_aspect("equal")
            ax.set_title(name)
            ax.set_xlabel("x (m)")
            ax.set_ylabel("y (m)")
            ax.grid(True, alpha=0.3)
        fig.tight_layout()
        st.pyplot(fig)

    with st.expander("Key Takeaways", expanded=True):
        st.markdown(f"""
        - **Beamwidth** scales with $\\lambda / D$ (wavelength / aperture)
        - **ULA** has 180° ambiguity (front-back) — good for 1D, poor for 2D
        - **Circular arrays** give uniform resolution in all azimuth directions
        - **Dual-ring** gives omnidirectional coverage with better vertical resolution
          than a single ring
        - **Sparse arrays** have higher sidelobes — more elements needed for clean pattern
        - λ/2 maximum spacing rule: {0.5 * C / freq:.2f} m keeps grating lobes at bay
        """)


def _build_arrays(n: int, radius: float, ula_spacing_lam: float, freq: float):
    lam = C / freq
    arrays = {}

    ring_n = n // 2
    cfg = ArrayConfig(
        ring1_radius=radius,
        ring2_radius=radius * 0.5,
        n_mics_ring1=ring_n,
        n_mics_ring2=n - ring_n,
        ring_spacing=0.2,
    )
    dual_ring = DualRingArray(cfg)
    arrays["Dual-Ring"] = dual_ring.positions

    ula_d = ula_spacing_lam * lam
    ula_pos = np.zeros((n, 3))
    ula_pos[:, 0] = np.arange(n) * ula_d - (n - 1) * ula_d / 2
    arrays["ULA"] = ula_pos

    uca = SingleRingArray(SingleRingArrayConfig(radius=radius, n_mics=n))
    arrays["UCA"] = uca.positions

    rng = np.random.RandomState(42)
    sparse_pos = np.zeros((n, 3))
    sparse_pos[:, 0] = rng.uniform(-radius, radius, n)
    sparse_pos[:, 1] = rng.uniform(-radius, radius, n)
    arrays["Sparse"] = sparse_pos

    return arrays


def _show_metrics_table(patterns, az_grid, arrays, freq):
    az_deg = np.degrees(az_grid)
    data = []
    for name, cut_dB in patterns.items():
        bw = beamwidth_from_cut(cut_dB, az_deg)
        psll = peak_sidelobe_from_cut(cut_dB)
        n = len(arrays[name])
        data.append((name, bw, psll, n))

    st.write("**Quantitative Comparison**")
    import pandas as pd
    df = pd.DataFrame(data, columns=["Array", "3 dB BW (deg)", "PSLL (dB)", "N elements"])
    st.dataframe(df, use_container_width=True)

    st.write(f"**Wavelength at {freq} Hz**: λ = {C/freq:.2f} m")
    st.write(f"**λ/2**: {0.5 * C/freq:.2f} m")

    if "Dual-Ring" in patterns and "ULA" in patterns:
        dr_bw = beamwidth_from_cut(patterns["Dual-Ring"], az_deg)
        ula_bw = beamwidth_from_cut(patterns["ULA"], az_deg)
        if dr_bw and ula_bw:
            st.write(f"**Dual-ring** BW: {dr_bw:.1f}° vs **ULA** BW: {ula_bw:.1f}°")
            st.write(f"Ratio: {dr_bw/ula_bw:.2f}×")
