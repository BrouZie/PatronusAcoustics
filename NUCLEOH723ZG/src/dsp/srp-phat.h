#ifndef SRPPHAT_H
#define SRPPHAT_H

#include "array_geometry.h"
#include "audio_config.h"
#include "spectrum.h"

#include <stdbool.h>

/*
 * SRP-PHAT bearing estimation.
 *
 * Steer the array at every direction on a grid and report where the
 * phase-aligned sum of the microphone spectra is loudest:
 *
 *     P(az, el) = SUM  | SUM  Xhat_m[k] * e^(+j 2pi k tau_m / N) |^2
 *                  k      m
 *
 * Xhat is the PHAT-whitened spectrum -- every bin divided by its own magnitude,
 * so only phase survives and the peak is decided by agreement across mics
 * rather than by loudness. tau_m is mic m's steering delay in samples, for a
 * plane wave from direction u:  tau_m = -(p_m . u) / c * fs.
 *
 * Conventions match py-simulation/src/{srpphat,geometry}.py so the board and
 * the simulator are directly comparable:
 *
 *   azimuth   -- rotation in the array plane, from +x toward +y.
 *   ELEVATION -- POLAR ANGLE FROM BORESIGHT (+z). 0 deg is straight ahead,
 *                90 deg is in the array plane. NOT elevation above horizon.
 *
 * An array resolves as many angles as its aperture spans dimensions: one
 * microphone resolves none, a pair resolves only a cone about its own axis,
 * and three non-collinear mics are the minimum for a unique bearing.
 */

/* --------- SEARCH GRID AND BAND --------- */

/* Grid and band come from src/config/array_geometry.h, next to the microphone
 * positions, because both follow from the layout: an array resolves as many
 * angles as its aperture spans dimensions, and it aliases above
 * c / (2 * smallest spacing). */

#define SRP_AZ_START_DEG ARRAY_SEARCH_AZ_START_DEG
#define SRP_AZ_STEP_DEG  ARRAY_SEARCH_AZ_STEP_DEG
#define SRP_AZ_STEPS     ARRAY_SEARCH_AZ_STEPS

#define SRP_EL_START_DEG ARRAY_SEARCH_EL_START_DEG
#define SRP_EL_STEP_DEG  ARRAY_SEARCH_EL_STEP_DEG
#define SRP_EL_STEPS     ARRAY_SEARCH_EL_STEPS

#define SRP_DIRECTIONS (SRP_AZ_STEPS * SRP_EL_STEPS)

#define SRP_MIN_FREQ_HZ ARRAY_BAND_MIN_HZ
#define SRP_MAX_FREQ_HZ ARRAY_BAND_MAX_HZ

// Bin index of a frequency is f * N / fs. Round the band inward on both ends.
#define SRP_K_MIN     ((SRP_MIN_FREQ_HZ * SPECTRUM_FFT_SIZE + AUDIO_SAMPLE_RATE_HZ - 1U) / AUDIO_SAMPLE_RATE_HZ)
#define SRP_K_MAX     ((SRP_MAX_FREQ_HZ * SPECTRUM_FFT_SIZE) / AUDIO_SAMPLE_RATE_HZ)
#define SRP_BAND_BINS (SRP_K_MAX - SRP_K_MIN + 1U)

/* --------- CONSTANTS --------- */

#define SRP_SPEED_OF_SOUND 343.0f // m/s, matches py-simulation SPEED_OF_SOUND_REF

/* Exponential time constant of the map, in frames. One frame of SRP-PHAT is a
 * noisy estimate whose peak hops between neighbouring cells even for a
 * stationary source; averaging before picking the peak is what turns it into a
 * readable bearing. 8 frames is ~85 ms. Set to 1 to see raw frames. */
#define SRP_AVERAGE_FRAMES 8U

/* Detection takes two gates, because neither alone answers the question.
 *
 * COHERENCE -- do the microphones agree about a direction? PHAT pins the map's
 * scale: aligned mics peak at M^2 * bins, an incoherent field sits at M * bins,
 * so (peak/bins - M) / (M^2 - M) runs 0 to 1 for any grid or mic count. Its
 * floor is NOT zero: a reverberant room is a diffuse field, in which two omnis
 * d apart correlate as sinc(2*pi*f*d/c) with nothing present -- 0.51 over
 * 300-1700 Hz at 10 cm, peaking at zero delay, i.e. broadside. The floor is
 * therefore computed from the built geometry at init and the gate sits
 * SRP_DETECT_MARGIN above it.
 *
 * LEVEL -- is there anything worth pointing at? This cannot come from the map,
 * since PHAT has already discarded amplitude. It is measured on the spectrum
 * before whitening, in true dBFS (0 dB = full-scale sine), and on a small array
 * it is the sharper of the two. Calibrate it by watching level_db in a quiet
 * room and setting this a few dB above. */
#define SRP_DETECT_MARGIN   0.15f
#define SRP_DETECT_LEVEL_DB (-70.0f)

/* --------- INVARIANTS --------- */

_Static_assert(SRP_K_MIN >= 1U && SRP_K_MAX <= SPECTRUM_BINS - 1U, "SRP band must lie strictly between DC and Nyquist");
_Static_assert(SRP_K_MIN < SRP_K_MAX, "SRP band is empty -- check ARRAY_BAND_* against the FFT size");

/* --------- PUBLIC API --------- */

typedef struct
{
    float32_t azimuth_deg;
    float32_t elevation_deg;   // polar from boresight -- see the note above
    float32_t coherence;       // 0 = incoherent, 1 = perfect agreement on a direction
    float32_t coherence_floor; // what a diffuse field alone yields for this geometry
    float32_t level_db;        // in-band level of mic 0, true dBFS, before whitening
    bool      detected;        // both gates passed
} srp_doa_t;

void srp_phat_init(void);

/* One frame in, one SRP map out.
 *
 * spec    -- as handed back by spectrum_compute(), all AUDIO_MIC_COUNT rows.
 * map_out -- SRP_DIRECTIONS floats owned by the CALLER, azimuth-major:
 *            map_out[az_index * SRP_EL_STEPS + el_index]. Caller-owned so an
 *            app can point it into a transmit buffer and skip a copy.
 * doa     -- peak of that map, decoded back to angles. May not be NULL.
 */
void srp_phat_compute(const float32_t (*spec)[SPECTRUM_FLOATS], float32_t* map_out, srp_doa_t* doa);

#endif
