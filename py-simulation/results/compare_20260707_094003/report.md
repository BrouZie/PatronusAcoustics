# Geometry Comparison Report

Generated: 2026-07-07T09:51:37
Distances: 10, 20, 30, 50, 70 m · 3 seed(s) per point · full mode (full-sphere search)

SNR at each distance follows from the EIN budget (drone SPL − spreading − absorption − mic noise floor); the drone is stationary at the configured bearing.

| Geometry | Mics | Range@90% | Range@50% | Err@30 m | Mirror supp. | MCU (H753) |
|---|---|---|---|---|---|---|
| dual_ring_s05 | 16 | 10.0 m | 14.5 m | 16.0° | 1.4 dB | 77.67 MB / 22.0 ms per 10.7 ms frame [MEMORY] |
| dual_ring_s20 | 16 | — | 14.5 m | 16.1° | 1.0 dB | 77.67 MB / 22.0 ms per 10.7 ms frame [MEMORY] |
| dual_ring_s30 | 16 | 10.0 m | 14.5 m | 16.2° | 1.2 dB | 77.67 MB / 22.0 ms per 10.7 ms frame [MEMORY] |
| single_ring_16 | 16 | — | — | 85.2° | -0.0 dB | 77.67 MB / 22.0 ms per 10.7 ms frame [MEMORY] |

Range@X% = interpolated distance where detection rate crosses X%; '—' means the curve never crossed inside the tested distances. MCU column: phase-table memory and est. frame compute vs the frame period for the *station's own* search grid (not the research full-sphere grid used for the curves above).

## MCU feasibility

Per-stage requirements (SRP-PHAT + log-mel cost model + uplink) for the station's own search grid, matched against each target profile. A verdict fails if compute, SRAM, flash, **or** mic TDM ingest (SAI/I2S buses × slots × bit clock) does not fit — an MCU that cannot physically connect the mics is never recommended. See docs/mcu.md for formulas and profile provenance.

### dual_ring_s05 (16 mics)

Required: 1286 MHz (at 1 MAC/cycle, 30% headroom) · 78.00 MB RAM · 17 KB flash · 57.6 kbps uplink

| Stage | RAM | Flash | MMACs/s |
|---|---|---|---|
| srp_phat | 77.999 MB | 8.0 KB | 988.7 |
| log_mel | 0.000 MB | 8.5 KB | 0.3 |
| transmit | 0.000 MB | 0.0 KB | 0.0 |

| Target | Verdict |
|---|---|
| stm32h753 | fails: compute 1286 MHz > 480 MHz; SRAM 78.00 MB > 840 KB; flash OK (17 KB ≤ 2.00 MB); audio OK (2 buses ≤ 8 (8 mics/bus)) |

**Recommended:** none of the configured targets

### dual_ring_s20 (16 mics)

Required: 1286 MHz (at 1 MAC/cycle, 30% headroom) · 78.00 MB RAM · 17 KB flash · 57.6 kbps uplink

| Stage | RAM | Flash | MMACs/s |
|---|---|---|---|
| srp_phat | 77.999 MB | 8.0 KB | 988.7 |
| log_mel | 0.000 MB | 8.5 KB | 0.3 |
| transmit | 0.000 MB | 0.0 KB | 0.0 |

| Target | Verdict |
|---|---|
| stm32h753 | fails: compute 1286 MHz > 480 MHz; SRAM 78.00 MB > 840 KB; flash OK (17 KB ≤ 2.00 MB); audio OK (2 buses ≤ 8 (8 mics/bus)) |

**Recommended:** none of the configured targets

### dual_ring_s30 (16 mics)

Required: 1286 MHz (at 1 MAC/cycle, 30% headroom) · 78.00 MB RAM · 17 KB flash · 57.6 kbps uplink

| Stage | RAM | Flash | MMACs/s |
|---|---|---|---|
| srp_phat | 77.999 MB | 8.0 KB | 988.7 |
| log_mel | 0.000 MB | 8.5 KB | 0.3 |
| transmit | 0.000 MB | 0.0 KB | 0.0 |

| Target | Verdict |
|---|---|
| stm32h753 | fails: compute 1286 MHz > 480 MHz; SRAM 78.00 MB > 840 KB; flash OK (17 KB ≤ 2.00 MB); audio OK (2 buses ≤ 8 (8 mics/bus)) |

**Recommended:** none of the configured targets

### single_ring_16 (16 mics)

Required: 1286 MHz (at 1 MAC/cycle, 30% headroom) · 78.00 MB RAM · 17 KB flash · 57.6 kbps uplink

| Stage | RAM | Flash | MMACs/s |
|---|---|---|---|
| srp_phat | 77.999 MB | 8.0 KB | 988.7 |
| log_mel | 0.000 MB | 8.5 KB | 0.3 |
| transmit | 0.000 MB | 0.0 KB | 0.0 |

| Target | Verdict |
|---|---|
| stm32h753 | fails: compute 1286 MHz > 480 MHz; SRAM 78.00 MB > 840 KB; flash OK (17 KB ≤ 2.00 MB); audio OK (2 buses ≤ 8 (8 mics/bus)) |

**Recommended:** none of the configured targets

![Detection rate](detection_rate_vs_range.png)
![Angular error](angular_error_vs_range.png)
![Mirror suppression](mirror_suppression_vs_range.png)
![Beampattern cuts](beampattern_cuts.png)
![Geometries](geometries.png)
