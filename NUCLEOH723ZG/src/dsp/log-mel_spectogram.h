#ifndef LOG_MEL_SPECTOGRAM
#define LOG_MEL_SPECTOGRAM

#include "arm_math.h"
#include "audio_config.h"

/*
 * Sound window 1-4 seconds common for CNN drone detection
 * Shorter window gives fast response, well suited for close range loud drones
 * Longer window gives slower response, well suited for longer range, quieter drones
 *
 * NUM_FRAMES calculated from (sampling_rate / hop_length) * seconds
 * Hop_length given by number of new samples introduced between one window and the next
*/

#define NUM_FRAMES    94
#define NUM_MEL_BANDS 64     

void mel_filterbank_init(void);
void get_logmel_frame(const float32_t (*spec)[SPECTRUM_FLOATS], float32_t* mel_out);


#endif
