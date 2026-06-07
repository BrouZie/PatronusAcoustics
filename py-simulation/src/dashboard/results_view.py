"""Display simulation results in Streamlit."""

import streamlit as st
import numpy as np
import matplotlib.figure
from matplotlib import pyplot as plt


def show_results(results: dict) -> None:
    """Render simulation results in the dashboard."""
    metrics = results["metrics"]
    n_frames = results.get("n_frames", 0)

    st.subheader("Results Summary")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Detection Rate", f"{metrics.detection_rate:.1%}")
    with col2:
        st.metric("Mean Angular Error", f"{metrics.mean_angular_error_deg:.2f}°")
    with col3:
        st.metric("Std Angular Error", f"{metrics.std_angular_error_deg:.2f}°")
    with col4:
        st.metric("Mean PSR", f"{metrics.mean_psr_db:.1f} dB")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Max Angular Error", f"{metrics.max_angular_error_deg:.2f}°")
    with col2:
        st.metric("Mean Beamwidth", f"{metrics.mean_beamwidth_deg:.2f}°")
    with col3:
        st.metric("Frames", str(n_frames))

    st.subheader("Diagnostic Plots")

    tab_timeline, tab_psr, tab_error_hist = st.tabs([
        "Angular Error Timeline", "PSR Timeline", "Error Distribution",
    ])

    timestamps = results.get("timestamps", np.array([]))
    angular_errors = getattr(metrics, "angular_errors_deg", np.array([]))
    psrs = getattr(metrics, "peak_to_sidelobe_ratios_db", np.array([]))

    with tab_timeline:
        if len(angular_errors) > 0 and len(timestamps) > 0:
            fig = _timeline_figure(timestamps, angular_errors)
            st.pyplot(fig)
        else:
            st.info("No angular error data available")

    with tab_psr:
        if len(psrs) > 0 and len(timestamps) > 0:
            fig = _psr_figure(timestamps, psrs)
            st.pyplot(fig)
        else:
            st.info("No PSR data available")

    with tab_error_hist:
        valid = angular_errors[~np.isnan(angular_errors)] if len(angular_errors) > 0 else np.array([])
        if len(valid) > 0:
            fig = _histogram_figure(valid)
            st.pyplot(fig)
        else:
            st.info("No valid angular error data available")


def _timeline_figure(timestamps: np.ndarray, errors: np.ndarray) -> matplotlib.figure.Figure:
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.plot(timestamps, errors, lw=0.8)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Angular Error (deg)")
    ax.set_title("Angular Error Over Time")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig


def _psr_figure(timestamps: np.ndarray, psrs: np.ndarray) -> matplotlib.figure.Figure:
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.plot(timestamps, psrs, lw=0.8, color="green")
    ax.axhline(y=3.0, color="red", linestyle="--", alpha=0.5, label="3 dB threshold")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("PSR (dB)")
    ax.set_title("Peak-to-Sidelobe Ratio Over Time")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig


def _histogram_figure(errors: np.ndarray) -> matplotlib.figure.Figure:
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.hist(errors, bins=30, alpha=0.7, edgecolor="black")
    ax.set_xlabel("Angular Error (deg)")
    ax.set_ylabel("Count")
    ax.set_title("Angular Error Distribution")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig
