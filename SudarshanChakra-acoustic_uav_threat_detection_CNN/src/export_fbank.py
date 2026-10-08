import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from src.data_loader import LogMelSpectrogram

fb = LogMelSpectrogram().mel.mel_scale.fb.numpy().T   # (128 mels, 513 bins)

starts, counts, weights = [], [], []
for row in fb:
    nz = np.nonzero(row)[0]
    if len(nz) == 0:
        starts.append(0); counts.append(0); continue
    s, e = nz[0], nz[-1] + 1
    starts.append(s); counts.append(e - s); weights.extend(row[s:e])

with open("mel_fbank.h", "w") as f:
    f.write("#ifndef MEL_FBANK_H\n#define MEL_FBANK_H\n#include <stdint.h>\n\n")
    f.write(f"#define MEL_WEIGHT_COUNT {len(weights)}\n\n")
    f.write(f"static const uint16_t MEL_START[{len(starts)}] = {{{','.join(map(str, starts))}}};\n")
    f.write(f"static const uint16_t MEL_COUNT[{len(counts)}] = {{{','.join(map(str, counts))}}};\n")
    f.write("static const float MEL_WEIGHTS[MEL_WEIGHT_COUNT] = {"
            + ",".join(f"{w:.9g}f" for w in weights) + "};\n\n#endif\n")
print(len(weights), "weights")
