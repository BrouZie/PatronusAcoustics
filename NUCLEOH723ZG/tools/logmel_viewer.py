"""Live log-mel spectrogram viewer for the NUCLEO-H723ZG `log-mel` app.

The board sends one packet per image: a 32-byte header (src/types/logmel_packet.h)
followed by frames x bands cells, one byte each. The reader syncs on the header's
magic word and takes its geometry, scaling and axis labels from the header, so
PORT and BAUD below are the only things that must match the board.

An image is a second of audio delivered in a ~66 ms burst, so columns are queued
and drawn at the rate they were captured: the picture scrolls smoothly, one image
behind the board, instead of lurching once a second.

    uv run tools/logmel_viewer.py
"""

import signal
import struct
import sys
from collections import deque, namedtuple

import numpy as np
import pyqtgraph as pg
import serial
from pyqtgraph.Qt import QtCore

# --- Config. Only the serial device and display preferences; the wire format
# --- describes itself.
PORT = "/dev/ttyACM0"
BAUD = 921600

SECONDS_SHOWN = 12.0        # width of the scrolling view
AUTO_LEVELS = True          # track the signal's own range; False uses LEVELS
LEVELS = (-6.0, 4.0)
TICK_MS = 20
IDLE_TICKS = 150            # warn after ~3 s with no packet

MAGIC = 0x4C454D4C
MAGIC_BYTES = struct.pack("<I", MAGIC)
HDR = struct.Struct("<IIHHIHHHHff")          # magic, then the fields below
HDR_SIZE = HDR.size                          # 32
Header = namedtuple("Header", "seq frames bands rate hop min_freq max_freq fft "
                              "q_scale q_offset")

port = None
buf = bytearray()
pending = deque()               # columns waiting to be drawn
img = img_rect = centers = None
cols_per_tick = 1.0
credit = 0.0                    # fractional columns owed to the display
frames_per_image = 1
configured = False
last_seq = None
idle_ticks = nbytes = nimages = ndropped = 0
sample_bytes = bytearray()      # first bytes seen, for the no-header diagnostic


