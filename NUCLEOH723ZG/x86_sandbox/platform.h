#ifndef ICS52000_H
#define ICS52000_H

#include "random.h"
#include "arm_math.h"

#include <stdint.h>
#include <stdbool.h>

#define ARRAY_COUNT(array) (sizeof(array) / sizeof((array)[0]))

#define local_persist static
#define internal static
#define global static

typedef float float32_t;
typedef uint32_t bool32;
typedef int16_t sample_t;

#define SCALING_FACTOR(type) _Generic((type){0},            \
                                      int16_t:   INT16_MAX, \
                                      int32_t:   INT32_MAX, \
                                      float32_t: 1)

//-----------------------
//   audio_config.h
#define MIC_COUNT      5
#define AUDIO_SAMPLES  512
#define SAMPLE_RATE_HZ 16000.0f
//-----------------------

enum
{
    ICS_MIC_COUNT     = MIC_COUNT,
    ICS_AUDIO_SAMPLES = AUDIO_SAMPLES,
};

typedef struct
{
    float32_t x;
    float32_t y;
    float32_t z;
} Vec3;

typedef struct
{
    Vec3 mics[ICS_MIC_COUNT];
} MicArray;

typedef struct
{
    float32_t azimuth;
    float32_t elevation;
} AngleDeg;

typedef struct
{
    // WARN: This motherfucker is interleaved
    sample_t pcm[ICS_AUDIO_SAMPLES][ICS_MIC_COUNT];
} AudioFrame;

typedef struct
{
    AudioFrame* frame;
    uint64_t seq;
} AudioViewFrame;

bool32 populate_frame(rng_t* r, AudioViewFrame* view, MicArray array, AngleDeg direction);

// TODO(sok): Startup of WS should be 300 ms!
#endif
