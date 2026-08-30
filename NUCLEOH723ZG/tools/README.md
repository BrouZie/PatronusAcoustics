# Host-side tools

Small scripts that run on the host PC and talk to the board (or otherwise help
with NUCLEO-H723ZG development). Python dependencies live in the repo-root
`pyproject.toml`, so `uv` resolves them automatically.

## Run

From the repo root:

    uv run tools/spectrum_viewer.py

The first run creates a `.venv` and installs the dependencies; afterwards it's
incremental. Without `uv`, install `numpy`, `PyQt6`, `pyqtgraph`, and
`pyserial` by hand and run `python tools/spectrum_viewer.py`.

## spectrum_viewer.py

Live spectrum display for the `fft` app: a per-channel magnitude plot with the
peak bin and the per-channel levels at that bin shown in the status line. The
board's DFT frames arrive raw over USART; the reader re-syncs mid-stream on
the frame structure (zero DC/Nyquist imaginary parts).

The `RATE`, `FFT`, `MICS`, `PORT`, and `BAUD` globals at the top of the file
must match the board's flashed config (`src/config/audio_config.h`) and your
serial device. If the serial port can't be opened, the script prints what's
wrong and exits; if it opens but no usable frames arrive, the status line says
so. Both messages point back at those globals.

## Adding a tool

Drop a new script in this directory and keep its wire-format constants
pointing back at `src/config/audio_config.h` so the two can't silently drift
apart.