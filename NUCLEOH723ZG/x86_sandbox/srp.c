#include "random.h"

#include <limits.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>

/*
*/

#define SPECTRUM_FLOATS 1026
#define SPECTRUM_BINS   (SPECTRUM_FLOATS / 2)
#define NUM_MICS 2
#define NUM_MIC_PAIRS 1
#define PHAT_BETA 0.7f       // proven to yield better results 0.6 - 0.8 
#define PHAT_EPS 1e-12f      // avoids zero-division in gcc_phat
#define SAMPLE_RATE 16000

const float32_t mic_array[NUM_MICS][3] = {
	{ 0.0f, 0.0f, 0.0f },
	{ 1.0f, 1.0f, 0.0f },
};

const float32_t candidate_grid[5] = {
	80.0f, 85.0f, 90.0f, 95.0f, 100.0f
};

typedef struct
{
	float32_t azimuth;
	float32_t power;
	float32_t ratio;
} doa_t;

typedef struct
{
    float real, imag;
} bin_t;

bin_t  WhitenedFreqDomain[SPECTRUM_BINS];

// typedef struct
// {
//     float32_t spectrum[NUM_MICS][SPECTRUM_FLOATS];
// } srp_t;

/// BUFFERS
static float32_t Spectrum[NUM_MICS][SPECTRUM_FLOATS];
static arm_rfft_fast_instance_f32 RfftCfg;
bin_t _TIME_DOMAIN[NUM_MICS][SPECTRUM_BINS];

#define SPECTRUM_FFT_SIZE 1024
static float32_t _PACKED[SPECTRUM_FFT_SIZE];     // 1024 floats: IFFT input (gets destroyed)
static float32_t CorrelationCoefficients[SPECTRUM_FFT_SIZE];         // 1024 floats: IFFT output

bin_t gcc_phat(float* restrict mic_l, float* restrict mic_m)
{
    float real = mic_l[0] * mic_m[0] + mic_l[1] * mic_m[1];
    float imag = mic_l[1] * mic_m[0] - mic_l[0] * mic_m[1];

    float mag_sq  = real * real + imag * imag;
    float denom   = powf(mag_sq, 0.5 * PHAT_BETA) + PHAT_EPS;

    return (bin_t) {
		.real = real / denom,
		.imag = imag / denom
	};
}

// Reduces 4 (2 x 2) -> 2 samples
// aliasing problem if we were to do pointers i guess
bin_t arm_gcc_phat(float* mic_l, float* mic_m)
{
	float32_t real = mic_l[0] * mic_m[0] + mic_l[1] * mic_m[1];
	float32_t imag = mic_l[1] * mic_m[0] - mic_l[0] * mic_m[1];

	float32_t mag_sq = real * real + imag * imag;
    float32_t denom  = powf(mag_sq, 0.5f * PHAT_BETA) + PHAT_EPS; // NOTE: powf is expensive - consider using approximation instead

	return (bin_t) {
		.real = real / denom,
		.imag = imag / denom
	};
}

// WARN:
// Re-packs bins after spectrum did the opposite
// This should be looked at and cleaned up properly
// after spectrum.c handles the problem correctly
void remove_when_spectrum_is_refined()
{
    // correlation_bins[0..512] -> CMSIS packed [DC.re, Nyq.re, b1.re, b1.im, ..., b511.re, b511.im]
    _PACKED[0] = WhitenedFreqDomain[0].real;                  // DC (imag is 0 anyway)
    _PACKED[1] = WhitenedFreqDomain[SPECTRUM_BINS - 1].real;  // Nyquist
    memcpy(&_PACKED[2], &WhitenedFreqDomain[1], (SPECTRUM_BINS - 2) * sizeof(bin_t));
}

