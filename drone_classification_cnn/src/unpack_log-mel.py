"""
Prepare dataset by splitting .npy file with long log-mel duration to shorter clips

Output: .npy files stored in folder with a label
"""

from pathlib import Path
import glob, os
import sys
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from configs.config import Config

def generate_dataset(folder_name: str) -> None:
    print("input:", Path(Config.DATA_INPUT_PATH).resolve(), "exists:", Path(Config.DATA_INPUT_PATH).exists())

    files = [file for file in Path(Config.DATA_INPUT_PATH).iterdir() if file.is_file()]

    num_clips = 0
    for file in files:
        data = np.load(file)

        print(f"Input shape: {data.shape}")
        print(f"Expected mel bins: {Config.N_MELS}")
        print(f"Clip frames: {Config.FRAMES}")

        assert data.ndim == 2, f"Expected 2D array, got {data.shape}"

        # Expected shape: (N_MELS, time_frames)
        assert data.shape[0] == Config.N_MELS, (
            f"Expected {Config.N_MELS} mel bins, got {data.shape[0]}"
        )

        folder = os.path.join(Config.DATA_OUTPUT_PATH, folder_name)
        os.makedirs(folder, exist_ok=True)

        for i, start in enumerate(
            range(0, data.shape[1] - Config.FRAMES + 1, Config.HOP_FRAMES)
        ):
            clip = data[:, start:start + Config.FRAMES]

            np.save(
                os.path.join(folder, f"{folder_name}_clip_{num_clips:05d}.npy"),
                clip
            )
            num_clips += 1

        print(f"Created {num_clips} clips in {Config.DATA_OUTPUT_PATH}")
        print(f"Clip shape: ({Config.N_MELS}, {Config.FRAMES})")
        print(f"Duration per clip: {Config.DURATION}s")

generate_dataset("background")
