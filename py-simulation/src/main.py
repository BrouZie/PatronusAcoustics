import argparse
import os
import platform
import sys
from pathlib import Path

import yaml


def _has_display():
    if platform.system() == "Darwin":
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


import matplotlib

if not _has_display():
    matplotlib.use("Agg")

from .config import Config, deep_merge
from .simulation import Simulation


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Patronus — Dual-Ring SRP-PHAT Beamforming Simulation"
    )
    parser.add_argument(
        "-c", "--config",
        default=str(Path(__file__).resolve().parent.parent / "config" / "default.yaml"),
        help="Path to YAML configuration file",
    )
    parser.add_argument(
        "-o", "--output-dir",
        default=str(Path(__file__).resolve().parent.parent / "output"),
        help="Root output directory (a run-specific subfolder is created inside)",
    )
    parser.add_argument(
        "--run-name", default=None,
        help="Custom run name (default: {config_basename}_{timestamp})",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print the run name and output path without executing",
    )
    parser.add_argument(
        "--ring1-radius", type=float, default=None,
        help="Override ring 1 radius (m)"
    )
    parser.add_argument(
        "--ring2-radius", type=float, default=None,
        help="Override ring 2 radius (m)"
    )
    parser.add_argument(
        "--n-mics-1", type=int, default=None,
        help="Override mic count on ring 1"
    )
    parser.add_argument(
        "--n-mics-2", type=int, default=None,
        help="Override mic count on ring 2"
    )
    parser.add_argument(
        "--ring-spacing", type=float, default=None,
        help="Override ring spacing (m)"
    )
    parser.add_argument(
        "--snr", type=float, default=None,
        help="Override SNR (dB)"
    )
    parser.add_argument(
        "--duration", type=float, default=None,
        help="Override simulation duration (s)"
    )
    parser.add_argument(
        "--azimuth", type=float, default=None,
        help="Override source azimuth (deg)"
    )
    parser.add_argument(
        "--elevation", type=float, default=None,
        help="Override source elevation (deg)"
    )
    parser.add_argument(
        "--moving", action="store_true",
        help="Enable drone motion"
    )
    parser.add_argument(
        "--no-animation", action="store_true",
        help="Skip animation rendering"
    )
    parser.add_argument(
        "--no-3d-animation", action="store_true",
        help="Skip animation rendering (legacy alias)"
    )
    parser.add_argument(
        "--no-figures", action="store_true",
        help="Skip summary figures"
    )
    parser.add_argument(
        "--quick", action="store_true",
        help="Fast iteration mode: 4s duration, 4° resolution, max_freq=2000, no animation",
    )
    parser.add_argument(
        "--interactive", action="store_true",
        help="Show interactive figure after saving (requires display)",
    )
    parser.add_argument(
        "--profile", action="store_true",
        help="Run with cProfile and print top-20 time stats",
    )
    return parser.parse_args(argv)


def apply_overrides(config, args):
    overrides = {}
    if args.ring1_radius is not None:
        overrides.setdefault("array", {})["ring1_radius"] = args.ring1_radius
    if args.ring2_radius is not None:
        overrides.setdefault("array", {})["ring2_radius"] = args.ring2_radius
    if args.n_mics_1 is not None:
        overrides.setdefault("array", {})["n_mics_ring1"] = args.n_mics_1
    if args.n_mics_2 is not None:
        overrides.setdefault("array", {})["n_mics_ring2"] = args.n_mics_2
    if args.ring_spacing is not None:
        overrides.setdefault("array", {})["ring_spacing"] = args.ring_spacing
    if args.snr is not None:
        overrides.setdefault("signal", {})["snr_db"] = args.snr
    if args.duration is not None:
        overrides.setdefault("signal", {})["duration"] = args.duration
    if args.azimuth is not None or args.elevation is not None:
        bearing = {}
        if args.azimuth is not None:
            bearing["azimuth_deg"] = args.azimuth
        if args.elevation is not None:
            bearing["elevation_deg"] = args.elevation
        overrides.setdefault("drone", {})["initial_bearing"] = bearing
    if args.moving:
        overrides.setdefault("drone", {}).setdefault("motion", {})["enabled"] = True
    if args.quick:
        overrides.setdefault("signal", {})["duration"] = 4.0
        overrides.setdefault("srpphat", {}).setdefault("search", {})["resolution_deg"] = 4.0
        overrides.setdefault("srpphat", {})["max_freq"] = 2000.0
        overrides.setdefault("output", {})["save_animation"] = False
        overrides.setdefault("output", {})["save_3d_animation"] = False
    if args.no_animation or args.no_3d_animation:
        overrides.setdefault("output", {})["save_animation"] = False
        overrides.setdefault("output", {})["save_3d_animation"] = False
    if args.no_figures:
        overrides.setdefault("output", {})["save_figures"] = False

    if overrides:
        with open(args.config) as f:
            base = yaml.safe_load(f)
        deep_merge(base, overrides)
        return Config.from_dict(base)
    return config


def _run_name(config_path, args):
    if args.run_name:
        return args.run_name
    stem = config_path.stem
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{stem}_{ts}"


def run_simulation(config, run_dir=None, profile=False):
    sim = Simulation(config)

    if profile:
        import cProfile
        import pstats
        profiler = cProfile.Profile()
        profiler.enable()
        results = sim.run()
        profiler.disable()
        stats = pstats.Stats(profiler).sort_stats("cumtime")
        stats.print_stats(20)
    else:
        results = sim.run()

    if run_dir is not None:
        run_dir = Path(run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        if config.output.save_data:
            sim.save_results(results, run_dir)
        if config.output.save_figures or config.output.save_animation or config.output.save_3d_animation:
            sim.plot_results(results, run_dir)

    return results


def main(argv=None):
    args = parse_args(argv)
    config_path = Path(args.config)

    if not config_path.exists():
        print(f"Config file not found: {config_path}", file=sys.stderr)
        return 1

    run_name = _run_name(config_path, args)
    run_dir = Path(args.output_dir) / run_name

    if args.dry_run:
        print(f"Config:  {config_path.resolve()}")
        print(f"Run:     {run_name}")
        print(f"Output:  {run_dir.resolve()}")
        return 0

    config = Config.from_yaml(str(config_path))
    config = apply_overrides(config, args)

    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"Run:  {run_name}")
    print(f"Out:  {run_dir.resolve()}\n")

    results = run_simulation(config, run_dir=run_dir, profile=args.profile)

    m = results["metrics"]
    print("\n=== Results Summary ===")
    print(f"  Mean Angular Error:  {m.mean_angular_error_deg:.2f}°")
    print(f"  Std Angular Error:   {m.std_angular_error_deg:.2f}°")
    print(f"  Max Angular Error:   {m.max_angular_error_deg:.2f}°")
    print(f"  Mean PSR:            {m.mean_psr_db:.1f} dB")
    print(f"  Mean Beamwidth:      {m.mean_beamwidth_deg:.2f}°")
    print(f"\nOutput: {run_dir.resolve()}")

    if args.interactive and _has_display():
        import matplotlib.pyplot as plt
        print("\nInteractive window open — rotate the 3D view with your mouse. Close to exit.")
        plt.show(block=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
