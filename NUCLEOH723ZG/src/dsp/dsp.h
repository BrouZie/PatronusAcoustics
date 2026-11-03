#ifndef DSP_H
#define DSP_H

#include "types.h"

// General DSP
enum
{
    DSP_COMPLEX_BINS = AUDIO_SAMPLES + 1,
    DSP_BUFFER_LEN   = AUDIO_SAMPLES * 2,
    NUM_MIC_PAIRS    = (MIC_COUNT * (MIC_COUNT - 1) / 2),
};

// SRP-PHAT
enum
{
    // SRP_BAND_MIN_HZ = 100,
    // SRP_BAND_MAX_HZ = 500,
    SRP_BAND_MIN_HZ = 300,
    SRP_BAND_MAX_HZ = 3000,

    SRP_BIN_LO = (SRP_BAND_MIN_HZ * DSP_BUFFER_LEN) / (int)SAMPLE_RATE_HZ,
    SRP_BIN_HI = (SRP_BAND_MAX_HZ * DSP_BUFFER_LEN) / (int)SAMPLE_RATE_HZ, // exclusive

    SRP_ELEVATION_STEPS = 91,
    SRP_AZIMUTH_STEPS   = 91,
    SRP_DIRECTIONS      = (SRP_AZIMUTH_STEPS * SRP_ELEVATION_STEPS),

    // NOTE: If the array aperture is changed, you'll have to change this too!
    // Largest |tau| (in samples) the array geometry can produce, with margin.
    // Current array: ~0.254 m aperture * 16000/343 ≈ 11.9 samples.
    // TODO(sok): Make MicArray positions compile-time constants and derive
    // SRP_MAX_LAG and SRP_LAG_WINDOW from them.
    SRP_MAX_LAG    = 16,
    SRP_LAG_WINDOW = (2 * SRP_MAX_LAG + 2), // lags [-MAX_LAG, MAX_LAG + 1]
};

// Logmel
enum
{
    NUM_MEL_BANDS = 128,
    MIN_FREQUENCY = 100,
    MAX_FREQUENCY = 8000,
};

// Structs for FFT spectrum and general DSP
typedef struct
{
    sample_t pcm[MIC_COUNT][AUDIO_SAMPLES];
} PrevAudioFrame;

typedef struct
{
    float32_t bins[MIC_COUNT][DSP_BUFFER_LEN];
    float32_t scratch[DSP_BUFFER_LEN];
} FFT_Spectrum;

// SRP-PHAT structs
typedef struct
{
    float32_t x, y, z;
} Vec3;

// TODO: Make the positions compile-time known
typedef struct
{
    Vec3 pos[MIC_COUNT];
} MicArray;

typedef struct
{
    uint16_t first, second;
} MicPair;

// TODO: Make the grid compile-time known
typedef struct
{
    float32_t az_start, az_step, el_start, el_step;
} SRP_Grid;

typedef struct
{
    MicPair   pairs[NUM_MIC_PAIRS];
    Vec3      pair_delta[NUM_MIC_PAIRS];
    float32_t sin_az[SRP_AZIMUTH_STEPS], cos_az[SRP_AZIMUTH_STEPS];
    float32_t sin_el[SRP_ELEVATION_STEPS], cos_el[SRP_ELEVATION_STEPS];
    SRP_Grid  grid;
} SRP_State;

typedef struct
{
    float32_t   correlations[NUM_MIC_PAIRS][SRP_LAG_WINDOW];
    float32_t   ifft_out[DSP_BUFFER_LEN];
    float32_t   map[SRP_DIRECTIONS];

    float32_t   azimuth;
    float32_t   elevation;
    float32_t   power;
} SRP_PHAT;

// Logmel structs
typedef struct
{
    float32_t frame[NUM_MEL_BANDS];
} Logmel;

void dsp_init_spectrum(void);
void dsp_compute_spectrum(const AudioFrame* frame, PrevAudioFrame* prev, FFT_Spectrum* spectra);

void dsp_init_srp(const SRP_Grid* grid, const MicArray* pos, SRP_State* state);
void dsp_compute_srp(const SRP_State* state, FFT_Spectrum* spec, SRP_PHAT* srp);
void dsp_beamform_delay_sum(const FFT_Spectrum* spec, const MicArray* pos, float32_t az, float32_t el, float32_t* beamed_spec);

void dsp_compute_logmel_frame(float32_t* scratch, const float32_t* spec, Logmel* mel_out);

#endif // DSP_H
