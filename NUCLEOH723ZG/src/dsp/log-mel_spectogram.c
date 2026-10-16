#include "log-mel_spectogram.h"
#include "arm_math.h"
#include "audio_config.h"
#include "mel_fbank.h"

#define EPSILON 1.0e-10f

/*
 * Mel filterbank coefficients, exported from the filterbank used to train
 * the CNN. All filter data lives in mel_fbank.h; regenerate it if the training
 * parameters change.
 */

static float32_t _power_spectrum[SPECTRUM_BINS];

static void get_power_magnitudes(const float32_t (*spec)[SPECTRUM_FLOATS])
{
	for (uint16_t spectrum_index = 0; spectrum_index < SPECTRUM_FLOATS; spectrum_index += 2)
	{
		/* Gather data from mic 0 in spec array, no need to compute data from all mics for log-mel */
		float32_t re = (spec)[0][spectrum_index];
		float32_t im = (spec)[0][spectrum_index + 1];
		uint16_t bin = spectrum_index / 2;
		_power_spectrum[bin] = re * re + im * im;
	}
}

static void apply_logmel(float32_t* mel_out)
{
	const float32_t* w = MEL_WEIGHTS;
	for (uint32_t m = 0; m < NUM_MEL_BANDS; ++m)
	{
		float32_t energy = 0.0f;
		if (MEL_COUNT[m])
			arm_dot_prod_f32(&_power_spectrum[MEL_START[m]], (float32_t*)w, MEL_COUNT[m], &energy);
		w += MEL_COUNT[m];
		mel_out[m] = 10.0f * log10f(energy + EPSILON);
	}
}

void get_logmel_frame(const float32_t (*spec)[SPECTRUM_FLOATS], float32_t* mel_out)
{
	get_power_magnitudes(spec);
	apply_logmel(mel_out);
}
