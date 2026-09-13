# Patronus Acoustics

Passive acoustic UAV detection. Microphone-array stations listen for drones,
estimate a bearing, and stream features to a C2 system that classifies and
locates the target.

## How it works

A station is two concentric UCA microphone rings (with different diameters)
separated along the boresight axis. The rings give azimuth directionality; the
axial offset breaks front/back mirror symmetry. Ring diameters target low
frequencies - they travel farther.

Per station:

```
ICS-52000 TDM array -> STM32 (SAI) -> FFT -> SRP-PHAT -> az/el bearing -> C2
                                          -> log-mel  -> 2D sound image -> C2
```

C2 runs CNN classification on the log-mel stream - providing the ability to
classify type of drone. One station yields a bearing only; two stations gives
a 3D estimate by triangulating station bearings.

## Hardware

| Part | Why |
|---|---|
| ICS-52000 on custom breakout | Built for arrays: shared clock/data over TDM, 65 dB SNR, PCM out (no PDM filtering cost). Custom PCB keeps array geometry flexible. |
| NUCLEO-H723ZG | SAI with 16-slot TDM, onboard Ethernet, cheap, proven for this workload. |
| GPS (u-blox NEO-7M GNSS?) | PPS output for sub-ms cross-station sync, no custom PCB needed. |

> Hardware specifications are not finalized and may change over time

## Layout

```
NUCLEOH723ZG/   Current station firmware (STM32H723, CMake + CMSIS-DSP)
teensy/         Superseded Teensy 4.1 prototype. Never got far; kept only as reference.
py-simulation/  See below.
about/          Project presentation and notes
```

`py-simulation/` is purely vibe-coded throwaway code used to test the waters of the
project before the MCU, mics and other parts arrived. It was used to explore
array configurations and how far away a drone frequency can be picked up (inside
the simulation), however its results should not be considered valid or reliable.
It is not part of the system.

## Status

We are currently at **single-station bring-up**:

- **Mics:** up to 5 physically on hand; the SAI TDM path is built for 8 slots.
  Mic count is a build-time knob (`-DAUDIO_MIC_COUNT=...`).
- **Log-mel:** working end to end - TDM capture → FFT → log-mel frames.
- **SRP-PHAT:** first implementation is almost finalized.
- **Transport:** no Ethernet/C2 setup yet. Frames go out over USART to host
  viewers in `NUCLEOH723ZG/tools/`.
- **GNSS:** no GPS module yet, so no PPS and no cross-station time sync.
- **Array:** Simple 1D array with four mic slots - concentric UCA ring is yet to
  be made

The design is not set in stone and will evolve.
