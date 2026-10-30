#!/usr/bin/env python3
"""
SUDARSHANchakra - Acoustic UAV Threat Detection System
======================================================

Main entry point for the defense-grade acoustic surveillance system.

Named after the divine discus weapon of Lord Vishnu - the Sudarshana Chakra -
this system serves as a protective guardian, detecting aerial threats
through acoustic signature analysis.

Usage:
------
    # Complete pipeline: ingest data, train model, evaluate
    python main.py --train

    # Data ingestion only
    python main.py --ingest

    # Inference on audio file
    python main.py --detect path/to/audio.wav

    # Run demonstration
    python main.py --demo

Author: Defense AI Systems
Version: 1.0.0
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


def run_data_ingestion(dataset_name: str):
    """Execute data ingestion pipeline."""
    from src.data_ingestion import run_ingestion
    return run_ingestion(dataset_name=dataset_name)


def run_training(dataset_name: str):
    """Execute complete training pipeline."""
    from src.train import run_training as train_pipeline
    return train_pipeline(dataset_name=dataset_name)

def run_detection():
    """Execute complete detection pipeline."""
    from src.detect import run_detection as detection_pipeline
    return detection_pipeline()

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="SUDARSHANchakra - Acoustic UAV Threat Detection System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Pipeline Commands:
------------------
  --train           Run complete training pipeline (ingest -> train -> evaluate)
  --ingest          Download and prepare dataset only
  --detect          Analyze audio for threats
  --demo            Run demonstration with sample data

Examples:
---------
  python main.py --train
  python main.py --detect recording.wav
  python main.py --detect recording.wav --threshold 0.3
  python main.py --demo

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
        "--ingest",
        action="store_true",
        help="Run data ingestion only",
    )
    parser.add_argument(
        "--detect",
        action="store_true",
        help="Run live threat detection from UART stream",
    )
    parser.add_argument(
        "--config",
        action="store_true",
        help="Display current configuration",
    )

    args = parser.parse_args()

    # Execute requested operation
    if args.config:
        Config.print_config()

    elif args.ingest:
        if not args.dataset:
            parser.error("--dataset is required when using --ingest")

        print("\n[MODE] Data Ingestion")
        run_data_ingestion(args.dataset)

    elif args.detect:
        print("[MODE] Detection Pipeline")
        run_detection()

    elif args.train:
        if not args.dataset:
            parser.error("--dataset is required when using --train")

        print("\n[MODE] Training Pipeline")
        print(f"[DATASET] Selected: {args.dataset}")

        print("\nStep 1: Data Ingestion")
        ingestion = run_data_ingestion(args.dataset)

        if ingestion and ingestion.validate_dataset():
            print("\nStep 2: Model Training")
            run_training(dataset_name=args.dataset)
        else:
            print("\n[ERROR] Dataset validation failed. Cannot proceed with training.")
            sys.exit(1)

    else:
        parser.print_help()
        print("\n" + "=" * 60)
        print("Quick Start:")
        print("  1. Train the model:  python main.py --train")
        print("  2. Run detection:    python main.py --detect audio.wav")
        print("=" * 60)


if __name__ == "__main__":
    main()
