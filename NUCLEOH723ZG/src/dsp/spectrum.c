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

// CMSIS-DSP configuration instance
static arm_rfft_fast_instance_f32 _rfft_cfg;

/* --------- LINKER BINDINGS --------- */

#define SPECTRUM_DTCM_BUF ".dtcm_buf"

/* --------- ANALYSIS BUFFERS --------- */

/* OUTPUT BUFFER - the caller is handed a pointer to this specific buffer!
 * (specifically a pointer to the first row of the 2D array). */
static float32_t _SPECTRUM[AUDIO_MIC_COUNT][SPECTRUM_FLOATS] __attribute__((section(SPECTRUM_DTCM_BUF), aligned(32)));

/* Periodic Hann (divide by N, not N-1): the block is one period of a
 * continuing signal, and 50%-overlapped periodic Hann sums to unity. */
static float32_t _hann[SPECTRUM_FFT_SIZE];

/* arm_rfft_fast_f32 destroys its input, so windowing happens in scratch and
 * the caller's pcm stays intact for level metering, raw dumps, and tests. */
static float32_t _windowed[SPECTRUM_FFT_SIZE] __attribute__((section(SPECTRUM_DTCM_BUF), aligned(32)));

// CMSIS packed layout, one channel, valid only inside spectrum_compute()
static float32_t _packed[SPECTRUM_FFT_SIZE] __attribute__((section(SPECTRUM_DTCM_BUF), aligned(32)));

/* --------- WINDOW --------- */

static void _hann_init(void)
{
    for (uint32_t n = 0; n < SPECTRUM_FFT_SIZE; ++n)
        _hann[n] = 0.5f * (1.0f - arm_cos_f32(2.0f * PI * (float32_t)n / (float32_t)SPECTRUM_FFT_SIZE));
}

/* --------- BIN EXPANSION --------- */

/* CMSIS packs the real FFT as [0]=DC, [1]=Nyquist (both purely real), then
 * [2k],[2k+1] = Re,Im for k = 1 .. N/2-1. Expanding once here means neither
 * consumer has to remember that. */
static void _expand_bins(const float32_t* packed, float32_t* out)
{
    out[0] = packed[0]; // DC - real
    out[1] = 0.0f;      // DC - imaginary

    for (uint32_t k = 1; k < SPECTRUM_FFT_SIZE / 2; ++k)
    {
        out[2 * k]     = packed[2 * k];
        out[2 * k + 1] = packed[2 * k + 1];
    }

    out[2 * (SPECTRUM_BINS - 1)]     = packed[1]; // Nyquist - real
    out[2 * (SPECTRUM_BINS - 1) + 1] = 0.0f;      // Nyquist - imaginary
}

/* --------- PUBLIC API --------- */

void spectrum_init(void)
{
    _hann_init();
    arm_rfft_fast_init_f32(&_rfft_cfg, SPECTRUM_FFT_SIZE);
}

/* CMSIS takes non-const pointers even for pure reads, so the const cast is
 * confined here rather than repeated at every call site. */
static void _analyze_channel(float32_t* pcm, float32_t* bins)
{
    /* DC before windowing: windowing an offset signal smears it across the
     * low bins instead of leaving it in bin 0 where it is easy to ignore. */
    float32_t dc;
    arm_mean_f32(pcm, SPECTRUM_FFT_SIZE, &dc);
    arm_offset_f32(pcm, -dc, _windowed, SPECTRUM_FFT_SIZE);

    arm_mult_f32(_windowed, _hann, _windowed, SPECTRUM_FFT_SIZE);
    arm_rfft_fast_f32(&_rfft_cfg, _windowed, _packed, 0);

    _expand_bins(_packed, bins);
}

void spectrum_compute(float32_t* const frame[AUDIO_MIC_COUNT], const float32_t (**spec)[SPECTRUM_FLOATS])
{
    for (uint32_t ch = 0; ch < AUDIO_MIC_COUNT; ++ch)
	{
		_analyze_channel(frame[ch], _SPECTRUM[ch]);
	}

	// Pointer to the first row of spectrum samples
	*spec = &_SPECTRUM[0];
}
