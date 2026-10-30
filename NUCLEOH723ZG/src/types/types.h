#ifndef TYPES_H
#define TYPES_H

#include "audio_config.h"
#include "arm_math.h"

#include <stdint.h>
#include <stdbool.h>

#define local_persist static
#define internal static
#define global static

typedef float float32_t;
typedef uint32_t bool32;
typedef int16_t sample_t;

#define ARRAY_COUNT(array) (sizeof(array) / sizeof((array)[0]))
#define SCALING_FACTOR(type) _Generic((type){0},            \
                                      int16_t:   INT16_MAX, \
                                      int32_t:   INT32_MAX, \
                                      float32_t: 1.0f)

typedef struct
{
    // WARN: This motherfucker is interleaved
    sample_t pcm[AUDIO_SAMPLES][MIC_COUNT];
} AudioFrame;

typedef struct
{
    AudioFrame* frame;
    uint32_t seq;
} AudioFrameView;

#endif // TYPES_H
