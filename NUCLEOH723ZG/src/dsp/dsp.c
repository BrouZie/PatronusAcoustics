#include "dsp.h"

#include "mel_fbank.h"

#define SRP_BETA 0.7f    // yields better results between 0.6 - 0.8 (source: trust me bro)
#define SRP_EPS  1e-12f  // TODO: Make it relative to running magnitude scale
#define SRP_SAMPLES_PER_METER ((float32_t)SAMPLE_RATE_HZ / 343.0f)

#define MEL_EPS 1e-10f

_Static_assert(SRP_BIN_LO >= 1,                      "band can't start at DC");
_Static_assert(SRP_BIN_HI <= DSP_COMPLEX_BINS,       "band exceeds spectrum");
_Static_assert(SRP_LAG_WINDOW <= DSP_BUFFER_LEN / 2, "Lag window wider than IFFT output");

_Static_assert((int)SAMPLE_RATE_HZ == 16000,   "mel_fbank.h generated for 16 kHz");
_Static_assert(DSP_BUFFER_LEN == 1024,         "mel_fbank.h generated for n_fft=1024");

global arm_rfft_fast_instance_f32 Rfft;
global float32_t HannConstants[DSP_BUFFER_LEN];

internal inline void populate_hann(void)
{
    for (uint32_t i = 0; i < AUDIO_SAMPLES * 2; ++i)
    {
        HannConstants[i] = 0.5f * (1.0f - arm_cos_f32(2.0f * PI * (float32_t)i / ((float32_t)AUDIO_SAMPLES * 2)));
    }
}

void dsp_init_spectrum(void)
{
    arm_rfft_fast_init_f32(&Rfft, DSP_BUFFER_LEN);
    populate_hann();
}

void dsp_compute_spectrum(const AudioFrame* frame, PrevAudioFrame* prev, FFT_Spectrum* spec)
{
    for (uint32_t mic_idx = 0; mic_idx < MIC_COUNT; ++mic_idx)
    {
        for (uint32_t sample_idx = 0; sample_idx < AUDIO_SAMPLES; ++sample_idx)
        {
            uint32_t new_half = AUDIO_SAMPLES + sample_idx;
            spec->scratch[sample_idx] = (float32_t)prev->pcm[mic_idx][sample_idx] / (float32_t)SCALING_FACTOR(sample_t);
            spec->scratch[new_half]   = (float32_t)frame->pcm[sample_idx][mic_idx] / (float32_t)SCALING_FACTOR(sample_t);

            // Save frame for next iteration
            prev->pcm[mic_idx][sample_idx] = frame->pcm[sample_idx][mic_idx];
        }
        // Remove DC offset drift (should be ~0)
        float32_t mean;
        arm_mean_f32(spec->scratch, DSP_BUFFER_LEN, &mean);
        arm_offset_f32(spec->scratch, -mean, spec->scratch, DSP_BUFFER_LEN);

        // Hann window applied
        arm_mult_f32(spec->scratch, HannConstants, spec->scratch, DSP_BUFFER_LEN);

        // Actual fft
        arm_rfft_fast_f32(&Rfft, spec->scratch, spec->bins[mic_idx], 0);
    }
}

internal inline Vec3 angles_to_vec3(float32_t az_deg, float32_t el_deg)
{
    float32_t sin_az, cos_az, sin_el, cos_el;
    arm_sin_cos_f32(az_deg, &sin_az, &cos_az);
    arm_sin_cos_f32(el_deg, &sin_el, &cos_el);

    return (Vec3) {
        .x = cos_el * sin_az,
        .y = sin_el,
        .z = cos_el * cos_az,
    };
}

internal void mic_delay_samples(const MicArray* pos, float32_t az, float32_t el, float32_t* delay)
{
    Vec3 sound_src = angles_to_vec3(az, el);

    for (uint32_t mic_idx = 0; mic_idx < MIC_COUNT; ++mic_idx)
    {
        const Vec3* mic_pos = &pos->pos[mic_idx];
        delay[mic_idx] = - (mic_pos->x * sound_src.x + mic_pos->y * sound_src.y + mic_pos->z * sound_src.z) * SRP_SAMPLES_PER_METER;
    }
}

