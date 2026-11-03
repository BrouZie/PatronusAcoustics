"""
Prepare dataset by splitting long .wav file into smaller files 

Take folder_name as input, this can either be drone or background
Edit input and output paths in config to match application

Output: .wav files stored in folder with a label
"""

from pathlib import Path
import glob, os
import sys
from pydub import AudioSegment

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from configs.config import Config

def generate_dataset(folder_name: str) -> None:
    output_duration_ms = int(Config.DURATION * 1000)

    print("input:", Path(Config.DATA_INPUT_PATH).resolve(), "exists:", Path(Config.DATA_INPUT_PATH).exists())

    audio_file = AudioSegment.from_wav(Config.DATA_INPUT_PATH)

    clip_index = 0
    for start in range(0, len(audio_file), output_duration_ms):
        end = start + output_duration_ms
        clip = audio_file[start:end]

        folder = os.path.join(Config.DATA_OUTPUT_PATH, folder_name)
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"{folder_name}_train_{clip_index:06d}.wav")

        if len(clip) < output_duration_ms:
            continue

        clip.export(path, format="wav")

        clip_index += 1
        print(f"{path} is finished writing!")

    print("=" * 60)
    print(f"Dataset generation complete. Generated {clip_index} clips.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage: python src/wav_dataset_generator.py <dataset_name>")
    generate_dataset(sys.argv[1])
