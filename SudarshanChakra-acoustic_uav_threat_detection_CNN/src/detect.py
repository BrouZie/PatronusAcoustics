import struct
import numpy as np
import serial
import time
import torch
import torch.nn.functional as funct
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from configs.config import Config
from src.model import get_model

# Make sure these values match with log-mel configuratin on the STM and parameters used to train the CNN
####################################################

PORT = "/dev/ttyACM0"
BAUD = 921600
FRAMES = 61       # rows in the image (time)
BANDS = 128       # columns in the image (mel bands)
RATE = 16000      # sample rate, Hz
HOP = 512         # hop size in samples between frames
MIN_FREQ = 100    # Hz
MAX_FREQ = 8000   # Hz
FFT = 1024        # FFT size used
Q_SCALE = 1.50    # dequant: db = byte / Q_SCALE + Q_OFFSET
Q_OFFSET = -100.0 # db value of byte 0

####################################################

THRESHOLD = 0.5

MAGIC = 0x4C454D4C
MAGIC_BYTES = struct.pack("<I", MAGIC)
HDR = struct.Struct("<II")             # magic, seq
HDR_SIZE = HDR.size                    # 8
PACKET_SIZE = HDR_SIZE + FRAMES * BANDS

def normalize(db, top_db=80.0):
    """
    Convert a dequantised packet into the model's input image.

    Args:
        db:     (FRAMES, BANDS) absolute dB values from find_packet
                (time on rows, mel bands on columns).
        top_db: Dynamic range kept below the loudest pixel.

    Returns:
        (BANDS, FRAMES) float32 array in [0, 1], mel bands on rows.

    Uses a fixed scale (peak -> 1.0, -top_db -> 0.0) instead of per-image
    min-max. The model was trained on 1 s clips zero-padded to 2 s, so every
    training image had a silent half that pinned its minimum at -top_db.
    Live packets are 2 s of real audio, and the fixed scale reproduces that
    value range.
    """
    db = np.maximum(db - db.max(), -top_db)
    return np.ascontiguousarray(((db + top_db) / top_db).T)

def load_model(model_path):
    """
    Load and prepare model for inference.
    """
    if not model_path.exists():
        raise FileNotFoundError(f"Model not found at {model_path}")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    model = get_model(Config.MODEL_TYPE)
    checkpoint = torch.load(model_path, map_location=device, weights_only=False)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(device)
    model.eval()

    return model, device

def find_packet(buf):
    """
    (seq, image) of the next complete packet in buf, or None.
    MAGIC_BYTES need to match whats given in log_mel application.
    """
    at = buf.find(MAGIC_BYTES)
    if at < 0:
        del buf[:-len(MAGIC_BYTES)]      # keep tail: magic may be split across reads
        return None
    del buf[:at]                         # drop junk before the magic
    if len(buf) < PACKET_SIZE:
        return None                      # packet not fully received yet
    _, seq = HDR.unpack_from(buf)
    cells = np.frombuffer(bytes(buf[HDR_SIZE:PACKET_SIZE]), np.uint8)
    del buf[:PACKET_SIZE]
    image = cells.reshape(FRAMES, BANDS).astype(np.float32)
    return seq, image / Q_SCALE + Q_OFFSET

def predict(model, device, image, threshold):
    """
    Predict class and probabilites.
    """
    image = normalize(image)
    x = torch.from_numpy(image)[None, None].to(device)
    with torch.no_grad():
        probs = funct.softmax(model(x), dim=1)[0]
    prob_safe = probs[Config.SAFE_LABEL].item()
    prob_threat = probs[Config.THREAT_LABEL].item()
    is_threat = prob_threat >= threshold
    return {
        "status": "THREAT" if is_threat else "SAFE",
        "confidence": prob_threat if is_threat else prob_safe,
        "probabilities": {"safe": round(prob_safe, 4), "threat": round(prob_threat, 4)},
        "threshold_used": threshold,
    }
def print_alert(result, seq):
    p = result["probabilities"]
    if result["status"] == "THREAT":
        print("\n" + "!" * 60)
        print("!!! [ALERT] DRONE DETECTED !!!")
        print(f"  Packet: {seq}   Threat confidence: {p['threat']:.1%}")
        print("!" * 60)
    else:
        print(f"[CLEAR] packet {seq}  safe: {p['safe']:.1%}")

def detect(model, device, serial_port, baudrate, idle_timeout=None):
    """
    Full pipeline from receiving data to making a prediction 
    """
    buf = bytearray()
    last_seq = None
    try:
        with serial.Serial(serial_port, baudrate, timeout=1) as ser:
            print(f"Connected to {serial_port}")
            deadline = time.time() + idle_timeout if idle_timeout else None
            while deadline is None or time.time() < deadline:
                buf += ser.read(ser.in_waiting or 1)
                while (packet := find_packet(buf)):
                    seq, image = packet
                    if last_seq is not None and seq != (last_seq + 1) & 0xFFFFFFFF:
                        print(f"Sequence jump: {last_seq} -> {seq}")
                    last_seq = seq

                    result = predict(model, device, image, THRESHOLD)
                    print_alert(result, seq)
                    if idle_timeout:
                        deadline = time.time() + idle_timeout
    except serial.SerialException as e:
        print(f"Port {serial_port} unavailable: {e}")
    except KeyboardInterrupt:
        print("Stopped.")


if __name__ == "__main__":

    model, device = load_model(Config.MODEL_DIR / "best_model.pth")
    detect(model, device, PORT, BAUD) 