void dsp_init_srp(const SRP_Grid* grid, const MicArray* arr, SRP_State* state)
{
    state->grid = *grid;

    uint8_t pair_idx = 0;
    for (uint8_t mic1 = 0; mic1 < MIC_COUNT; ++mic1)
    {
        for (uint8_t mic2 = mic1 + 1; mic2 < MIC_COUNT; ++mic2)
        {
            const Vec3* p1 = &arr->pos[mic1];
            const Vec3* p2 = &arr->pos[mic2];

            // tau = delay[first] - delay[second] = dot(p2 - p1, u) * fs / c
            Vec3 d = {
                .x = (p2->x - p1->x) * SRP_SAMPLES_PER_METER,
                .y = (p2->y - p1->y) * SRP_SAMPLES_PER_METER,
                .z = (p2->z - p1->z) * SRP_SAMPLES_PER_METER,
            };
            // |u| = 1, so |tau| <= |d| <= L1 norm; must fit the compact lag window
            // TODO: Remove when mic positions are compiletime known
            ASSERT(sqrtf(d.x * d.x + d.y * d.y + d.z * d.z) < (float32_t)SRP_MAX_LAG);

            state->pairs[pair_idx] = (MicPair) { .first = mic1, .second = mic2 };
            state->pair_delta[pair_idx++] = d;
        }
    }

    for (uint32_t az_idx = 0; az_idx < SRP_AZIMUTH_STEPS; ++az_idx)
    {
        arm_sin_cos_f32(grid->az_start + (float32_t)az_idx * grid->az_step, &state->sin_az[az_idx], &state->cos_az[az_idx]);
    }
    for (uint32_t el_idx = 0; el_idx < SRP_ELEVATION_STEPS; ++el_idx)
    {
        arm_sin_cos_f32(grid->el_start + (float32_t)el_idx * grid->el_step, &state->sin_el[el_idx], &state->cos_el[el_idx]);
    }
}

internal inline void srp_map_lookup(const SRP_State* state, SRP_PHAT* srp)
{
    // az outer / el inner keeps dir_idx = az_idx * EL_STEPS + el_idx (argmax decode relies on it)
    uint32_t dir_idx = 0;
    for (uint32_t az_idx = 0; az_idx < SRP_AZIMUTH_STEPS; ++az_idx)
    {
        for (uint32_t el_idx = 0; el_idx < SRP_ELEVATION_STEPS; ++el_idx)
        {
            // Same mathmatical computation as is done in angles_to_vec3()
            const float32_t ux = state->cos_el[el_idx] * state->sin_az[az_idx];
            const float32_t uy = state->sin_el[el_idx];
            const float32_t uz = state->cos_el[el_idx] * state->cos_az[az_idx];

            float32_t power = 0.0f;
            for (uint32_t pair_idx = 0; pair_idx < NUM_MIC_PAIRS; ++pair_idx)
            {
                const Vec3*      d    = &state->pair_delta[pair_idx];
                const float32_t* corr = srp->correlations[pair_idx];

                float32_t tau   = d->x * ux + d->y * uy + d->z * uz;
                float32_t floor = floorf(tau);
                int32_t   i0    = (int32_t)floor + SRP_MAX_LAG; // compact window, no wrap needed

                power += corr[i0] + (tau - floor) * (corr[i0 + 1] - corr[i0]);
            }
            srp->map[dir_idx++] = power;
        }
    }
}

