#ifndef AUDIO_FORMAT_H
#define AUDIO_FORMAT_H

// ============================================================================
// The capture stage's runtime contract, published by the driver and consumed
// by everything downstream (DSP, transport, etc.).
//
// LEAF HEADER: No HAL, no function declarations, no module
// headers - that is what keeps it safe for every module to depend on.
// ============================================================================

#include <stdint.h>
#include "arm_math.h"

typedef float32_t audio_sample_t;

typedef struct
{
    uint32_t       samples_per_block; // per microphone
    uint32_t       mic_count;
    uint32_t       sample_rate_hz;
    uint32_t       sample_bits;
    audio_sample_t full_scale;        // magnitude of 0 dBFS
} audio_format_t;

#endif
