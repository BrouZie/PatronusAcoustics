#ifndef LOG_MEL_SPECTOGRAM
#define LOG_MEL_SPECTOGRAM

#include "arm_math_types.h"
#include "audio_config.h"

void mel_filterbank_init(void);
void get_magnitudes(float32_t (**spec)[SPECTRUM_FLOATS]);

#endif
