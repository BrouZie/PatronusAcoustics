#ifndef SPECTRUM_H
#define SPECTRUM_H

#include "arm_math.h"
#include "audio_config.h"

void spectrum_init(void);
void spectrum_compute(float32_t* const frame[AUDIO_MIC_COUNT], float32_t(**spec)[SPECTRUM_FLOATS]);

#endif
