"""
Data Discovery Module
Automatic dataset acquisition and validation for DroneAudioDataset.

This module handles:
2. Directory structure discovery and validation
3. Locating Binary_Drone_Audio data paths dynamically
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple, Dict, List

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from configs.config import Config


class DatasetDiscovery:
    """
    Handles automatic dataset path discovery.
    """

    def __init__(self, dataset_name: str):
        self.data_root = Config.DATA_DIR
        self.data_dir = self.data_root / dataset_name

        # Prevent selecting paths outside the data directory
        if self.data_dir.resolve().parent != self.data_root.resolve():
            raise ValueError("Invalid dataset selection.")

        if not self.data_dir.exists():
            raise FileNotFoundError(
                f"Dataset '{dataset_name}' was not found at {self.data_dir}"
            )

        if not self.data_dir.is_dir():
            raise NotADirectoryError(
                f"'{self.data_dir}' is not a directory."
            )

        # Potential folder names for binary classification
        self.drone_keyword = Config.DRONE_FOLDER
        self.background_keyword = Config.BACKGROUND_FOLDER

        print(f"[DATASET] Selected: {dataset_name}")
        print(f"[DATASET] Location: {self.data_dir}")

    def print_directory_tree(self, max_depth: int = 4) -> None:
        """
        Print the directory structure of the cloned dataset.

        Args:
            max_depth: Maximum depth to traverse
        """
        print("\n" + "=" * 60)
        print("DATASET DIRECTORY STRUCTURE")
        print("=" * 60)

        if not self.data_dir.exists():
            print("[ERROR] Dataset not found. Run clone_repository() first.")
            return

        for root, dirs, files in os.walk(self.data_dir):
            # Calculate depth
            depth = root.replace(str(self.data_dir), "").count(os.sep)
            if depth > max_depth:
                continue

            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith(".")]

            indent = "│   " * depth
            folder_name = os.path.basename(root)
            print(f"{indent}├── {folder_name}/")

            # Show files (limit to prevent overflow)
            sub_indent = "│   " * (depth + 1)
            wav_files = [f for f in files if f.endswith(".wav")]
            other_files = [f for f in files if not f.endswith(".wav")]

            for f in other_files[:5]:
                print(f"{sub_indent}├── {f}")

            if wav_files:
                print(f"{sub_indent}├── [{len(wav_files)} .wav files]")

        print("=" * 60 + "\n")

    def find_binary_data_paths(self) -> Tuple[Optional[Path], Optional[Path]]:
        """
        Locate the specific paths for binary classification data.

        Searches for directories containing 'Drone' and 'Background'/'Unknown'
        audio files, prioritizing the Binary_Drone_Audio folder structure.

        Returns:
            Tuple of (drone_path, background_path) or (None, None) if not found
        """
        print("\n[INFO] Searching for binary classification audio data...")

        drone_path = None
        background_path = None

        # First, look for Binary_Drone_Audio specific structure
        for root, dirs, files in os.walk(self.data_dir):
            root_path = Path(root)
            name = root_path.name.lower()

            # Check if this directory contains wav files
            if not any(f.lower().endswith(".wav") for f in files):
                continue

            if drone_path is None and self.drone_keyword in name:
                drone_path = root_path
                print(f"[FOUND] Drone audio: {root_path}")
            elif background_path is None and self.background_keyword in name:
                background_path = root_path
                print(f"[FOUND] Background audio: {root_path}")

        # Final validation
        if drone_path and background_path:
            print("\n[SUCCESS] Binary classification data located!")
            print(f"  Drone Path:      {drone_path}")
            print(f"  Background Path: {background_path}")
        else:
            print("\n[WARNING] Could not locate both required directories.")
            print("  Please verify the dataset structure manually.")

        return drone_path, background_path

    def get_all_audio_files(self) -> Tuple[List[Path], List[Path]]:
        """
        Get lists of all drone and background audio files.

        Returns:
            Tuple of (drone_files, background_files)
        """
        drone_path, background_path = self.find_binary_data_paths()

        drone_files = []
        background_files = []

        if drone_path and drone_path.exists():
            drone_files = list(drone_path.glob("*.wav")) + list(drone_path.glob("*.WAV"))

        if background_path and background_path.exists():
            background_files = list(background_path.glob("*.wav")) + list(background_path.glob("*.WAV"))

        print(f"\n[DATA SUMMARY]")
        print(f"  Drone samples:      {len(drone_files)}")
        print(f"  Background samples: {len(background_files)}")
        print(f"  Total samples:      {len(drone_files) + len(background_files)}")

        return drone_files, background_files

    def validate_dataset(self) -> bool:
        """
        Validate that the dataset is properly downloaded and structured.

        Returns:
            bool: True if dataset is valid
        """
        print("\n[INFO] Validating dataset integrity...")

        drone_files, background_files = self.get_all_audio_files()

        if len(drone_files) == 0:
            print("[ERROR] No drone audio files found!")
            return False

        if len(background_files) == 0:
            print("[ERROR] No background audio files found!")
            return False

        # Check file accessibility
        sample_drone = drone_files[0]
        sample_background = background_files[0]

        try:
            # Verify files are readable
            with open(sample_drone, "rb") as f:
                header = f.read(4)
                if header != b"RIFF":
                    print(f"[WARNING] {sample_drone} may not be a valid WAV file")

            with open(sample_background, "rb") as f:
                header = f.read(4)
                if header != b"RIFF":
                    print(f"[WARNING] {sample_background} may not be a valid WAV file")

            print("[SUCCESS] Dataset validation passed!")
            return True

        except Exception as e:
            print(f"[ERROR] File validation failed: {e}")
            return False


def run_discovery(dataset_name: str):
    """Execute the complete data discovery pipeline."""
    print("\n" + "=" * 60)
    print("DATA DISCOVERY PIPELINE")
    print("Acoustic UAV Threat Detection System")
    print("=" * 60)

    discovery = DatasetDiscovery(dataset_name)

    # Step 1: Print directory structure
    discovery.print_directory_tree()

    # Step 2: Locate binary data paths
    drone_path, background_path = discovery.find_binary_data_paths()

    # Step 3: Validate dataset
    if discovery.validate_dataset():
        print("\n[READY] Dataset is ready for training!")
        return discovery
    else:
        print("\n[WARNING] Dataset validation failed. Please check the data.")
        return discovery


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage: python src/data_discovery.py <dataset_name>")
    run_discovery(sys.argv[1])
