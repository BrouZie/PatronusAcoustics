"""Live SRP-PHAT map viewer for the NUCLEO-H723ZG `srp-phat` app.

The board sends one packet per map: a 48-byte header (src/types/srp_packet.h)
followed by az_steps x el_steps float32 cells, azimuth major. The reader syncs
on the header's magic word and takes the grid geometry and axis labels from the
header, so PORT and BAUD below are the only things that must match the board.

What you are looking at is the steered response power over the whole search
grid, not just the winning direction. That matters during bring-up: a wrong
bearing and a genuinely ambiguous one produce the same az/el pair but very
different pictures. A compact planar array should show a broad ridge, and a
two-microphone pair should show a full CONE -- a closed band of equally-good
directions -- which is correct physics, not a bug.

Elevation is the POLAR ANGLE FROM BORESIGHT: 0 deg is straight ahead, 90 deg is
in the plane of the ring.

    uv run tools/srp_viewer.py
"""

import signal
import struct
import sys
from collections import namedtuple

import numpy as np
import pyqtgraph as pg
import serial
from pyqtgraph.Qt import QtCore

# --- Config. Only the serial device and display preferences; the wire format
# --- describes itself.
PORT = "/dev/ttyACM0"
BAUD = 921600

TICK_MS = 20
IDLE_TICKS = 150            # warn after ~3 s with no packet
AUTO_LEVELS = True          # track the map's own range; False uses LEVELS
LEVELS = (0.0, 1.0)

MAGIC = 0x50505253
MAGIC_BYTES = struct.pack("<I", MAGIC)
HDR = struct.Struct("<IHHHHffffIffffffHHI")
HDR_SIZE = HDR.size                          # 64
Header = namedtuple("Header", "version mics az_steps el_steps az_start az_step "
                              "el_start el_step frame peak_az peak_el "
                              "coherence level_db gate_coherence gate_level_db "
                              "detected bins reserved")

port = None
buf = bytearray()
configured = False
one_d = False               # degenerate grid: draw a curve, not a heatmap
axis_deg = None             # the varying angle, in degrees, for 1-D mode
last_frame = None
frame_stride = None         # firmware decimation, learned from the stream
idle_ticks = nbytes = nmaps = ndropped = 0
header = None
sample_bytes = bytearray()  # first bytes seen, for the no-header diagnostic


def parse_header(raw):
    """Validated header at the front of `raw`, or None. The bounds matter: a
    false magic match would have to carry a plausible grid too."""
    magic, *fields = HDR.unpack_from(raw)
    h = Header(*fields)
    ok = (magic == MAGIC and h.version == 3
          and 0 < h.mics <= 64
          and 0 < h.az_steps <= 2048 and 0 < h.el_steps <= 2048
          and h.az_steps * h.el_steps <= 1 << 20
          and h.az_step > 0.0 and h.el_step > 0.0
          and 0 < h.bins <= 8192
          and all(np.isfinite(v) for v in (h.az_start, h.az_step, h.el_start,
                                           h.el_step, h.coherence, h.level_db,
                                           h.gate_coherence, h.gate_level_db))
          and h.detected in (0, 1))
    return h if ok else None


def find_packet():
    """(header, map) of the next complete buffered packet, or None. Sheds bytes
    ahead of the first plausible magic so junk cannot accumulate."""
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
        size = HDR_SIZE + 4 * h.az_steps * h.el_steps
        if len(buf) < size:
            return None
        # bytes() first: a frombuffer view would keep the bytearray exported
        # and block the del below.
        cells = np.frombuffer(bytes(buf[HDR_SIZE:size]), np.float32)
        del buf[:size]
        if not np.all(np.isfinite(cells)):
            start = len(MAGIC_BYTES)         # payload cannot be a real map
            continue
        return h, cells.reshape(h.az_steps, h.el_steps)


