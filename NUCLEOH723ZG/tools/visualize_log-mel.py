import numpy as np
import matplotlib.pyplot as plt
import sys

data = np.load(sys.argv[1])

plt.imshow(data, aspect="auto", origin="lower", cmap="magma")
plt.colorbar(label="Log-Mel")
plt.xlabel("Time frames")
plt.ylabel("Mel bins")
plt.title(f"Log-Mel Spectrogram - {data.shape}")
plt.tight_layout()
plt.show()