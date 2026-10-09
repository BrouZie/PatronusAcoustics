#include "srp.h"
#include "audio_config.h"
#include "random.h"

#include <stdio.h>

// Where populate_spectrum places the dummy source
#define TEST_SOURCE_AZ_DEG 60.0f
#define TEST_SOURCE_EL_DEG 90.0f

// Arrival delay per mic (in samples) for a plane wave from (az, el) degrees
static void _mic_delays(const mic_array_t *arr, float32_t az, float32_t el, float32_t *delay)
{
    float32_t sin_az, cos_az, sin_el, cos_el;
    arm_sin_cos_f32(az, &sin_az, &cos_az); // takes degrees
    arm_sin_cos_f32(el, &sin_el, &cos_el);
    vec3_t u = { sin_el * cos_az, sin_el * sin_az, cos_el };

    for (uint32_t mic = 0; mic < arr->count; ++mic)
    {
        const vec3_t *v = &arr->mic[mic];
        delay[mic] = -(v->x * u.x + v->y * u.y + v->z * u.z) * SRP_SAMPLES_PER_METER;
    }
}

// Reduces 4 (2 x 2) -> 2 samples
static inline void _gcc_phat(const float32_t *mic_l, const float32_t *mic_m, float32_t *out)
{
    float32_t real = mic_l[0] * mic_m[0] + mic_l[1] * mic_m[1];
    float32_t imag = mic_l[1] * mic_m[0] - mic_l[0] * mic_m[1];

    float32_t mag_sq = real * real + imag * imag;
    float32_t denom  = powf(mag_sq, 0.5f * SRP_BETA) + SRP_EPS; // NOTE: powf is expensive - consider using approximation instead

    out[0] = real / denom;
    out[1] = imag / denom;
}

// GCC-PHAT per pair, written straight into the CMSIS packed layout, then IFFT
static void _cross_spectra(srp_t *s, const float32_t spec[][SPECTRUM_FLOATS])
{
    for (uint32_t pair_idx = 0; pair_idx < NUM_MIC_PAIRS; ++pair_idx)
    {
        const float32_t *mic_l = spec[s->pair[pair_idx].l];
        const float32_t *mic_m = spec[s->pair[pair_idx].m];

        // bins outside the band stay zero - refilled per pair since the IFFT destroys its input
        memset(s->packed, 0, sizeof(s->packed));

        for (uint16_t bin_idx = s->bin_lo; bin_idx <= s->bin_hi - 1; ++bin_idx)
        {
            _gcc_phat(&mic_l[bin_idx * 2], &mic_m[bin_idx * 2], &s->packed[bin_idx * 2]);
        }

        #define INVERSE_FFT 1
        arm_rfft_fast_f32(&s->ifft, s->packed, s->corr[pair_idx], INVERSE_FFT);
    }
}

// Per candidate: sum every pair's correlation at the lag that candidate predicts
static void _steer(srp_t *s)
{
    uint32_t directions = (uint32_t)s->grid.az_steps * s->grid.el_steps;
    for (uint32_t dir_idx = 0; dir_idx < directions; ++dir_idx)
    {
        float32_t power = 0.0f;
        for (uint32_t pair_idx = 0; pair_idx < NUM_MIC_PAIRS; ++pair_idx)
        {
            const float32_t *corr = s->corr[pair_idx];
            const tap_t     *tap  = &s->tap[dir_idx][pair_idx];
            power += corr[tap->i0] + tap->w * (corr[tap->i1] - corr[tap->i0]);
        }
        s->map[dir_idx] = power;
    }
}

static doa_t _peak(const srp_t *s)
{
    uint32_t  directions = (uint32_t)s->grid.az_steps * s->grid.el_steps;
    uint32_t  dir_idx;
    float32_t power;
    arm_max_f32(s->map, directions, &power, &dir_idx);

    // azimuth major: dir_idx = az_idx * el_steps + el_idx
    return (doa_t) {
        .az    = s->grid.az0 + ((float32_t)dir_idx / s->grid.el_steps) * s->grid.az_step,
        .el    = s->grid.el0 + ((float32_t)dir_idx / s->grid.el_steps) * s->grid.el_step,
        .power = power,
        .ratio = 0.0f, // TODO: add ratio
    };
}