def configure(h):
    """First packet decides the grid: size the view and label the axes.

    A grid with a single elevation row (or a single azimuth column) is not a
    picture, it is a curve -- and a curve is what a linear pair of microphones
    actually produces, since the only thing a pair measures is the angle to its
    own axis. Drawing that as a one-pixel-tall heatmap strip would hide the
    shape of the response, which is the part worth looking at."""
    global img_rect, configured, one_d, axis_deg

    one_d = h.az_steps == 1 or h.el_steps == 1
    if one_d:
        if h.el_steps == 1:
            axis_deg = h.az_start + np.arange(h.az_steps) * h.az_step
            xlabel = f"azimuth (deg), elevation fixed at {h.el_start:.0f}"
        else:
            axis_deg = h.el_start + np.arange(h.el_steps) * h.el_step
            xlabel = f"elevation from boresight (deg), azimuth fixed at {h.az_start:.0f}"

        img_item.hide()
        curve.show()
        peak_line.show()
        mean_line.show()
        gate_line.show()
        plot.setLabel("bottom", xlabel)
        plot.setLabel("left", "steered response power")
        plot.setXRange(float(axis_deg[0]), float(axis_deg[-1]), padding=0.02)
        plot.enableAutoRange(axis="y")
        plot.showGrid(x=True, y=True, alpha=0.3)
        plot.setTitle(f"SRP-PHAT sweep, {len(axis_deg)} directions | {h.mics} mics")
        configured = True
        size = HDR_SIZE + 4 * h.az_steps * h.el_steps
        print(f"1-D sweep of {len(axis_deg)} directions, packet {size} B = "
              f"{size * 10 / BAUD * 1e3:.1f} ms on the wire at {BAUD} baud")
        return

    curve.hide()
    peak_line.hide()
    mean_line.hide()
    gate_line.hide()
    img_item.show()

    # Cells are CENTRED on their angle, so the image starts half a step before
    # the first one. Without this every label sits on a cell edge.
    img_rect = QtCore.QRectF(h.az_start - h.az_step / 2.0,
                             h.el_start - h.el_step / 2.0,
                             h.az_steps * h.az_step,
                             h.el_steps * h.el_step)
    plot.setXRange(img_rect.left(), img_rect.right(), padding=0)
    plot.setYRange(img_rect.top(), img_rect.bottom(), padding=0)
    plot.setTitle(f"SRP-PHAT {h.az_steps} x {h.el_steps} grid | {h.mics} mics | "
                  f"az {h.az_start:.0f}-{h.az_start + (h.az_steps - 1) * h.az_step:.0f} deg, "
                  f"el {h.el_start:.0f}-{h.el_start + (h.el_steps - 1) * h.el_step:.0f} deg "
                  f"(polar from boresight)")
    configured = True

    size = HDR_SIZE + 4 * h.az_steps * h.el_steps
    print(f"{h.az_steps} x {h.el_steps} map, packet {size} B = "
          f"{size * 10 / BAUD * 1e3:.0f} ms on the wire at {BAUD} baud")


def show(h, srp_map):
    if one_d:
        y = srp_map.ravel()
        curve.setData(axis_deg, y)
        peak_line.setValue(float(h.peak_az if h.el_steps == 1 else h.peak_el))
        # PHAT pins the map's scale: mics that agree perfectly peak at
        # mics^2 * bins, mics looking at diffuse noise sit at mics * bins.
        # Drawing the gate between them turns "why did it not say DETECTED"
        # into something you can see rather than infer.
        floor = h.mics * h.bins
        ceil_ = h.mics * floor
        gate_line.setValue(float(floor + h.gate_coherence * (ceil_ - floor)))
        mean_line.setValue(float(floor))
        return

    levels = None
    if AUTO_LEVELS:
        lo, hi = np.percentile(srp_map, (1.0, 100.0))
        levels = (float(lo), float(max(hi, lo + 1e-6)))
    else:
        levels = LEVELS
    img_item.setImage(srp_map, levels=levels, autoLevels=False)
    # setImage resets the item's rect to the array's pixel size, which would
    # draw a 72x19 grid across 72x19 degrees. Re-impose it every time.
    img_item.setRect(img_rect)
    peak.setData([h.peak_az], [h.peak_el])


