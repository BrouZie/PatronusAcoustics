#include "app_entry.h"
#include "console.h"
#include "ics52000.h"
#include "audio_config.h"
#include "spectrum.h"

#include <stdint.h>
#include <stdio.h>

void app_main(void)
{
	const float32_t (*pcm)[512];
	float32_t (*spec)[514] = {};

	console_init();
	spectrum_init();
    ics52000_start();

	uint16_t hz;
	float32_t threshold = 0.5;

	while (1)
	{
		if (ics52000_read(&pcm))
		{
			spectrum_compute(pcm, spec);

			// Increment over all frequency bins, each bin contains a real and imaginary part
			for (uint16_t index = 0; index < AUDIO_SAMPLES_PER_BLOCK + 2; index += 2)
			{
				float32_t re = (*spec)[index];
				float32_t im = (*spec)[index + 1];
				float32_t magnitude = sqrtf(re * re + im * im);
				if (magnitude > threshold)
				{
					uint16_t bin = index / 2;
					hz = (uint16_t)((float32_t)bin * AUDIO_SAMPLE_RATE_HZ / (float32_t)AUDIO_SAMPLES_PER_BLOCK);
					printf("Magnitude:%.3f\r\n", magnitude);
					printf("Hz:%u\r\n", hz);
				}
			}
		}
	}
}		
