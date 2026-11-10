import struct
import numpy as np
import serial

# --- must match firmware / Config ---
PORT          = "/dev/ttyACM0"
BAUD          = 921600
MAGIC         = 0x314C4D4C          # Config.MAGIC
Q_SCALE       = 1.50
Q_OFFSET      = -100.0
NUM_MEL_BANDS = 128                 # NUM_MEL_BANDS in firmware

HDR      = struct.Struct("<II8x")                  # magic, seq, then skip azimuth+elevation (2 x float32)
PKT_SIZE = HDR.size + NUM_MEL_BANDS                # 16 + 128 = 144 bytes
MAGIC_B  = struct.pack("<I", MAGIC)

def record(out_stem, n_frames):
    ser = serial.Serial(PORT, BAUD, timeout=0.5)
    ser.reset_input_buffer()

    buf = bytearray()
    cells = []
    last_seq, dropped = None, 0

    while len(cells) < n_frames:
        buf += ser.read(4096)
        while True:
            i = buf.find(MAGIC_B)
            if i < 0:
                del buf[:-3]                       # keep a possible partial magic word
                break
            if len(buf) < i + PKT_SIZE:
                if i > 0: del buf[:i]
                break
            nxt = i + PKT_SIZE
            if len(buf) >= nxt + 4 and buf[nxt:nxt + 4] != MAGIC_B:
                del buf[:i + 1]                    # false match inside payload, resync
                continue

            _, seq = HDR.unpack_from(buf, i)
            frame = np.frombuffer(buf, np.uint8, NUM_MEL_BANDS, i + HDR.size).astype(np.float32) / Q_SCALE + Q_OFFSET

            if last_seq is not None and seq != last_seq + 1:
                gap = seq - last_seq - 1
                dropped += gap
                cells.extend(np.full(NUM_MEL_BANDS, np.nan, np.float32) for _ in range(gap))
            last_seq = seq

            cells.append(frame)
            del buf[:nxt]

    ser.close()
    mel = np.stack(cells[:n_frames], axis=1)       # shape (n_mels, n_frames)
    np.save(f"{out_stem}.npy", mel)

    print(f"Logmel saved in {out_stem}.npy")



record("silence", 3750)

if __name__ == "__main_":
    record("test", 1000)