def status():
    if idle_ticks < IDLE_TICKS:
        if configured and header is not None:
            h = header
            drop = f"  dropped {ndropped}" if ndropped else ""
            # Name the gate that failed: "no detection" on its own sends you
            # hunting through the wrong half of the signal chain.
            if h.detected:
                gate = "DETECTED"
            elif h.coherence < h.gate_coherence and h.level_db < h.gate_level_db:
                gate = "no detection (too quiet, and mics disagree)"
            elif h.level_db < h.gate_level_db:
                gate = "no detection (too quiet)"
            else:
                gate = "no detection (mics disagree about a direction)"
            label.setText(f"maps {nmaps}{drop} | frame {h.frame} | "
                          f"peak az {h.peak_az:.0f} deg  el {h.peak_el:.0f} deg | "
                          f"coherence {h.coherence:.2f}/{h.gate_coherence:.2f} | "
                          f"level {h.level_db:.1f}/{h.gate_level_db:.0f} dBFS | {gate}")
        return
    # Say which half of the link is at fault: silence is a port/flash problem,
    # bytes without a header is a format problem on the board.
    if nbytes == 0:
        label.setText(f"no bytes at all on {PORT} @ {BAUD} - is the board connected, "
                      "is the srp-phat app the one flashed, and is this the right device?")
    else:
        label.setText(f"{nbytes} bytes arriving but no valid header - expected magic "
                      f"{MAGIC_BYTES.hex(' ')} ('SRPP'). "
                      f"First bytes: {sample_bytes.hex(' ')}")


def poll():
    global idle_ticks, nbytes, nmaps, ndropped, last_frame, frame_stride, header

    chunk = port.read(port.in_waiting or 1)
    nbytes += len(chunk)
    sample_bytes.extend(chunk[: 16 - len(sample_bytes)])
    buf.extend(chunk)

    got = None
    while (packet := find_packet()) is not None:
        h, srp_map = packet
        if not configured:
            configure(h)

        # frame_index counts AUDIO frames, so consecutive packets are one
        # firmware decimation apart. Learn that stride from the smallest gap
        # seen, then any larger multiple of it is a dropped packet.
        if last_frame is not None:
            gap = h.frame - last_frame
            if gap > 0:
                frame_stride = gap if frame_stride is None else min(frame_stride, gap)
                ndropped += round(gap / frame_stride) - 1
        last_frame = h.frame

        header = h
        nmaps += 1
        got = (h, srp_map)      # only the newest map is worth painting

    if got is not None:
        show(*got)
    idle_ticks = 0 if got else idle_ticks + 1
    status()


def main():
    global port, plot, img_item, peak, label, curve, peak_line, mean_line, gate_line

    try:
        port = serial.Serial(PORT, BAUD, timeout=0)
    except serial.SerialException as e:
        print(f"Could not open {PORT}: {e}")
        print("Check that the board is connected and that PORT/BAUD at the top of this "
              "file match your setup.")
        sys.exit(1)

    app = pg.mkQApp()
    win = pg.GraphicsLayoutWidget(title="SRP-PHAT")
    win.resize(1400, 700)
    win.show()

    plot = win.addPlot(row=0, col=0, title="waiting for a packet...")
    img_item = pg.ImageItem()
    # A viridis-ish ramp, spelled out so the tool needs no matplotlib.
    cmap = pg.ColorMap(pos=[0.0, 0.25, 0.5, 0.75, 1.0],
                       color=[(0, 0, 40), (0, 80, 140), (0, 170, 140),
                              (180, 210, 60), (255, 255, 180)])
    img_item.setLookupTable(cmap.getLookupTable(nPts=256))
    plot.addItem(img_item)
    peak = pg.ScatterPlotItem(size=16, pen=pg.mkPen("r", width=2),
                              brush=None, symbol="o")
    plot.addItem(peak)

    # Used only when the grid collapses to a single row or column.
    curve = pg.PlotCurveItem(pen=pg.mkPen((120, 200, 255), width=2))
    peak_line = pg.InfiniteLine(angle=90, pen=pg.mkPen("r", width=2))
    mean_line = pg.InfiniteLine(angle=0, pen=pg.mkPen((130, 130, 130), width=1,
                                                      style=QtCore.Qt.PenStyle.DotLine))
    gate_line = pg.InfiniteLine(angle=0, pen=pg.mkPen((255, 180, 60), width=1,
                                                      style=QtCore.Qt.PenStyle.DashLine))
    for it in (curve, peak_line, mean_line, gate_line):
        plot.addItem(it)
        it.hide()
    plot.setLabel("bottom", "azimuth (deg)")
    plot.setLabel("left", "elevation from boresight (deg)")

    label = pg.LabelItem(justify="left")
    win.addItem(label, row=1, col=0)
    win.ci.layout.setRowStretchFactor(0, 1)   # map takes the window

    timer = QtCore.QTimer()
    timer.timeout.connect(poll)
    timer.start(TICK_MS)

    def handle_sigint(signum, frame):
        print("\nClosing SRP-PHAT viewer...")
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
