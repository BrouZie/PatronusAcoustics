#ifndef DSP_H
#define DSP_H

#include "platform.h"

// General DSP
enum
{
    DSP_COMPLEX_BINS = AUDIO_SAMPLES + 1,
    DSP_BUFFER_LEN      = AUDIO_SAMPLES * 2,
    NUM_MIC_PAIRS    = (MIC_COUNT * (MIC_COUNT - 1) / 2),
};

// SRP-PHAT
enum
{
    SRP_BAND_MIN_HZ = 100,  // previous: 300
    SRP_BAND_MAX_HZ = 500,  // previous: 3000

    SRP_BIN_LO = (SRP_BAND_MIN_HZ * DSP_BUFFER_LEN) / (int)SAMPLE_RATE_HZ,
    SRP_BIN_HI = (SRP_BAND_MAX_HZ * DSP_BUFFER_LEN) / (int)SAMPLE_RATE_HZ, // exclusive

    SRP_ELEVATION_STEPS = 121,
    SRP_AZIMUTH_STEPS   = 121,
    SRP_DIRECTIONS      = (SRP_AZIMUTH_STEPS * SRP_ELEVATION_STEPS)
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
    float32_t pcm[MIC_COUNT][AUDIO_SAMPLES];
} PrevAudioFrame;

typedef struct
{
    float32_t bins[MIC_COUNT][DSP_BUFFER_LEN];
    float32_t scratch[DSP_BUFFER_LEN];
} FFT_Spectrum;

// SRP-PHAT structs
typedef struct
{
    uint16_t first, second;
} MicPair;

typedef struct
{
    uint16_t  i0;
    uint16_t  i1;
    float32_t alpha;
} TimeLagLerp;

typedef struct
{
    float32_t az_start, az_step, el_start, el_step;
} SRP_Grid;

typedef struct
{
    TimeLagLerp candidates[SRP_DIRECTIONS][NUM_MIC_PAIRS];
    MicPair     pairs[NUM_MIC_PAIRS];
    SRP_Grid    grid;
} SRP_State;

typedef struct
{
    float32_t   correlations[NUM_MIC_PAIRS][DSP_BUFFER_LEN];
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

void dsp_beamform_ds(const FFT_Spectrum* spec, const MicArray* pos, float32_t az, float32_t el, float32_t* beamed_spec);

void dsp_compute_logmel_frame(float32_t* scratch, const float32_t* spec, Logmel* mel_out);

#endif // DSP_H
