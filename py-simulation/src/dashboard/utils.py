"""Shared dashboard helpers: cached beampattern computation and cut metrics.

The cached functions take positions as raw bytes (hashable for
st.cache_data) and rebuild an `ArrayGeometry`, so the educational tabs
exercise the same production code the simulation uses.
"""

import numpy as np
import streamlit as st

from src.beampattern import array_response
from src.geometry import ArrayGeometry


def beamwidth_from_cut(cut_db: np.ndarray, angle_deg: np.ndarray) -> float | None:
    """-3 dB width of a beampattern cut, or None when nothing is above -3 dB."""
    above = cut_db >= -3
    if not np.any(above):
        return None
    idx = np.where(above)[0]
    return angle_deg[idx[-1]] - angle_deg[idx[0]]


def peak_sidelobe_from_cut(cut_db: np.ndarray) -> float | None:
    """Highest response (dB) outside the central-third mainlobe region."""
    half = len(cut_db) // 2
    center_third = len(cut_db) // 3
    main_idx = slice(half - center_third // 2, half + center_third // 2)
    mask = np.ones(len(cut_db), dtype=bool)
    mask[main_idx] = False
    if not np.any(mask):
        return None
    linear = 10 ** (cut_db / 10)
    peak = np.max(linear[mask])
    return 10 * np.log10(max(peak, 1e-15))


def _array_from_bytes(positions: bytes, n_mics: int) -> ArrayGeometry:
    pos = np.frombuffer(positions, dtype=np.float64).reshape(n_mics, 3)
    return ArrayGeometry(pos)


@st.cache_data(show_spinner=False)
def beampattern_grid(positions: bytes, n_mics: int, freq: float,
                     n_az: int = 721, n_el: int = 361) -> np.ndarray:
    """Boresight-steered power response over az ∈ [-90°, 90°], el ∈ [0°, 90°]."""
    array = _array_from_bytes(positions, n_mics)
    az = np.radians(np.linspace(-90, 90, n_az))
    el = np.radians(np.linspace(0, 90, n_el))
    AZ, EL = np.meshgrid(az, el, indexing="ij")
    return array_response(array, freq, AZ, EL)


@st.cache_data(show_spinner=False)
def boresight_cut_db(positions: bytes, n_mics: int, freq: float,
                     n_points: int = 721) -> np.ndarray:
    """Boresight-steered cut through the xz-plane (θ from boresight, dB)."""
    array = _array_from_bytes(positions, n_mics)
    theta = np.radians(np.linspace(-90, 90, n_points))
    az = np.where(theta < 0, np.pi, 0.0).reshape(-1, 1)
    el = np.abs(theta).reshape(-1, 1)
    B = array_response(array, freq, az, el)[:, 0]
    return 10 * np.log10(np.maximum(B, 1e-15))
