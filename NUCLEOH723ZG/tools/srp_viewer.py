"""Live SRP-PHAT map viewer for the NUCLEO-H723ZG `srp-phat` app.

The board sends one packet per audio hop (srp_packet_t in
src/apps/srp-phat/app_main.c): a 64-byte header, then the SRP map as float32,
azimuth major. The grid comes from the header, so PORT and BAUD are the only
local settings.

    uv run tools/srp_viewer.py
"""

import signal
import struct
import sys

import numpy as np
import pyqtgraph as pg
import serial
from pyqtgraph.Qt import QtCore

PORT = "/dev/ttyACM0"
BAUD = 921600

MAGIC = b"SRPP"
# magic, seq, az0, az_step, el0, el_step, az_steps, el_steps,
# peak az, el, power, ratio, 20 reserved bytes
HEADER = struct.Struct("<4sI4f2H4f20x")
MAX_CELLS = 4096            # anything larger is a false magic match


def next_packet(buf):
    """Pops the next complete packet off buf -> (header fields, map), or None."""
    while True:
        start = buf.find(MAGIC)
        if start < 0:
            del buf[:-3]    # keep the tail, a magic may be split across reads
            return None
        del buf[:start]
        if len(buf) < HEADER.size:
            return None

        hdr = HEADER.unpack_from(buf)
        cells = hdr[6] * hdr[7]
        if not 0 < cells <= MAX_CELLS:
            del buf[:4]     # not a real header, look for the next magic
            continue

        size = HEADER.size + 4 * cells
        if len(buf) < size:
            return None
        srp_map = np.frombuffer(bytes(buf[HEADER.size:size]), np.float32)
        del buf[:size]
        return hdr, srp_map


def show(hdr, srp_map):
    _, seq, az0, az_step, _, _, az_steps, el_steps, az, el, power, _ = hdr

    # azimuth major: one row per azimuth. With several elevations, plot the best one.
    per_az = srp_map.reshape(az_steps, el_steps).max(axis=1)
    az_axis = az0 + az_step * np.arange(az_steps)

    curve.setData(az_axis, per_az)
    peak_line.setValue(az)
    label.setText(f"seq {seq} | dropped {dropped} | board az {az:.1f} el {el:.1f} power {power:.3f} | "
                  f"map argmax az {az_axis[int(np.argmax(per_az))]:.1f}")


def poll():
    global last_seq, dropped
    buf.extend(port.read(port.in_waiting or 1))

    latest = None
    while (packet := next_packet(buf)) is not None:
        seq = packet[0][1]
        if last_seq is not None and seq != last_seq + 1:
            dropped += 1
        last_seq = seq
        latest = packet

    if latest is not None:
        show(*latest)


def main():
    global port, buf, last_seq, dropped, curve, peak_line, label

    try:
        port = serial.Serial(PORT, BAUD, timeout=0.02)
    except serial.SerialException as e:
        print(f"Could not open {PORT}: {e}")
        sys.exit(1)

    buf = bytearray()
    last_seq = None
    dropped = 0

    app = pg.mkQApp()
    win = pg.GraphicsLayoutWidget(title="srp-phat")
    win.resize(1000, 600)
    win.show()

    plot = win.addPlot(row=0, col=0, title="SRP map")
    plot.setLabel("bottom", "azimuth (deg)")
    plot.setLabel("left", "power")
    curve = plot.plot(pen="y")
    peak_line = pg.InfiniteLine(angle=90, pen=pg.mkPen("r", width=1))
    plot.addItem(peak_line)

    label = pg.LabelItem(justify="left")
    label.setText("waiting for packets...")
    win.addItem(label, row=1, col=0)
    win.ci.layout.setRowStretchFactor(0, 1)

    timer = QtCore.QTimer()
    timer.timeout.connect(poll)
    timer.start(20)

    # Ctrl+C closes the window; the timer above keeps Python responsive to it
    signal.signal(signal.SIGINT, lambda *_: app.quit())

    try:
        app.exec()
    finally:
        port.close()


if __name__ == "__main__":
    main()
