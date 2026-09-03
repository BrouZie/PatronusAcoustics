#include "log-mel_spectogram.h"

#include <stdint.h>

#define NUM_MEL_BANDS        64U
#define MIN_FREQUENCY        100
#define MAX_FREQUENCY        6000
#define EPSILON              1.0e-6f
#define MEL_WEIGHT_POOL_SIZE 384U   /* Size to sum(num_bins) across all bands */

typedef struct {
    uint16_t   start_bin;
    uint16_t   num_bins;
    float32_t* weights_addr; // Pointer to where weights data start
} mel_filter_t;

static mel_filter_t _mel_filters[NUM_MEL_BANDS];
static float32_t    _mel_weight_pool[MEL_WEIGHT_POOL_SIZE]; // Store all Mel weights contiguously to avoid per-filter padding
static float32_t    _power_spectrum[SPECTRUM_BINS];
static float32_t    _logmel_output[NUM_MEL_BANDS];

void get_magnitudes(float32_t (**spec)[SPECTRUM_FLOATS])
{
	for (uint16_t index = 0; index < SPECTRUM_BINS; ++index)
	{
		float32_t re = (**spec)[index];
		float32_t im = (**spec)[index + 1];
		_power_spectrum[index] = re * re + im * im;
	}
}

static float32_t hz_to_mel(float32_t freq)
{
	return 2595 * log10f(1 + freq/700.0f);
}

static float32_t mel_to_hz(float32_t mel)
{
	return 700.0f * (powf(10.0f, (float32_t)mel / 2595.0f) - 1.0f);
}

void mel_filterbank_init(void)
{
	float32_t min_mel = hz_to_mel(MIN_FREQUENCY);
	float32_t max_mel = hz_to_mel(MAX_FREQUENCY);
	float32_t mel_step_size = (max_mel - min_mel) / (float32_t)(NUM_MEL_BANDS + 1U);
	float32_t bin_spacing = (float32_t)AUDIO_SAMPLE_RATE_HZ / (float32_t)FFT_BUFFER_SIZE;

	float32_t hz_points[NUM_MEL_BANDS + 2U];
	uint16_t bin_points[NUM_MEL_BANDS + 2U];

	for (uint8_t i = 0; i < NUM_MEL_BANDS + 2U; ++i)
	{
		hz_points[i] = mel_to_hz(min_mel + (float32_t)i * mel_step_size);
		/* Floor not round maps each point to bin at/just below, 
		 * so that shared edges between adjecent filters stay aligned */
		bin_points[i] = (uint16_t)floorf(hz_points[i] / bin_spacing); 
	}

	float32_t* pool_ptr = _mel_weight_pool;
	
	for (uint32_t mel_band_idx = 0; mel_band_idx < NUM_MEL_BANDS; ++mel_band_idx)
	{
		uint16_t bin_left = bin_points[mel_band_idx];
		uint16_t bin_center = bin_points[mel_band_idx + 1U];
		uint16_t bin_right = bin_points[mel_band_idx + 2U];

		if (bin_center <= bin_left)   { bin_center = bin_left + 1U; }
		if (bin_right  <= bin_center) { bin_right  = bin_center + 1U; }

		/* Number of fft bins touched by the triangular filter */
		uint16_t num_bins = bin_right - bin_left + 1U;

		mel_filter_t* filter = &_mel_filters[mel_band_idx];
		filter->start_bin    = bin_left;
		filter->num_bins     = num_bins;
		filter->weights_addr = pool_ptr;
		pool_ptr += num_bins; // Move pointer to address of next filter 

		/* Calculate weight for bins */
        for (uint16_t fft_index = 0; fft_index < num_bins; ++fft_index)
        {
            uint16_t bin = bin_left + fft_index;
            float32_t weight;

			/* Linearly ramp this bin's weight: 0 at the filter's outer edges, 1 at its
			 * center — rising edge (bin_left -> bin_center), falling edge (bin_center -> bin_right) */
            if (bin <= bin_center)
            {
                weight = (bin_center > bin_left)
                    ? (float32_t)(bin - bin_left) / (float32_t)(bin_center - bin_left)
                    : 1.0f;
            }
            else
            {
                weight = (bin_right > bin_center)
                    ? (float32_t)(bin_right - bin) / (float32_t)(bin_right - bin_center)
                    : 1.0f;
            }
            filter->weights_addr[fft_index] = weight;
        }
	}
}

static void apply_logmel(const float32_t* power_spec, float32_t* mel_out)
{
	for (uint32_t mel_idx = 0; mel_idx < NUM_MEL_BANDS; ++mel_idx)
	{
		mel_filter_t* filter = &_mel_filters[mel_idx];
		/* Compute mel-band energy as the weighted sum of the power spectrum. */
		arm_dot_prod_f32(&power_spec[filter->start_bin], filter->weights_addr, filter->num_bins, &mel_out[mel_idx]);
		/* Convert mel-band energy to log10 scale; EPSILON prevents log10(0). */
		mel_out[mel_idx] = log10f(mel_out[mel_idx] + EPSILON);
	}
}
