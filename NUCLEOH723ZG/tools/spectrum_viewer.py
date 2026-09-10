"""Live spectrum viewer for the NUCLEO-H723ZG `fft` app.

The app streams raw float32 frames over USART, one per audio block: `mics`
channels of `bins` complex pairs (Re, Im interleaved), matching
src/config/audio_config.h. There are no framing bytes, so the reader re-syncs
on the one impossible case in the payload: the imaginary parts of DC and
Nyquist are always exactly zero (see _expand_bins in src/dsp/spectrum.c).

Run from the repo root with uv:

    uv run tools/spectrum_viewer.py
"""

import sys

import signal
import numpy as np
import pyqtgraph as pg
import serial
from pyqtgraph.Qt import QtCore

# ---------------------------------------------------------------------------
# Config -- edit these to match the board's flashed audio_config.h and your
# serial device.
# ---------------------------------------------------------------------------
RATE = 48000     # AUDIO_SAMPLE_RATE_HZ
FFT  = 1024      # SPECTRUM_FFT_SIZE
MICS = 2         # AUDIO_MIC_COUNT
PORT = "/dev/ttyACM0"
BAUD = 921600

DB_RANGE = (-60.0, 40.0)
IDLE_TICKS = 100            # 20 ms timer tick -> warn after ~2 s of silence


def frame_start_ok(off):
    """A frame at byte offset off must have zero DC/Nyquist imaginary parts
    on the first and last channels and no NaN/Inf anywhere."""
    if off + frame_bytes > len(buf):
        return False
    f = np.frombuffer(buf, np.float32, fl_frame, off)
    last_ch = (mics - 1) * fl_ch
    return (f[1] == 0.0 and f[fl_ch - 1] == 0.0 and
            f[last_ch + 1] == 0.0 and f[fl_frame - 1] == 0.0 and
            np.all(np.isfinite(f)))


def find_frame_start():
    """Byte offset of the next complete buffered frame, or -1 once drained.
    Sheds stale bytes when no frame start shows up in a while."""
    limit = min(len(buf) - frame_bytes + 1, frame_bytes)
    for off in range(limit):
        if frame_start_ok(off):
            return off
    if len(buf) > 8 * frame_bytes:
        del buf[: 4 * frame_bytes]
    return -1


def show(frame):
    global nframes
    nframes += 1

    dbs = []
    for ch in range(mics):
        re = frame[ch * fl_ch: (ch + 1) * fl_ch: 2]
        im = frame[ch * fl_ch + 1: (ch + 1) * fl_ch: 2]
        dbs.append(10 * np.log10(re * re + im * im + 1e-12))

    for mag, db in zip(mags, dbs):
        mag.setData(freqs, db)

    k = int(np.argmax(dbs[0][1:])) + 1      # peak on mic 0, skipping DC
    pk_line.setValue(freqs[k])

    levels = "  ".join(f"ch{i} {db[k]:.1f} dB" for i, db in enumerate(dbs))
    label.setText(f"frames {nframes} | peak {freqs[k]:.0f} Hz | {levels}")


def poll():
    global buf, idle_ticks
    buf += port.read(port.in_waiting or 1)

    got = 0
    while True:
        off = find_frame_start()
        if off < 0:
            break
        frame = np.frombuffer(buf, np.float32, fl_frame, off).copy()
        del buf[: off + frame_bytes]
        show(frame)
        got += 1

    idle_ticks = idle_ticks + 1 if got == 0 else 0
    if idle_ticks >= IDLE_TICKS:
        label.setText("no frames from the board - check the config globals at the "
                      "top of this file (PORT, BAUD, RATE, FFT, MICS) match audio_config.h")


def main():
    print("="*90)
    print("NB: baud rate (921600) of current USART setup limits this script to run at maximum 1 mic")
    print("="*90)
    global mics, bins, fl_ch, fl_frame, frame_bytes, freqs, nyquist, port, buf
    global idle_ticks, nframes, mags, pk_line, label

    mics = MICS
    bins = FFT // 2 + 1
    fl_ch = 2 * bins
    fl_frame = MICS * fl_ch
    frame_bytes = fl_frame * 4
    freqs = np.arange(bins) * RATE / (2 * (bins - 1))
    nyquist = RATE / 2

    try:
        port = serial.Serial(PORT, BAUD, timeout=0.2)
    except serial.SerialException as e:
        print(f"Could not open {PORT}: {e}")
        print("Check that board is connected and config globals at the top of this file "
              "(PORT, BAUD, RATE, FFT, MICS) match your setup and the flashed audio_config.h.")
        sys.exit(1)

    buf = bytearray()
    idle_ticks = 0

    app = pg.mkQApp()
    win = pg.GraphicsLayoutWidget(title="spectrum")
    win.resize(1000, 700)
    win.show()

    p2 = win.addPlot(row=0, col=0, title="magnitude")
    CHANNEL_PENS = ("y", "b", "c", "m", "g", "w", "orange", "purple")
    mags = [p2.plot(pen=CHANNEL_PENS[ch]) for ch in range(mics)]
    pk_line = pg.InfiniteLine(angle=90, pen=pg.mkPen("r", width=1))
    p2.addItem(pk_line)
    p2.setYRange(*DB_RANGE)
    p2.setLabel("bottom", "Hz")
    p2.setLabel("left", "dB")

    label = pg.LabelItem(justify="left")
    win.addItem(label, row=1, col=0)

    win.ci.layout.setRowStretchFactor(0, 1)   # plot takes the window, label stays short

    nframes = 0

    timer = QtCore.QTimer()
    timer.timeout.connect(poll)
    timer.start(20)

    # Let Ctrl+C (SIGINT) terminate the Qt event loop cleanly.
    def handle_sigint(signum, frame):
        print("\nClosing spectrum viewer...")
        app.quit()

    signal.signal(signal.SIGINT, handle_sigint)

    # Qt's event loop can otherwise prevent Python from processing SIGINT.
    # This timer periodically returns control to Python.
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
