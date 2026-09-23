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

typedef struct
{
	float32_t azimuth;
	float32_t power;
	float32_t ratio;
} doa_t;

typedef struct
{
	
} srp_t;

doa_t srp_compute(const float32_t (*spectrum)[SPECTRUM_FLOATS], srp_t* srp);

#endif
