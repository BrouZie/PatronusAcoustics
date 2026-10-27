#ifndef ICS52000_H
#define ICS52000_H

#include <stdint.h>
#include <stdbool.h>
#include "random.h"

#include "arm_math.h"

#define ARRAY_COUNT(array) (sizeof(array) / sizeof((array)[0]))

#define local_persist static
#define internal static
#define global static

typedef float float32_t;
typedef uint32_t bool32;

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
    // TODO(sok): change to int16_t/uint16_t
    // when MDMA setup is completed
    // WARN: This motherfucker is interleaved
    float32_t pcm[ICS_AUDIO_SAMPLES][ICS_MIC_COUNT];
} AudioFrame;

typedef struct
{
    AudioFrame* frame;
    uint64_t seq;
} AudioViewFrame;

bool32 populate_frame(rng_t* r, AudioViewFrame* view, MicArray array, AngleDeg direction);

// TODO(sok): Startup of WS should be 300 ms!
//
#endif
