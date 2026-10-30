"""
Unpack parquet to sorted wav files 

Make sure to change: 
    DATA_INPUT_PATH depending on where your data is stored
    DATA_OUTPUT_PATH for wanted location of new data
    class_names, double check 0 is background and 1 is drone

Output: .wav files stored in two folders, drone and unknown depending on the label
"""

import sys
from pathlib import Path
import glob, os
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from configs.config import Config

parquet_dir = ROOT / Config.DATA_INPUT_PATH
output_dir = ROOT / Config.DATA_OUTPUT_PATH
class_names = {0: Config.BACKGROUND_FOLDER, 1: Config.DRONE_FOLDER}

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
