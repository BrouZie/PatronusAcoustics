#ifndef SRP_H
#define SRP_H

#include "arm_math.h"
#include "audio_config.h"

#define SRP_MIC_PAIR_COUNT (AUDIO_MIC_COUNT * (AUDIO_MIC_COUNT - 1) / 2)
#define SRP_SPEED_OF_SOUND 343.0f
#define SRP_SAMPLES_PER_METER ((float32_t)AUDIO_SAMPLE_RATE_HZ / SRP_SPEED_OF_SOUND)
#define SRP_BETA 0.7f                   // proven to yield better results between 0.6 - 0.8
#define SRP_EPS 1e-12f                  // TODO: Make it relative to running magnitude scale

#define SRP_BAND_MIN_HZ 300             // only bins inside the band contribute
#define SRP_BAND_MAX_HZ 3000

typedef struct
{
    float32_t x;
    float32_t y;
    float32_t z;
} vec3_t;

typedef struct
{
    const vec3_t* mic;
    uint32_t count;
} mic_array_t;

typedef struct
{
    float32_t az0;
    float32_t az_step;
    float32_t el0;
    float32_t el_step;

    uint16_t az_steps;
    uint16_t el_steps;
} grid_t;

typedef struct
{
    float32_t az;
    float32_t el;
    float32_t power;
    float32_t ratio;
} doa_t;

typedef struct
{
    uint16_t l;
    uint16_t m;
} pair_t;

typedef struct
{
    uint16_t i0;
    uint16_t i1;
    float32_t w;
} tap_t; // 2-tap fractional lag

typedef struct {
    // --- built once by srp_init --- //
    arm_rfft_fast_instance_f32 ifft;
    grid_t   grid;
    pair_t   pair[NUM_MIC_PAIRS];
    tap_t    tap[SRP_AZIMUTH_DIRECTIONS][NUM_MIC_PAIRS];

    // Band limiting to reduce work
    // Set to SRP_BAND_MIN_HZ & SRP_BAND_MAX_HZ at init
    uint16_t bin_lo;
    uint16_t bin_hi;

    // --- overwritten every hop --- //
    float32_t packed[SPECTRUM_FFT_SIZE];
    float32_t corr[NUM_MIC_PAIRS][SPECTRUM_FFT_SIZE];
    float32_t map[SRP_AZIMUTH_DIRECTIONS];
} srp_t;

void  srp_init(srp_t *s, const mic_array_t *arr, const grid_t *g);
doa_t srp_compute(srp_t *restrict s, const float32_t spec[][SPECTRUM_FLOATS]);

#endif // SRP_H
