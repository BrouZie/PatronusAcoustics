"""
Patronus — Interactive Research Dashboard

Usage:
    streamlit run src/dashboard/app.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from src.config import Config
from src.results import SweepCatalog, cached_run, has_cached
from src.dashboard.forms import render_config_form
from src.dashboard.results_view import show_results
from src.dashboard.edu_beamforming import render_beamforming_basics
from src.dashboard.edu_ground import render_ground_reflection
from src.dashboard.edu_geometry import render_array_geometry


st.set_page_config(
    page_title="Patronus — Beamforming Simulation",
    page_icon="🎯",
    layout="wide",
)

st.title("🎯 Patronus — Dual-Ring SRP-PHAT Beamforming")
st.caption("Interactive research platform for acoustic drone detection simulation")

tab_sim, tab_sweeps, tab_edu = st.tabs([
    "**Simulation**",
    "**Sweep Results**",
    "**Educational**",
])

with tab_sim:
    config = render_config_form()

    run_col, cache_col = st.columns([1, 3])
    with run_col:
        run = st.button("▶ Run Simulation", type="primary", use_container_width=True)
    with cache_col:
        if has_cached(config):
            st.info(f"⚡ Cached results available — click Run to load from cache")

    if run:
        with st.spinner("Running simulation..."):
            results = cached_run(config)
        show_results(results)

with tab_sweeps:
    catalog = SweepCatalog()

    all_sweeps = catalog.list_sweeps()
    if not all_sweeps:
        st.info("No sweep results found. Run some sweeps first via `python -m src.sweep`")
    else:
        sweep_names = [d.name for d in all_sweeps]
        selected = st.selectbox("Select sweep run", sweep_names)
        sd = catalog.get(selected)
        if sd is not None:
            st.write(f"**Config:** {sd.sweep_config_path or 'N/A'}")
            st.write(f"**Completed:** {sd.n_completed} combinations")
            st.write(f"**Started:** {sd.started or 'N/A'}")

            df = catalog.to_dataframe(sd)
            st.dataframe(df, use_container_width=True)

            with st.expander("Summary Stats"):
                st.write(f"Detection rate range: {df['detection_rate'].min():.1%} – {df['detection_rate'].max():.1%}")
                if "mean_angular_error_deg" in df.columns:
                    st.write(f"Angular error range: {df['mean_angular_error_deg'].min():.2f}° – {df['mean_angular_error_deg'].max():.2f}°")

            param_cols = [c for c in df.columns if c.startswith("drone.") or c.startswith("srpphat.") or c.startswith("environment.")]
            metric_col = st.selectbox("Y-axis metric", ["detection_rate", "mean_angular_error_deg", "mean_psr_db"])
            if param_cols:
                param_col = st.selectbox("X-axis parameter", param_cols)
                if param_col and metric_col:
                    import matplotlib.pyplot as plt
                    fig, ax = plt.subplots(figsize=(8, 4))
                    ax.plot(df[param_col].astype(float), df[metric_col].astype(float),
                            marker="o", lw=1.5)
                    ax.set_xlabel(param_col)
                    ax.set_ylabel(metric_col)
                    ax.set_title(f"{metric_col} vs {param_col}")
                    ax.grid(True, alpha=0.3)
                    st.pyplot(fig)

with tab_edu:
    edu_tab1, edu_tab2, edu_tab3 = st.tabs([
        "Beamforming Basics",
        "Ground Reflection",
        "Array Geometry",
    ])
    with edu_tab1:
        render_beamforming_basics()
    with edu_tab2:
        render_ground_reflection()
    with edu_tab3:
        render_array_geometry()
