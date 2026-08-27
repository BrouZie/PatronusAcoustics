#include "spectrum.h"
#include "audio_config.h"

/*
 * One shared analysis stage: DC removal, window, real FFT.
 *
 * Both log-mel and SRP-PHAT read the same output, so the transform runs once
 * per block. Every choice that is neither hardware nor consumer-specific --
 * window shape, transform length, highpass -- lives here and nowhere else.
 *
 * Output is expanded from the CMSIS packed layout into SPECTRUM_BINS proper
 * complex pairs: spec[ch][2k] = Re(bin k), spec[ch][2k+1] = Im(bin k).
 * DC and Nyquist have zero imaginary part. Consumers can index bins uniformly
 * instead of special-casing the packed first two floats.
 */

#define DTCM_BUF ".dtcm_buf"

/* Periodic Hann (divide by N, not N-1): the block is one period of a
 * continuing signal, and 50%-overlapped periodic Hann sums to unity. */
static float32_t _window[FFT_BUFFER_SIZE];

static arm_rfft_fast_instance_f32 _rfft;

/* arm_rfft_fast_f32 destroys its input, so windowing happens in scratch and
 * the caller's pcm stays intact for level metering, raw dumps, and tests. */
static float32_t _td[FFT_BUFFER_SIZE] __attribute__((section(DTCM_BUF), aligned(32)));
static float32_t _packed[FFT_BUFFER_SIZE] __attribute__((section(DTCM_BUF), aligned(32)));

static void _window_init(void)
{
    for (uint32_t n = 0; n < FFT_BUFFER_SIZE; ++n)
        _window[n] = 0.5f * (1.0f - arm_cos_f32(2.0f * PI * (float32_t)n / (float32_t)FFT_BUFFER_SIZE));
}

/* CMSIS packs the real FFT as [0]=DC, [1]=Nyquist (both purely real), then
 * [2k],[2k+1] = Re,Im for k = 1 .. N/2-1. Expanding once here means neither
 * consumer has to remember that. */
static void _unpack(const float32_t* packed, float32_t* out)
{
    out[0] = packed[0]; // DC - real
    out[1] = 0.0f;      // DC - imaginary

    for (uint32_t k = 1; k < FFT_BUFFER_SIZE / 2; ++k)
    {
        out[2 * k]     = packed[2 * k];
        out[2 * k + 1] = packed[2 * k + 1];
    }

    out[2 * (SPECTRUM_BINS - 1)]     = packed[1]; // Nyquist - real
    out[2 * (SPECTRUM_BINS - 1) + 1] = 0.0f;      // Nyquist - imaginary
}

void spectrum_init(void)
{
    _window_init();
    arm_rfft_fast_init_f32(&_rfft, FFT_BUFFER_SIZE);
}

void spectrum_compute(const float32_t (*pcm)[AUDIO_SAMPLES_PER_BLOCK], float32_t (*spec)[SPECTRUM_FLOATS])
{
    for (uint32_t ch = 0; ch < AUDIO_MIC_COUNT; ++ch)
    {
        /* DC before windowing: windowing an offset signal smears it across the
         * low bins instead of leaving it in bin 0 where it is easy to ignore. */
        float32_t mean;
        arm_mean_f32((float32_t*)pcm[ch], FFT_BUFFER_SIZE, &mean);
        arm_offset_f32((float32_t*)pcm[ch], -mean, _td, FFT_BUFFER_SIZE);

        arm_mult_f32(_td, _window, _td, FFT_BUFFER_SIZE);

        arm_rfft_fast_f32(&_rfft, _td, _packed, 0);
        _unpack(_packed, spec[ch]);
    }
}
