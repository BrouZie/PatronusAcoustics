#ifndef SRPPHAT_H
#define SRPPHAT_H

#include "array_geometry.h"
#include "audio_config.h"
#include "spectrum.h"

#include <stdbool.h>

/*
 * SRP-PHAT bearing estimation.
 *
 * Steered Response Power with PHase Transform: steer the array at every
 * direction on a grid, and report where the phase-aligned sum of the
 * microphone spectra is loudest.
 *
 *     P(az, el) = SUM  | SUM  Xhat_m[k] * e^(+j 2pi k tau_m / N) |^2
 *                  k      m
 *
 * Xhat is the PHAT-whitened spectrum -- each bin divided by its own magnitude,
 * so only phase survives. That is what makes the estimate robust to a loud
 * broadband source: it weights every frequency by how CONSISTENT it is across
 * mics, not by how strong it is.
 *
 * tau_m is the steering delay of mic m, in samples, for a plane wave arriving
 * from direction u:
 *
 *     tau_m = -(p_m . u) / c * fs
 *
 * Conventions match py-simulation/src/{srpphat,geometry}.py exactly, so the
 * board and the simulator can be compared directly:
 *
 *   azimuth   -- rotation in the array plane, from +x toward +y.
 *   ELEVATION -- POLAR ANGLE FROM BORESIGHT (+z). 0 deg is straight ahead,
 *                90 deg is in the plane of the ring. This is NOT elevation
 *                above the horizon.
 *
 * Microphone positions come from src/config/array_geometry.h.
 *
 * At AUDIO_MIC_COUNT == 1 everything below still runs and produces a flat map:
 * a single microphone carries no direction information. Two mics resolve only
 * a cone; three non-collinear mics are the minimum for a unique bearing.
 */

/* --------- SEARCH GRID AND BAND --------- */

/* Both come from src/config/array_geometry.h, alongside the microphone
 * positions, because both follow from the layout: an array resolves only as
 * many angles as its aperture spans dimensions, and it aliases above
 * c / (2 * smallest spacing). Editing the geometry there updates all three
 * together, which is what stops them drifting apart. */

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

/* Exponential time constant of the map, in frames.
 *
 * A single 1024-point frame is 21 ms of audio, and one frame of SRP-PHAT is a
 * NOISY estimate -- the peak hops between neighbouring cells from frame to
 * frame even with a stationary source. Averaging the map before picking the
 * peak is what turns it into a bearing you can read.
 *
 * 8 frames is ~85 ms of memory: fast enough to follow a moving drone, slow
 * enough to stop the peak twitching. Set to 1 to disable and see raw frames. */
#define SRP_AVERAGE_FRAMES 8U

/* Detection needs TWO gates, because neither one alone answers the question.
 *
 * COHERENCE -- do the microphones agree about a direction? PHAT pins the map's
 * absolute scale: aligned mics peak at M^2 * bins, mics hearing an incoherent
 * field sit at M * bins, so (peak/bins - M) / (M^2 - M) runs 0 to 1 regardless
 * of grid or microphone count.
 *
 * Its floor is NOT zero. A reverberant room is a diffuse field, and two omnis
 * d apart in one are correlated by sinc(2*pi*f*d/c) with nothing there at all
 * -- 0.51 averaged over 300-1700 Hz at 10 cm spacing, and peaking at zero
 * delay, i.e. broadside. An empty room therefore reads about half coherent and
 * points at broadside, and any fixed threshold below that can never fail. So
 * the floor is computed from the geometry and band actually built, at init,
 * and the gate sits a margin above it.
 *
 * LEVEL -- is there anything worth pointing at? This cannot come from the SRP
 * map: PHAT divides every bin by its own magnitude, so downstream of it a
 * whisper and a jet engine are identical. Level is measured on the spectrum
 * BEFORE whitening, and is true dBFS with 0 dB a full-scale sine.
 *
 * Of the two, level is the sharper discriminator on a small array: a quiet
 * room and a phone playing a drone differ by ~20 dB of level but only ~0.2 of
 * coherence. Calibrate SRP_DETECT_LEVEL_DB by watching level_db in a quiet
 * room and setting it a few dB above what you see. */
#define SRP_DETECT_MARGIN   0.15f
#define SRP_DETECT_LEVEL_DB (-70.0f)

/* --------- INVARIANTS --------- */

_Static_assert(SRP_K_MIN >= 1U, "SRP band must start above DC");
_Static_assert(SRP_K_MAX <= SPECTRUM_BINS - 1U, "SRP band runs past Nyquist");
_Static_assert(SRP_K_MIN < SRP_K_MAX, "SRP band is empty -- check SRP_MIN/MAX_FREQ_HZ against the FFT size");

/* --------- PUBLIC API --------- */

typedef struct
{
    float32_t azimuth_deg;
    float32_t elevation_deg; // polar from boresight -- see the note above
    float32_t peak_power;    // the map's maximum, arbitrary units
    float32_t coherence;       // 0 = incoherent, 1 = perfect agreement about a direction
    float32_t coherence_floor; // what a diffuse field alone yields for this geometry
    float32_t level_db;        // in-band level of mic 0, true dBFS, before whitening
    bool      detected;        // both gates passed -- see SRP_DETECT_MARGIN / _LEVEL_DB
} srp_doa_t;

void srp_phat_init(void);

/* One frame in, one SRP map out.
 *
 * spec     -- as handed back by spectrum_compute(), all AUDIO_MIC_COUNT rows.
 * map_out  -- SRP_DIRECTIONS floats supplied by the CALLER, azimuth-major:
 *             map_out[az_index * SRP_EL_STEPS + el_index]. Caller-owned so an
 *             app can point it straight into a transmit buffer and skip a copy.
 * doa      -- peak of that map, decoded back to angles. May not be NULL.
 */
void srp_phat_compute(const float32_t (*spec)[SPECTRUM_FLOATS], float32_t* map_out, srp_doa_t* doa);

#endif