void  srp_init(srp_t *s, const mic_array_t *arr, const grid_t *g)
{
    s->grid = *g;

    arm_rfft_fast_init_f32(&s->ifft, SPECTRUM_FFT_SIZE);

    // NOTE: must stay within 1 .. SPECTRUM_BINS - 2 (DC and Nyquist are packed differently)
    s->bin_lo = (uint16_t)(SRP_BAND_MIN_HZ * SPECTRUM_FFT_SIZE / AUDIO_SAMPLE_RATE_HZ);
    s->bin_hi = (uint16_t)(SRP_BAND_MAX_HZ * SPECTRUM_FFT_SIZE / AUDIO_SAMPLE_RATE_HZ);

    uint16_t pair_idx = 0;
    for (uint16_t mic_l = 0; mic_l < arr->count; ++mic_l)
    {
        for (uint16_t mic_m = (uint16_t)(mic_l + 1); mic_m < arr->count; ++mic_m)
        {
            s->pair[pair_idx++] = (pair_t){ .l = mic_l, .m = mic_m };
        }
    }

    uint32_t dir_idx = 0;
    for (uint32_t az_idx = 0; az_idx < g->az_steps; ++az_idx)
    {
        for (uint32_t el_idx = 0; el_idx < g->el_steps; ++el_idx, ++dir_idx)
        {
            float32_t delay[AUDIO_MIC_COUNT];
            _mic_delays(arr, g->az0 + (float32_t)az_idx * g->az_step, g->el0 + (float32_t)el_idx * g->el_step, delay);

            for (pair_idx = 0; pair_idx < NUM_MIC_PAIRS; ++pair_idx)
            {
                float32_t tau   = delay[s->pair[pair_idx].l] - delay[s->pair[pair_idx].m];
                float32_t floor = floorf(tau);

                // mask wraps negative lags to the end of the IFFT output
                uint16_t i0 = (uint16_t)((int32_t)floor & (SPECTRUM_FFT_SIZE - 1));
                s->tap[dir_idx][pair_idx] = (tap_t){
                    .i0 = i0,
                    .i1 = (uint16_t)((i0 + 1) & (SPECTRUM_FFT_SIZE - 1)),
                    .w  = tau - floor,
                };
            }
        }
    }
}

doa_t srp_compute(srp_t *restrict s, const float32_t spec[][SPECTRUM_FLOATS])
{
    _cross_spectra(s, spec);
    _steer(s);
    return _peak(s);
}

//=============== SANDBOX ===============//

static const vec3_t MIC_POSITIONS[AUDIO_MIC_COUNT] = {
    { -0.05f, 0.0f, 0.0f },
    { 0.05f, 0.0f, 0.0f },
};
static const mic_array_t MIC_ARRAY = { .mic = MIC_POSITIONS, .count = AUDIO_MIC_COUNT };

// el is polar angle from +z, 90 = array plane
static const grid_t GRID = {
    .az0 = 30.0f, .az_step = 1.0f, .az_steps = SRP_AZIMUTH_DIRECTIONS,
    .el0 = 90.0f, .el_step = 1.0f, .el_steps = 1,
};

static srp_t     g_srp;
static float32_t g_spec[AUDIO_MIC_COUNT][SPECTRUM_FLOATS];

// One source: every mic gets the same random spectrum, phase shifted by its arrival delay
static void populate_spectrum(rng_t *seed)
{
    float32_t delay[AUDIO_MIC_COUNT];
    _mic_delays(&MIC_ARRAY, TEST_SOURCE_AZ_DEG, TEST_SOURCE_EL_DEG, delay);

    for (int bin_idx = 0; bin_idx < SPECTRUM_BINS; ++bin_idx)
    {
        float32_t real = arm_rng_rangef32(seed, -1.0f, 1.0f);
        float32_t imag = arm_rng_rangef32(seed, -1.0f, 1.0f);

        for (int mic = 0; mic < AUDIO_MIC_COUNT; ++mic)
        {
            // delay of d samples = rotation by -2*pi*k*d/N at bin k
            float32_t phase = -2.0f * PI * (float32_t)bin_idx * delay[mic] / (float32_t)SPECTRUM_FFT_SIZE;
            float32_t cos_p = arm_cos_f32(phase);
            float32_t sin_p = arm_sin_f32(phase);

            g_spec[mic][bin_idx * 2]     = real * cos_p - imag * sin_p;
            g_spec[mic][bin_idx * 2 + 1] = real * sin_p + imag * cos_p;
        }
    }
}

int main()
{
    rng_t r;
    rng_seed(&r, 0);
    populate_spectrum(&r);

    srp_init(&g_srp, &MIC_ARRAY, &GRID);
    doa_t doa = srp_compute(&g_srp, g_spec);

    printf("az %.1f el %.1f power %f\n", doa.az, doa.el, doa.power);

    return 0;
}
