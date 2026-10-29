"""
Unpack parquet from geronimobasso/drone-audio-detection-samples on HuggingFace

Output: .wav files stored in two folders, drone and unknown depending on the label
"""

import sys
from pathlib import Path
import glob, os
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from configs.config import Config

parquet_dir = ROOT / Config.INPUT_PATH
output_dir = ROOT / Config.OUTPUT_PATH
class_names = {0: "no_drone", 1: "drone"}

counter = 0
for file in sorted(glob.glob(os.path.join(parquet_dir, "**", "*.parquet"), recursive=True)):
    n = pq.ParquetFile(file).metadata.num_rows
    print(Path(file).name, n)
    pf = pq.ParquetFile(file)
    for batch in pf.iter_batches(batch_size=500):
        for row in batch.to_pylist():
            label = class_names[row["label"]]
            folder = os.path.join(output_dir, label)
            os.makedirs(folder, exist_ok=True)

            counter += 1
            path = os.path.join(folder, f"train_{counter:06d}.wav")
            with open(path, "wb") as out:
                out.write(row["audio"]["bytes"])
    print(f"Finished unpacking file: {file}")

print(f"Wrote {counter} files")
