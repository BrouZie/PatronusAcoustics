#include "app_entry.h"
#include "arm_math_types.h"
#include "audio_format.h"
#include "console.h"
#include "dsp/transform_functions.h"
#include "ics52000fft.h"
#include "audio_config.h"

#include <math.h>
#include <stdint.h>
#include <stdio.h>

#define ICS_DTCM_FFT_BUF ".dtcm_fft_buf"
static audio_sample_t _block_fft_buf[AUDIO_BLOCK_SAMPLES] __attribute__((section(ICS_DTCM_FFT_BUF)));
void app_main(void)
{
	arm_rfft_fast_instance_f32 _fft_handler;

	const audio_sample_t* data;
    audio_format_t fmt = ics52000_format();

    console_init();
    ics52000_start_fft();
	arm_rfft_fast_init_f32(&_fft_handler, FFT_BUFFER_SIZE);

	float32_t peak_val = 0.0f;
	uint16_t peak_hz = 0;
	
	while (1)
	{
		if (ics52000_read_fft(&data))
		{
			for (uint32_t i = 0; i < fmt.mic_count; i++)
			{
				arm_rfft_fast_f32(&_fft_handler, (float32_t*)data, _block_fft_buf, 0);
				peak_val = fabsf(_block_fft_buf[0]);
				peak_hz = 0;

				for (uint16_t index = 2; index < FFT_BUFFER_SIZE; index += 2)
				{
					float32_t _re = _block_fft_buf[index];
					float32_t _im = _block_fft_buf[index + 1];
					float32_t cur_val = sqrtf(_re * _re + _im * _im);
					if (cur_val > peak_val)	
					{
						peak_val = cur_val;
						uint16_t bin = index / 2;
						peak_hz = (uint16_t)((float32_t)bin * AUDIO_SAMPLE_RATE_HZ / (float32_t)FFT_BUFFER_SIZE);
					}
				}
				printf("Peak val:%.3f\r\n", peak_val);
				printf("Peak hz:%u\r\n", peak_hz);
			}
		}

	}
}		
