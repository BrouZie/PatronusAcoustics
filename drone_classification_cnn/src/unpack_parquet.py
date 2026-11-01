"""
Unpack parquet to sorted wav files

Make sure to change:
    DATA_INPUT_PATH depending on where your data is stored
    DATA_OUTPUT_PATH for wanted location of new data
    class_names, check for number of classes and labels

Output: .wav files stored in two folders, drone and unknown depending on the label
"""

import sys
from pathlib import Path
import glob, os
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from configs.config import Config

def unpack_parquet(input_folder, output_folder):
    """
    Args:
        input_folder: Location of all the .parquet file
        output_folder: Location of output sorted files

    Make sure Config.LABEL_TO_FOLDER fit with the unpacked dataset 
    """

    print("input:", Path(input_folder).resolve(), "exists:", Path(input_folder).exists())
    print("found:", list(Path(input_folder).rglob("*.parquet"))[:5])

    counter = 0
    for file in sorted(glob.glob(os.path.join(input_folder, "**", "*.parquet"), recursive=True)):
        n = pq.ParquetFile(file).metadata.num_rows
        print(Path(file).name, n)
        pf = pq.ParquetFile(file)
        for batch in pf.iter_batches(batch_size=500):
            for row in batch.to_pylist():
                label = Config.LABEL_TO_FOLDER[row["label"]]
                folder = os.path.join(output_folder, label)
                os.makedirs(folder, exist_ok=True)

                counter += 1
                path = os.path.join(folder, f"train_{counter:06d}.wav")
                with open(path, "wb") as out:
                    out.write(row["audio"]["bytes"])
        print(f"Finished unpacking file: {file}")

    print(f"Wrote {counter} files")

if __name__ == "__main__":
    unpack_parquet(Config.DATA_INPUT_PATH, Config.DATA_OUTPUT_PATH)
