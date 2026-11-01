"""Live log-mel spectrogram viewer for the NUCLEO-H723ZG `log-mel` app
CNN-pipeline variant.

Geometry, rate, and quantization are fixed by the trained model, so they're
compile-time constants here (mirrored in firmware) rather than fields on the
wire. The board sends one packet per frame:

    struct __attribute__((packed)) {
        uint32_t magic;      // must be LOGMEL_MAGIC
        uint32_t seq;        // increments every frame; used to detect drops
        float    azimuth;
        float    elevation;
        uint8_t  cells[128]; // one spectrogram column
    };                       // 144 bytes

Bump MAGIC whenever FRAMES/BANDS/RATE/HOP/FFT/quant range change, so a stale
binary can never feed the CNN a shape it wasn't trained on.

Columns are drawn as soon as they arrive, about one frame behind the board.

    uv run tools/logmel_viewer_cnn.py
"""

import signal
import struct
import sys
from collections import deque

import numpy as np
import pyqtgraph as pg
import serial
from pyqtgraph.Qt import QtCore

# --- Config: serial device and display preferences.
PORT = "/dev/ttyACM0"
# PORT = "/tmp/ttySIM0"
BAUD = 921600

SECONDS_SHOWN = 12.0        # width of the scrolling view
# AUTO_LEVELS = True          # track the signal's own range; False uses LEVELS
AUTO_LEVELS = False          # track the signal's own range; False uses LEVELS
LEVELS = (-100, 30)
TICK_MS = 20
IDLE_TICKS = 150            # warn after ~3 s with no packet

# --- Fixed by the trained model. Must match src/dsp/log-mel_spectogram.c and
# --- whatever produced the training set exactly, or the CNN sees a shape or
# --- scale it was never trained on. Bump MAGIC if any of these change.
FRAMES = 61                # rows in the image (time)
BANDS = 128                   # columns in the image (mel bands)
RATE = 16000                 # sample rate, Hz
HOP = 512                    # hop size in samples between frames
MIN_FREQ = 100                # Hz
MAX_FREQ = 8000              # Hz
FFT = 1024                    # FFT size used
Q_SCALE = 1.5                # dequant: db = byte / Q_SCALE + Q_OFFSET
Q_OFFSET = -100.0

# These values needs to match with the ones in STM32

MAGIC = 0x314C4D4C             # "LML1"
MAGIC_BYTES = struct.pack("<I", MAGIC)
HDR = struct.Struct("<IIff")           # magic, seq, azimuth, elevation
HDR_SIZE = HDR.size                    # 16
PACKET_SIZE = HDR_SIZE + BANDS         # one packet per frame

port = None
buf = bytearray()
pending = deque()               # columns waiting to be drawn
img = img_rect = centers = None
idle_ticks = nbytes = ncolumns = ndropped = 0
last_seq = None
sample_bytes = bytearray()      # first bytes seen, for the no-header diagnostic



def find_packet():
    """(seq, column) of the next complete buffered packet, or None. Sheds
    bytes ahead of the first plausible magic so junk cannot accumulate."""
    start = 0
    while True:
        at = buf.find(MAGIC_BYTES, start)
        if at < 0:
            # Keep the tail: a magic word may be split across two reads.
            del buf[: -len(MAGIC_BYTES)]
            return None
        del buf[:at]
        if len(buf) < HDR_SIZE:
            return None
        magic, seq, _, _ = HDR.unpack_from(buf)
        if magic != MAGIC:
            start = len(MAGIC_BYTES)         # false match, look past it
            continue
        if len(buf) < PACKET_SIZE:
            return None
        # bytes() first: a frombuffer view would keep the bytearray exported
        # and block the del below.
        cells = np.frombuffer(bytes(buf[HDR_SIZE:PACKET_SIZE]), np.uint8)
        del buf[:PACKET_SIZE]
        return seq, cells.astype(np.float32) / Q_SCALE + Q_OFFSET


def mel_centers_hz():
    """Band centre frequencies, mirroring mel_filterbank_init() in
    src/dsp/log-mel_spectogram.c. float32 throughout, to land on the same side
    of floorf() as the firmware. Only the firmware's centre clamp matters here;
    its right-edge clamp cannot move a centre."""
    f = np.float32
    to_mel = lambda hz: f(2595) * np.log10(f(1) + f(hz) / f(700))

    lo, hi = to_mel(MIN_FREQ), to_mel(MAX_FREQ)
    step = (hi - lo) / f(BANDS + 1)
    spacing = f(RATE) / f(FFT)
    mels = lo + np.arange(BANDS + 2, dtype=f) * step
    bins = np.floor((f(700) * (f(10.0) ** (mels / f(2595)) - f(1))) / spacing).astype(int)

    return np.maximum(bins[1:BANDS + 1], bins[:BANDS] + 1) * float(spacing)


