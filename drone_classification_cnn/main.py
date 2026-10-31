#!/usr/bin/env python3
"""
Patronus Acoustic - Acoustic UAV Threat Detection System
======================================================

Main entry point for the defense-grade acoustic surveillance system.

Usage:
------
    # Unpacking .parquet files to sorted folder of the different labels
    # DISCLAIMER: Every dataset is different! Match the config file to your dataset
    python main.py --unpack_parquet

    # Complete pipeline: discover data, train model, evaluate
    python main.py --train --dataset

    # Data discovery only
    python main.py --discover --dataset

    # Real time drone classification from data received over UART
    python main.py --detect --model
"""

import os
import sys
import argparse
from pathlib import Path

# Ensure project root is in path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# Radeon RX 6700-series (Navi 22) is not officially supported by ROCm and
# crashes unless it is presented as gfx1030. Must be set before torch loads.
_NAVI22_IDS = {"0x1002:0x73df"}
for _dev in Path("/sys/class/drm").glob("card*/device"):
    try:
        _pci_id = f"{(_dev / 'vendor').read_text().strip()}:{(_dev / 'device').read_text().strip()}"
    except OSError:
        continue
    if _pci_id in _NAVI22_IDS:
        os.environ.setdefault("HSA_OVERRIDE_GFX_VERSION", "10.3.0")

from configs.config import Config


def run_data_discovery(dataset_name: str):
    """Execute data discovery pipeline."""
    from src.data_discovery import run_discovery
    return run_discovery(dataset_name=dataset_name)


def run_training(dataset_name: str):
    """Execute complete training pipeline."""
    from src.train import run_training as train_pipeline
    return train_pipeline(dataset_name=dataset_name)

def run_detection(model, serial_port):
    """Execute complete detection pipeline."""
    from src.detect import run_detection as detection_pipeline
    return detection_pipeline(model, serial_port)

def unpack_parquet(input_folder, output_folder):
    """Unpack .parquet files sorted folder with different labels"""
    from src.unpack_parquet import unpack_parquet
    return unpack_parquet(input_folder, output_folder)

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="SUDARSHANchakra - Acoustic UAV Threat Detection System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Pipeline Commands:
------------------
  --train           Run complete training pipeline (discover -> train -> evaluate)
  --discover        Discover and validate dataset only
  --detect          Real time detection with data sent over UART

Examples:
---------
  python main.py --train --dataset dataset
  python main.py --detect --model best.pth

Configuration:
--------------
  Edit configs/config.py to modify system parameters.
 """,
    )

    parser.add_argument(
        "--train",
        action="store_true",
        help="Run complete training pipeline",
    )
    parser.add_argument(
        "--dataset",
        type=str,
        required=False,
        default=None,
        help="Name of the dataset folder inside data/ (required for training)",
        )
    parser.add_argument(
        "--discover",
        action="store_true",
        help="Run data discovery only",
    )
    parser.add_argument(
        "--detect",
        action="store_true",
        help="Run live threat detection from UART stream",
    )
    parser.add_argument(
        "--unpack_parquet",
        action="store_true",
        help="Unpack .parquet files and sort with respect to label",
    )
    parser.add_argument(
        "--model",
        type=str,
        required=False,
        default=None,
        help="Name of the model inside outputs/model (required for detection)",
        )
    parser.add_argument(
        "--serial_port",
        type=str,
        required=False,
        default=None,
        help="Name of the serial port(Ex. /dev/ttyACM0)",
        )
    args = parser.parse_args()

    if args.discover:
        if not args.dataset:
            parser.error("--dataset is required when using --discovery")

        print("\n[MODE] Data Discovery")
        run_data_discovery(args.dataset)

    elif args.detect:
        if not args.model or not args.serial_port:
            parser.error("--model and --port is required when using --detect")
        print("[MODE] Detection Pipeline")
        run_detection(args.model, args.serial_port)

    elif args.train:
        if not args.dataset:
            parser.error("--dataset is required when using --train")

        print("\n[MODE] Training Pipeline")
        print(f"[DATASET] Selected: {args.dataset}")

        print("\nStep 1: Data Discovery")
        discovery = run_data_discovery(args.dataset)

        if discovery and discovery.validate_dataset():
            print("\nStep 2: Model Training")
            run_training(dataset_name=args.dataset)
        else:
            print("\n[ERROR] Dataset validation failed. Cannot proceed with training.")
            sys.exit(1)
    
    elif args.unpack_parquet:
        print("\n[MODE] Unpack .parquet files")
        unpack_parquet(Config.DATA_INPUT_PATH, Config.DATA_OUTPUT_PATH)

    else:
        parser.print_help()
        print("\n" + "=" * 60)
        print("Quick Start:")
        print("  1. Train the model:  python main.py --train --dataset <dataset_name>")
        print("  2. Run detection:    python main.py --detect --model <model.pth> --port <Serialport name>")
        print("=" * 60)


if __name__ == "__main__":
    main()
