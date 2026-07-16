# Patronus - Teensy Station Firmware

Firmware experimentation for the Patronus passive acoustic UAV detection
station: a Teensy 4.1 driving an ICS-52000 TDM microphone array. The station
will eventually run the performance-critical pipeline validated in
[`../py-simulation/`](../py-simulation/) - TDM ingest → FFT → SRP-PHAT DOA →
log-mel features → streaming to C2 - and produce the on-hardware benchmark
numbers that feed back into the simulator's MCU model
(`py-simulation/docs/mcu.md`, `mcu.calibrations`). Project background:
`../about/Patronus Acoustics Team.pdf`.

## Layout

```
src/
  main.cpp          # development driver: new work is driven here first,
                    # then promoted to lib/; one day the real station entry point
  tests/<name>.cpp  # one self-contained experiment per file (frozen once working)
lib/<Name>/         # app-agnostic building blocks (see rules below)
include/            # shared project headers (currently unused)
platformio.ini      # env "main" + one [env:test-<name>] per test sketch
Makefile            # uv + pio wrapper
```

## Architecture rules

**Sketches compose; libraries provide.** Each sketch owns its state and wires
its own pipeline. With the Teensy Audio library, declaring `AudioConnection`s
*is* the composition mechanism - that wiring always lives in the sketch, never
in a library. We will be composing very different pipelines over time (level
metering, sine detection, FFT benchmarks, SRP-PHAT, beamforming, telemetry),
so nothing app-specific may hide inside `lib/`.

Rules for `lib/<Name>/`:

- **One concern per library.** `LevelMeter` renders meters; `SerialPrompt`
  asks questions. A library that needs "and" in its description is two.
- **Self-contained.** Each library compiles independently and is auto-linked
  into every env by PlatformIO's Library Dependency Finder. It must not
  reference sketch globals.
- **No audio graphs, no app state.** APIs take parameters (`Stream&`, values,
  caller-owned state by reference) and return results. Setup/wiring decisions
  belong to the sketch.
- **Performance-critical code**: prefer CMSIS-DSP primitives for math, avoid
  heap allocation in the steady state, and keep hot paths inlinable
  (header-visible) when it measurably matters.

Planned future modules - create when first needed, never as stubs:

| Module | Concern |
|---|---|
| `AudioCapture` | Audio-graph sink → raw multi-channel sample blocks for custom DSP |
| `Dsp` | FFT / windowing wrappers (CMSIS-DSP) |
| `SrpPhat` | Phase table + steering → az/el |
| `Telemetry` | Framing for host plotting / C2 streaming |

## Workflow

```sh
make build                  # build main app
make build TEST=ics52000    # build a test sketch
make upload TEST=ics52000   # flash it
make monitor                # serial monitor (BAUD=115200 default)
make list                   # list available envs
make compiledb              # refresh compile_commands.json for clangd
```

Adding a test: drop `src/tests/<name>.cpp` + add an `[env:test-<name>]` block
in `platformio.ini`.

Current tests:

- `ics52000` - n-mic ICS-52000 TDM bring-up: interactive mic count, per-mic
  RMS/peak-hold bar meters.
- `ics43434` - single ICS-43434 on I2S, raw RMS/peak printout.