def configure():
    """Geometry is fixed by the model, so the view can be sized before the
    first packet ever arrives."""
    global img, img_rect, centers

    centers = mel_centers_hz()
    per_s = RATE / HOP
    img = np.full((max(FRAMES, int(SECONDS_SHOWN * per_s)), BANDS),
                  Q_OFFSET, dtype=np.float32)
    img_rect = QtCore.QRectF(0, 0, SECONDS_SHOWN, BANDS)

    plot.setXRange(0, SECONDS_SHOWN, padding=0)
    plot.setYRange(0, BANDS, padding=0)
    stride = max(1, BANDS // 10)
    plot.getAxis("left").setTicks(
        [[(b + 0.5, f"{centers[b]:.0f}") for b in range(0, BANDS, stride)]])
    plot.setTitle(f"log-mel {FRAMES} x {BANDS} | {RATE} Hz, hop {HOP} "
                  f"({per_s:.1f} col/s) | {MIN_FREQ}-{MAX_FREQ} Hz | "
                  f"{10.0 / Q_SCALE:.2f} dB/step")

    print(f"{per_s:.2f} col/s; "
          f"packet {PACKET_SIZE} B = {PACKET_SIZE * 10 / BAUD * 1e3:.1f} ms on the wire, "
          f"{PACKET_SIZE * 10 * per_s / BAUD * 100:.1f}% of the link")


def redraw():
    """Move every column received so far into the image, then paint it."""
    global img

    n = min(len(pending), img.shape[0])
    if n > 0:
        img = np.roll(img, -n, axis=0)
        img[-n:] = list(pending)[-n:]
        pending.clear()

    if AUTO_LEVELS:
        lo, hi = np.percentile(img, (2.0, 99.8))
        levels = (float(lo), float(max(hi, lo + 0.5)))
    else:
        levels = LEVELS
    img_item.setImage(img, levels=levels, autoLevels=False)
    # setImage resets the item's rect to the array's pixel size, which would
    # stretch a 1000-column image across a 12-unit view. Re-impose it every time.
    img_item.setRect(img_rect)


def status():
    if idle_ticks < IDLE_TICKS:
        peak = int(np.argmax(img[-1]))
        drop = f"  dropped {ndropped}" if ndropped else ""
        label.setText(f"columns {ncolumns}{drop} | seq {last_seq} | "
                      f"peak band {peak} "
                      f"({centers[peak]:.0f} Hz)")
        return
    # Say which half of the link is at fault: silence is a port/flash problem,
    # bytes without a header is a format problem on the board.
    if nbytes == 0:
        label.setText(f"no bytes at all on {PORT} @ {BAUD} - is the board connected, "
                      "is the log-mel app the one flashed, and is this the right device?")
    else:
        label.setText(f"{nbytes} bytes arriving but no valid header - expected magic "
                      f"{MAGIC_BYTES.hex(' ')} ('LML1'). If the board's geometry/rate/quant "
                      f"were retrained, bump MAGIC here to match. "
                      f"First bytes: {sample_bytes.hex(' ')}")


def poll():
    global idle_ticks, nbytes, ncolumns, ndropped, last_seq

    chunk = port.read(port.in_waiting or 1)
    nbytes += len(chunk)
    sample_bytes.extend(chunk[: 16 - len(sample_bytes)])
    buf.extend(chunk)

    got = 0
    while (packet := find_packet()) is not None:
        seq, column = packet
        if last_seq is not None:
            ndropped += seq - last_seq - 1
        last_seq = seq
        ncolumns += 1
        pending.append(column)
        got += 1

    idle_ticks = 0 if got else idle_ticks + 1
    redraw()
    status()


def main():
    global port, plot, img_item, label

    try:
        port = serial.Serial(PORT, BAUD, timeout=0)
    except serial.SerialException as e:
        print(f"Could not open {PORT}: {e}")
        print("Check that the board is connected and that PORT/BAUD at the top of this "
              "file match your setup.")
        sys.exit(1)

    app = pg.mkQApp()
    win = pg.GraphicsLayoutWidget(title="log-mel")
    win.resize(1400, 800)
    win.show()

    plot = win.addPlot(row=0, col=0, title="log-mel")
    img_item = pg.ImageItem()
    # A viridis-ish ramp, spelled out so the tool needs no matplotlib.
    cmap = pg.ColorMap(pos=[0.0, 0.25, 0.5, 0.75, 1.0],
                       color=[(0, 0, 40), (0, 80, 140), (0, 170, 140),
                              (180, 210, 60), (255, 255, 180)])
    img_item.setLookupTable(cmap.getLookupTable(nPts=256))
    plot.addItem(img_item)
    plot.setLabel("bottom", "seconds (oldest left)")
    plot.setLabel("left", "mel band centre (Hz)")

    label = pg.LabelItem(justify="left")
    win.addItem(label, row=1, col=0)
    win.ci.layout.setRowStretchFactor(0, 1)   # image takes the window

    # Geometry is fixed, so the view can be built before any packet arrives.
    configure()

    timer = QtCore.QTimer()
    timer.timeout.connect(poll)
    timer.start(TICK_MS)

    def handle_sigint(signum, frame):
        print("\nClosing log-mel viewer...")
        app.quit()

    # Qt's event loop would otherwise keep Python from seeing SIGINT, so an idle
    # timer hands control back periodically.
    signal.signal(signal.SIGINT, handle_sigint)
    sigint_timer = QtCore.QTimer()
    sigint_timer.timeout.connect(lambda: None)
    sigint_timer.start(100)

    try:
        app.exec()
    finally:
        timer.stop()
        sigint_timer.stop()
        if port.is_open:
            port.close()
        win.close()


if __name__ == "__main__":
    main()
