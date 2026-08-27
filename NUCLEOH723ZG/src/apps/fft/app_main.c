#include "app_entry.h"
#include "arm_math_types.h"
#include "audio_config.h"
#include "audio_format.h"
#include "console.h"
#include "ics52000.h"

#include <math.h>
#include <stdint.h>
#include <stdio.h>

#define ICS_DTCM_FFT_BUF ".dtcm_fft_buf"
static audio_sample_t _block_fft_buf[AUDIO_SAMPLES_PER_BLOCK] __attribute__((section(ICS_DTCM_FFT_BUF)));

void app_main(void)
{
    // Prints out all frequencies and corresponding magnitudes over a chosen threshold
    arm_rfft_fast_instance_f32 _fft_handler;

    const float32_t(*pcm)[AUDIO_SAMPLES_PER_BLOCK];
    audio_format_t fmt = ics52000_format();

    console_init(); // For printing to the serial console
    ics52000_start();
    arm_rfft_fast_init_f32(&_fft_handler, AUDIO_SAMPLES_PER_BLOCK);

    uint16_t  _hz;
    float32_t _threshold = 0.5f;

    while (1)
    {
        if (ics52000_read(&pcm))
        {
            for (uint32_t i = 0; i < fmt.mic_count; i++)
            {
                arm_rfft_fast_f32(&_fft_handler, (float32_t*)pcm[i], _block_fft_buf, 0);
                _hz = 0;

                // Increment over all frequency bins, each bin contains a real and imaginary part
                for (uint16_t index = 2; index < AUDIO_SAMPLES_PER_BLOCK; index += 2)
                {
                    float32_t _re        = _block_fft_buf[index];
                    float32_t _im        = _block_fft_buf[index + 1];
                    float32_t _magnitude = sqrtf(_re * _re + _im * _im);
                    if (_magnitude > _threshold)
                    {
                        uint16_t _bin = index / 2;
                        _hz = (uint16_t)((float32_t)_bin * AUDIO_SAMPLE_RATE_HZ / (float32_t)AUDIO_SAMPLES_PER_BLOCK);
                        printf("Magnitude:%.3f\r\n", _magnitude);
                        printf("Hz:%u\r\n", _hz);
                    }
                }
            }
        }
    }
}