void compute_signal_features(float32_t (*spec)[SPECTRUM_FLOATS])
{
	for (int bin_idx = 0; bin_idx < SPECTRUM_BINS; ++bin_idx)
	{
		WhitenedFreqDomain[bin_idx] = arm_gcc_phat(&spec[0][bin_idx * 2], &spec[1][bin_idx * 2]);
	}

    // NOTE: Return to time domain
    remove_when_spectrum_is_refined(); // re-packs bins

	#define INVERSE_FFT 1
	arm_rfft_fast_f32(&RfftCfg, _PACKED, CorrelationCoefficients, INVERSE_FFT);
}

void print_features()
{
	for (int i = 0; i < SPECTRUM_BINS; ++i)
	{
		printf("real: %.2f\timag: %.2f\n", WhitenedFreqDomain[i].real, WhitenedFreqDomain[i].imag);
	}
}

void print_time_domain()
{
	for (int mic = 0; mic < NUM_MIC_PAIRS; ++mic)
	{
		for (int i = 0; i < SPECTRUM_FFT_SIZE; ++i)
		{
            printf("Corrcoeff[%d]: %f\n", i, CorrelationCoefficients[i]);
		}
	}
}

void populate_spectrum(rng_t* seed)
{
    //    TODO: This should run at init for the dsp module
    //   ARM_MATH_SUCCESS                 =  0,        /**< No error */
    //   ARM_MATH_ARGUMENT_ERROR          = -1,        /**< One or more arguments are incorrect */
    //   ARM_MATH_LENGTH_ERROR            = -2,        /**< Length of data buffer is incorrect */
    //   ARM_MATH_SIZE_MISMATCH           = -3,        /**< Size of matrices is not compatible with the operation */
    //   ARM_MATH_NANINF                  = -4,        /**< Not-a-number (NaN) or infinity is generated */
    //   ARM_MATH_SINGULAR                = -5,        /**< Input matrix is singular and cannot be inverted */
    //   ARM_MATH_TEST_FAILURE            = -6,        /**< Test Failed */
    //   ARM_MATH_DECOMPOSITION_FAILURE   = -7         /**< Decomposition Failed */
	if (arm_rfft_fast_init_f32(&RfftCfg, SPECTRUM_FLOATS - 2) < 0)
    {
        printf("_rfft_cfg not initialized\n");
        exit(1);
    }

	for (int mic = 0; mic < NUM_MICS; ++mic)
	{
		for (int sample = 0; sample < SPECTRUM_FLOATS; ++sample)
		{
			Spectrum[mic][sample] = arm_rng_rangef32(seed, (float32_t)1e-4f, (float32_t)20.0f);
		}
	}
}

// doa_t srp_compute(const float32_t (*spectrum)[SPECTRUM_FLOATS], srp_t* srp)
// {
// 	compute_signal_features(spectrum);
//
// 	return (doa_t){ .azimuth=0, .power=0, .ratio=0};
// }

int argmax(float32_t* list, int size)
{
    // Skipping first two as they are DC and Nyquist
    // DC is always the biggest
    int       max_idx_so_far = 0;
    float32_t max_value_so_far = list[2];

    for (int i = 2; i < size; ++i)
    {
        if (list[i] > max_value_so_far)
        {
            max_idx_so_far   = i;
            max_value_so_far = list[i];
        }
    }
    return max_idx_so_far;
}

int main()
{
	rng_t r;
	rng_seed_entropy(&r);

	populate_spectrum(&r);
	float32_t (*spec)[SPECTRUM_FLOATS] = Spectrum;

    compute_signal_features(spec);
    print_time_domain();

    int idxBiggest = argmax(CorrelationCoefficients, SPECTRUM_FFT_SIZE);
    printf("\nLargest value is %f at index: %d\n", CorrelationCoefficients[idxBiggest], idxBiggest);

    return 0;
}

// function x-srp(X, V, d = null)
//     ˆU ←  ∅
//     G ←  create initial candidate grid(d)
//     C ←  compute signal features(X)
//     while G != ∅ do
//         S ←  create srp map(V, G, C)
//         ˆU = grid search(G, S, ˆU)
//         C = update signal features(C, ˆU, V)
//         G = update grid( ˆU, d)
//     end for
//     return ˆU
// end function
