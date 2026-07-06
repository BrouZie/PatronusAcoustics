"""Two-station bearing triangulation — geometric Monte Carlo, no audio.

A single station resolves only a bearing; the C2 fuses bearings from two
stations into a 3D position. Given the single-station bearing error the
simulation measures (e.g. `RangeCurve.angular_error_deg`), this module
predicts 3D position error over the coverage area — derisking the pitch's
two-station 20–70 m claim with pure geometry.

Standalone:
    python -m src.analysis.triangulation --baseline 40 --sigma 3
"""

import numpy as np

from ..geometry import direction_vectors


def bearing_to_vector(az_rad: float, el_rad: float) -> np.ndarray:
    return direction_vectors(np.atleast_2d(az_rad), np.atleast_2d(el_rad))[0]


def vector_to_bearing(v: np.ndarray) -> tuple[float, float]:
    v = v / np.linalg.norm(v)
    return float(np.arctan2(v[1], v[0])), float(np.arccos(np.clip(v[2], -1, 1)))


def triangulate(station_positions: np.ndarray, bearings: np.ndarray) -> np.ndarray:
    """Least-squares intersection of bearing rays.

    Minimizes the summed squared perpendicular distance to each ray
    (p_i, u_i):  x* = argmin Σ ||(I − u_i u_iᵀ)(x − p_i)||².

    Parameters
    ----------
    station_positions : (S, 3) station origins in world coordinates.
    bearings : (S, 2) az/el in radians (el = polar angle from +z).
    """
    station_positions = np.asarray(station_positions, dtype=float)
    bearings = np.asarray(bearings, dtype=float)
    A = np.zeros((3, 3))
    b = np.zeros(3)
    for p, (az, el) in zip(station_positions, bearings):
        u = bearing_to_vector(az, el)
        proj = np.eye(3) - np.outer(u, u)
        A += proj
        b += proj @ p
    return np.linalg.solve(A, b)


def position_error_map(baseline_m: float, bearing_sigma_deg: float,
                       extent_m: float = 100.0, altitude_m: float = 30.0,
                       grid_n: int = 41, n_trials: int = 100,
                       seed: int = 0) -> dict:
    """RMS 3D position error over an (x, y) grid at fixed drone altitude.

    Two stations sit at (±baseline/2, 0, 0); bearing noise with the given
    std is added independently to each station's az and el.
    """
    rng = np.random.default_rng(seed)
    sigma = np.radians(bearing_sigma_deg)
    stations = np.array([
        [-baseline_m / 2, 0.0, 0.0],
        [+baseline_m / 2, 0.0, 0.0],
    ])

    xs = np.linspace(-extent_m, extent_m, grid_n)
    ys = np.linspace(1.0, 2 * extent_m, grid_n)  # in front of the baseline
    err = np.zeros((grid_n, grid_n))

    for i, x in enumerate(xs):
        for j, y in enumerate(ys):
            target = np.array([x, y, altitude_m])
            true_bearings = np.array([
                vector_to_bearing(target - s) for s in stations
            ])
            trial_err = np.zeros(n_trials)
            for t in range(n_trials):
                noisy = true_bearings + rng.normal(0.0, sigma, size=(2, 2))
                est = triangulate(stations, noisy)
                trial_err[t] = np.linalg.norm(est - target)
            err[i, j] = float(np.sqrt(np.mean(trial_err ** 2)))

    return {"x_m": xs, "y_m": ys, "rms_error_m": err,
            "stations": stations, "altitude_m": altitude_m}


def plot_error_map(result: dict, out_path: str,
                   baseline_m: float, bearing_sigma_deg: float) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 6))
    x, y, err = result["x_m"], result["y_m"], result["rms_error_m"]
    im = ax.pcolormesh(x, y, np.minimum(err.T, 50.0), cmap="viridis",
                       shading="auto")
    fig.colorbar(im, ax=ax, label="RMS 3D position error (m, clipped at 50)")
    st = result["stations"]
    ax.scatter(st[:, 0], st[:, 1], marker="^", s=120, c="red",
               label="stations", zorder=5)
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.set_title(
        f"Two-station triangulation error — baseline {baseline_m:g} m, "
        f"bearing σ {bearing_sigma_deg:g}°, altitude {result['altitude_m']:g} m"
    )
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Two-station triangulation error map")
    parser.add_argument("--baseline", type=float, default=40.0, help="Station separation (m)")
    parser.add_argument("--sigma", type=float, default=3.0,
                        help="Single-station bearing error std (deg) — take from "
                             "a measured range curve at the range of interest")
    parser.add_argument("--extent", type=float, default=100.0)
    parser.add_argument("--altitude", type=float, default=30.0)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    out = args.out or str(
        Path(__file__).resolve().parent.parent.parent / "figures"
        / f"triangulation_b{args.baseline:g}_s{args.sigma:g}.png"
    )
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    result = position_error_map(args.baseline, args.sigma,
                                extent_m=args.extent, altitude_m=args.altitude)
    plot_error_map(result, out, args.baseline, args.sigma)
    print(f"Error map → {out}")
