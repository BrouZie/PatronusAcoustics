# Patronus Acoustics

Passive acoustic UAV detection. Microphone-array stations listen for drones,
estimate a bearing, and stream features to a C2 system that classifies and
locates the target.

## Intended structure for final version

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
| Microphone | Passive sensor used to calculate DOA, and classification using a NN on microphone data |
| Microcontroller | All local calculations happens on the MCU (Data processing, SRP-PHAT) |
| GPS | For station positions and timing when incorperating multiple stations |

#### [Hardware prototype 1](docs/hardware.md)

## Software

Main software pipeline


| Step | Description |
|------|-------------|
| **Read data** | Read raw sensor data from microphone, and GPS module. |
| **Data processing** | Process data with FFT(Fast Fourier Transform) |
| **Classification** | Transform data to format best suited for machine learning |
| **Localization** | Implement algorithm for calculating DOA of sound |
| **Transfer** | Transfer processed data to external computer | 
| **Machine learning** | Use machine learning to classify sound | 
| **Triangulating** | Combine localization and gps data to triangulate pos| 


#### [Software prototype 1](docs/software.md)

## Status (Prototype 1)

We are currently at **single-station bring-up**:

- **Mics:** Up to 5 physically on hand.
- **Array:** Simple 1D array with five mic slots - concentric UCA ring
- **GNSS:** No GPS module yet, so no PPS and no cross-station time sync.
- **Classification:** Log-mel format working end to end - TDM capture → FFT → log-mel frames.
- **Localization:** SRP-PHAT is algorithm of choice, first implementation is almost finalized.
- **Transfer:** No Ethernet/C2 setup yet. Frames go out over USART to host.
- **Machine learning** CNN pipeline from [kbhujbal](https://github.com/kbhujbal/SudarshanChakra-acoustic_uav_threat_detec)
- **Triangulating** No triangulating since we only have one station.
