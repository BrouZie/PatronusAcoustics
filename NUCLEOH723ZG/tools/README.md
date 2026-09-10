# Host-side tools

Small scripts that run on the host PC and talk to the board (or otherwise help
with NUCLEO-H723ZG development). Python dependencies live in the repo-root
`pyproject.toml`, so `uv` resolves them automatically.

## Run

From the repo root:

    uv run tools/spectrum_viewer.py
    uv run tools/logmel_viewer.py
    uv run tools/srp_viewer.py

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

## logmel_viewer.py

Live log-mel spectrogram display for the `log-mel` app: a scrolling picture of
the images the detector will eventually consume, mel band on the vertical axis
labelled in Hz.

Play a 1 kHz tone and the ridge should land on the band labelled 984 Hz; sweep
200 Hz -> 5 kHz and it should trace a smooth curve rising left to right; cover
the mic and the picture should collapse to a flat floor.

Unlike the spectrum viewer, this one needs no constants kept in step with the
firmware. The board sends a 32-byte header (`src/types/logmel_packet.h`) ahead
of every image carrying the geometry, sample rate, hop, filterbank edges and
quantiser constants, so the script syncs on the header's magic word and
configures its own axes and scaling from the stream. Only `PORT` and `BAUD` are
local settings. An image counter in the header means a dropped image is
reported rather than silently smoothed over.

The board produces one image per second and ships it in a ~66 ms burst.
Painting each image the moment it lands would make the display lurch once a
second and look frozen in between, so columns are queued and drawn at the rate
the audio was captured. The picture scrolls smoothly, one image behind the
board; `SECONDS_SHOWN` sets how much history is visible. `AUTO_LEVELS` tracks
the signal's own range, which matters because the absolute log-mel level moves
with microphone gain -- set it False and edit `LEVELS` to pin the colour scale
instead.

Five pairs of low bands render as identical rows. That is the firmware, not the
display: the mel spacing is finer than the FFT resolves down there, so the
clamps in `src/dsp/log-mel_spectogram.c` collapse those pairs onto identical
filters, and five of 64 bands carry nothing the band below does not.

## srp_viewer.py

Live SRP-PHAT map for the `srp-phat` app. The board sends a 64-byte header
(`src/types/srp_packet.h`) and then the map, so the script configures its own
axes and thresholds from the stream; only `PORT` and `BAUD` are local settings.

When the firmware searches a single elevation row -- which is all a microphone
pair can use -- the viewer draws a curve instead of a heatmap: power against
the swept angle, peak in red, with the detection gate as a dashed line so a
missed detection is visible rather than inferred.

Elevation is the polar angle from boresight: 0 deg straight ahead, 90 deg in
the plane of the array.

### Reading it with two microphones

A pair measures one thing: the angle between the source and the line through
the two microphones. The grid in `src/config/array_geometry.h` is set to match,
so azimuth carries that angle (0 and 180 endfire, 90 broadside) and elevation
stays pinned at 90.

- **Use a broadband source.** A pure tone gives a confident, repeatable, wrong
  bearing -- delay is read from the slope of cross-phase against frequency, and
  one frequency has no slope. Pink noise, a sustained "shhh", keys or crumpling
  paper all work; a 1500 Hz tone measured 1.4 deg for a source truly at 40.
- **Stay off the microphone axis.** Sensitivity is `0.24 * sin(angle)` samples
  per degree, so broadside resolves about 12x better than endfire. Between 40
  and 90 deg off the axis the error is 1-2 deg; below 30 deg the geometry
  cannot resolve it at all.
- **Distance barely matters.** The plane-wave model is off 1.6 deg at 15 cm and
  0.1 deg at 50 cm.
- **If nothing detects**, check the band first: flash the `fft` app and run
  `spectrum_viewer.py`. Laptop and phone speakers roll off below ~400 Hz, which
  is where a drone recording keeps its energy, so playback can leave almost
  nothing in the 300-1700 Hz band however loud it sounds.

The status line names which gate failed. `coherence` (0-1) says whether the
microphones agree about a direction; `level` (dBFS, in-band) says whether there
was anything worth pointing at. Both must pass. `SRP_DETECT_LEVEL_DB` in
`src/dsp/srp-phat.h` is the one number that needs calibrating to your gain --
watch the level in a quiet room and set it a few dB above that.

The board sizes its own streaming rate to about 60% of the link: a 37x1 sweep
goes out every frame, the full 72x19 grid every tenth. `BUILD=Debug` compiles
-O0 and can make the DSP miss frames; use `BUILD=Release`.

## Adding a tool

Drop a new script in this directory and keep its wire-format constants
pointing back at `src/config/audio_config.h` so the two can't silently drift
apart.