void dsp_compute_srp(const SRP_State* state, FFT_Spectrum* spec, SRP_PHAT* srp)
{
    // Generation of correlation coefficionts
    for (uint32_t pair_idx = 0; pair_idx < NUM_MIC_PAIRS; ++pair_idx)
    {
        // Ensure scratch buffer is zeroed!
        memset(spec->scratch, 0, sizeof(spec->scratch));

        // DSP_FFT_LEN samples in each array (1024 most likely)
        const float32_t* first_spec = spec->bins[state->pairs[pair_idx].first];
        const float32_t* second_spec = spec->bins[state->pairs[pair_idx].second];

        // Only looping over
        for (uint16_t bin_idx = SRP_BIN_LO; bin_idx <= SRP_BIN_HI - 1; ++bin_idx)
        {
            // This loop does the actual GCC-PHAT
            uint16_t spec_idx = bin_idx * 2;

            // spec_idx return the real part while adding "+ 1" accesses the imaginary part
            float32_t real = first_spec[spec_idx] * second_spec[spec_idx] + first_spec[spec_idx + 1] * second_spec[spec_idx + 1];
            float32_t imag = first_spec[spec_idx + 1] * second_spec[spec_idx] - first_spec[spec_idx] * second_spec[spec_idx + 1];

            float32_t mag_sq = real * real + imag * imag;
            float32_t denom  = powf(mag_sq, 0.5f * SRP_BETA) + SRP_EPS; // NOTE: powf is expensive - consider using approximation instead

            spec->scratch[spec_idx]     = real / denom;
            spec->scratch[spec_idx + 1] = imag / denom;
        }
        #define INVERSE_FFT 1
        arm_rfft_fast_f32(&Rfft, spec->scratch, srp->ifft_out, INVERSE_FFT);

        // Keep only lags [-MAX_LAG, MAX_LAG + 1]; negative lags wrap to the end of the IFFT output
        float32_t* row = srp->correlations[pair_idx];
        memcpy(row,               &srp->ifft_out[DSP_BUFFER_LEN - SRP_MAX_LAG], SRP_MAX_LAG       * sizeof(float32_t));
        memcpy(row + SRP_MAX_LAG, &srp->ifft_out[0],                            (SRP_MAX_LAG + 2) * sizeof(float32_t));
    }

    srp_map_lookup(state, srp);

    // Argmaxing srp map
    uint32_t dir_idx = 0;
    arm_max_f32(srp->map, SRP_DIRECTIONS, &srp->power, &dir_idx);
    uint32_t az_idx = dir_idx / SRP_ELEVATION_STEPS;
    uint32_t el_idx = dir_idx % SRP_ELEVATION_STEPS;

    srp->azimuth   = state->grid.az_start + (float32_t)az_idx * state->grid.az_step;
    srp->elevation = state->grid.el_start + (float32_t)el_idx * state->grid.el_step;
}

void dsp_beamform_delay_sum(const FFT_Spectrum* spec, const MicArray* pos, float32_t az, float32_t el, float32_t* beamed_spec)
{
    float32_t delay[MIC_COUNT];
    mic_delay_samples(pos, az, el, delay);

    float32_t dc = 0.0f, nyq = 0.0f;
    for (uint32_t mic_idx = 0; mic_idx < MIC_COUNT; ++mic_idx)
    {
        dc  += spec->bins[mic_idx][0];
        nyq += spec->bins[mic_idx][1];
    }
    beamed_spec[0] = dc  / (float32_t)MIC_COUNT;
    beamed_spec[1] = nyq / (float32_t)MIC_COUNT;  // unsteered; mel never reads Nyquist

    for (uint32_t bin_idx = 1; bin_idx < DSP_COMPLEX_BINS - 1; ++bin_idx)
    {
        float32_t real = 0.0f, imag = 0.0f;
        for (uint32_t mic_idx = 0; mic_idx < MIC_COUNT; ++mic_idx)
        {
            float32_t phi_deg = 360.0f * (float32_t)bin_idx * delay[mic_idx] / (float32_t)DSP_BUFFER_LEN;
            float32_t s, c;
            arm_sin_cos_f32(phi_deg, &s, &c);

            float32_t xr = spec->bins[mic_idx][bin_idx * 2];
            float32_t xi = spec->bins[mic_idx][bin_idx * 2 + 1];
            real += xr * c - xi * s;
            imag += xr * s + xi * c;
        }
        beamed_spec[bin_idx * 2]     = real / (float32_t)MIC_COUNT;
        beamed_spec[bin_idx * 2 + 1] = imag / (float32_t)MIC_COUNT;
    }
}

internal void get_power_spectrum(const float32_t* spec, float32_t* power)
{
    power[0]             = spec[0] * spec[0];  // DC (real only)
    power[AUDIO_SAMPLES] = spec[1] * spec[1];  // Nyquist (real only)
    arm_cmplx_mag_squared_f32((float32_t*)&spec[2], &power[1], AUDIO_SAMPLES - 1);
}

internal void apply_logmel(const float32_t* power, float32_t* mel_out)
{
    const float32_t* w = MEL_WEIGHTS;
    for (uint32_t m = 0; m < NUM_MEL_BANDS; ++m)
    {
        float32_t energy = 0.0f;
        if (MEL_COUNT[m])
        {
            arm_dot_prod_f32((float32_t*)&power[MEL_START[m]], (float32_t*)w, MEL_COUNT[m], &energy);
        }
        w += MEL_COUNT[m];
        mel_out[m] = 10.0f * log10f(energy + MEL_EPS);
    }
}

void dsp_compute_logmel_frame(float32_t* scratch, const float32_t* spec, Logmel* mel_out)
{
    get_power_spectrum(spec, scratch);
    apply_logmel(scratch, mel_out->frame);
}
