#ifndef SPECTRUM_H
#define SPECTRUM_H

#include "arm_math.h"
#include "audio_config.h"

void spectrum_init(void);
void spectrum_compute(const float32_t (*pcm)[AUDIO_SAMPLES_PER_BLOCK], float32_t (*spec)[SPECTRUM_FLOATS]);

#endif