def parse_header(raw):
    """Validated header at the front of `raw`, or None. The bounds matter: a
    false magic match would have to carry a plausible geometry too."""
    magic, *fields = HDR.unpack_from(raw)
    h = Header(*fields)
    ok = (magic == MAGIC
          and 0 < h.frames <= 4096 and 0 < h.bands <= 512
          and 1000 <= h.rate <= 384000 and h.hop > 0 and h.fft > 0
          and h.q_scale > 0.0 and np.isfinite(h.q_scale) and np.isfinite(h.q_offset)
          and 0 <= h.min_freq < h.max_freq <= h.rate // 2)
    return h if ok else None


def find_packet():
    """(header, image) of the next complete buffered packet, or None. Sheds
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
        h = parse_header(buf)
        if h is None:
            start = len(MAGIC_BYTES)         # false match, look past it
            continue
        size = HDR_SIZE + h.frames * h.bands
        if len(buf) < size:
            return None
        # bytes() first: a frombuffer view would keep the bytearray exported
        # and block the del below.
        cells = np.frombuffer(bytes(buf[HDR_SIZE:size]), np.uint8)
        del buf[:size]
        image = cells.reshape(h.frames, h.bands).astype(np.float32)
        return h, image / h.q_scale + h.q_offset


def mel_centers_hz(h):
    """Band centre frequencies, mirroring mel_filterbank_init() in
    src/dsp/log-mel_spectogram.c. float32 throughout, to land on the same side
    of floorf() as the firmware. Only the firmware's centre clamp matters here;
    its right-edge clamp cannot move a centre."""
    f = np.float32
    to_mel = lambda hz: f(2595) * np.log10(f(1) + f(hz) / f(700))

    lo, hi = to_mel(h.min_freq), to_mel(h.max_freq)
    step = (hi - lo) / f(h.bands + 1)
    spacing = f(h.rate) / f(h.fft)
    mels = lo + np.arange(h.bands + 2, dtype=f) * step
    bins = np.floor((f(700) * (f(10.0) ** (mels / f(2595)) - f(1))) / spacing).astype(int)

    return np.maximum(bins[1:h.bands + 1], bins[:h.bands] + 1) * float(spacing)


def configure(h):
    """First packet decides the geometry: size the view and label the axes."""
    global img, img_rect, centers, cols_per_tick, configured

    centers = mel_centers_hz(h)
    per_s = h.rate / h.hop
    cols_per_tick = per_s * TICK_MS / 1000.0
    img = np.full((max(h.frames, int(SECONDS_SHOWN * per_s)), h.bands),
                  h.q_offset, dtype=np.float32)
    img_rect = QtCore.QRectF(0, 0, SECONDS_SHOWN, h.bands)

    plot.setXRange(0, SECONDS_SHOWN, padding=0)
    plot.setYRange(0, h.bands, padding=0)
    stride = max(1, h.bands // 10)
    plot.getAxis("left").setTicks(
        [[(b + 0.5, f"{centers[b]:.0f}") for b in range(0, h.bands, stride)]])
    plot.setTitle(f"log-mel {h.frames} x {h.bands} | {h.rate} Hz, hop {h.hop} "
                  f"({per_s:.1f} col/s) | {h.min_freq}-{h.max_freq} Hz | "
                  f"{10.0 / h.q_scale:.2f} dB/step")
    configured = True

    size, secs = HDR_SIZE + h.frames * h.bands, h.frames * h.hop / h.rate
    print(f"{h.frames} x {h.bands} image every {secs:.2f} s ({per_s:.2f} col/s); "
          f"packet {size} B = {size * 10 / BAUD * 1e3:.0f} ms on the wire, "
          f"{size * 10 / secs / BAUD * 100:.1f}% of the link")


def redraw():
    """Move queued columns into the image at the rate they were captured, then
    paint it."""
    global img, credit

    if pending:
        # Catch up rather than fall further behind if the queue is running long.
        credit += cols_per_tick * (2 if len(pending) > 2 * frames_per_image else 1)
        n = int(credit)
        if n > 0:
            credit -= n
            n = min(n, len(pending))
            img = np.roll(img, -n, axis=0)
            img[-n:] = [pending.popleft() for _ in range(n)]

    if img is None:
        return
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
        if configured:
            peak = int(np.argmax(img[-1]))
            drop = f"  dropped {ndropped}" if ndropped else ""
            label.setText(f"images {nimages}{drop} | seq {last_seq} | "
                          f"queue {len(pending)} | peak band {peak} "
                          f"({centers[peak]:.0f} Hz)")
        return
    # Say which half of the link is at fault: silence is a port/flash problem,
    # bytes without a header is a format problem on the board.
    if nbytes == 0:
        label.setText(f"no bytes at all on {PORT} @ {BAUD} - is the board connected, "
                      "is the log-mel app the one flashed, and is this the right device?")
    else:
        label.setText(f"{nbytes} bytes arriving but no valid header - expected magic "
                      f"{MAGIC_BYTES.hex(' ')} ('LMEL'). "
                      f"First bytes: {sample_bytes.hex(' ')}")


def poll():
    global idle_ticks, nbytes, nimages, ndropped, last_seq, frames_per_image

    chunk = port.read(port.in_waiting or 1)
    nbytes += len(chunk)
    sample_bytes.extend(chunk[: 16 - len(sample_bytes)])
    buf.extend(chunk)

    got = 0
    while (packet := find_packet()) is not None:
        h, image = packet
        if not configured:
            configure(h)
        frames_per_image = h.frames
        if last_seq is not None:
            ndropped += h.seq - last_seq - 1
        last_seq = h.seq
        nimages += 1
        pending.extend(image)
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

    plot = win.addPlot(row=0, col=0, title="waiting for a packet...")
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
