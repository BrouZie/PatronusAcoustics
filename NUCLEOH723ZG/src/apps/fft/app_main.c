#include "app_entry.h"
#include "audio_config.h"
#include "console.h"
#include "ics52000.h"
#include "spectrum.h"

static float32_t spec[AUDIO_MIC_COUNT][SPECTRUM_FLOATS];

void app_main(void)
{
// <<<<<<< HEAD
	float32_t* frame[AUDIO_MIC_COUNT];
// 	float32_t spec[AUDIO_MIC_COUNT][SPECTRUM_FLOATS];
// =======
//     const float32_t(*pcm)[AUDIO_SAMPLES_PER_BLOCK];
// >>>>>>> 76104a8 (Improved variable naming in spectrum + srp-phat module start)

    UART_DMA_start();
    spectrum_init();
    ics52000_start();

// <<<<<<< HEAD
// 	uint16_t hz;
// 	float32_t threshold = 0.5;
//
// 	while (1)
// 	{
// 		if (ics52000_read(frame))
// 		{
// 			spectrum_compute(frame, spec);
//
// 			// Increment over all frequency bins, each bin contains a real and imaginary part
// 			for (uint16_t index = 0; index < FFT_BUFFER_SIZE + 2; index += 2)
// 			{
// 				float32_t re = (*spec)[index];
// 				float32_t im = (*spec)[index + 1];
// 				float32_t magnitude = sqrtf(re * re + im * im);
// 				if (magnitude > threshold)
// 				{
// 					uint16_t bin = index / 2;
// 					hz = (uint16_t)((float32_t)bin * AUDIO_SAMPLE_RATE_HZ / (float32_t)FFT_BUFFER_SIZE);
// 					printf("Magnitude:%.3f\r\n", magnitude);
// 					printf("Hz:%u\r\n", hz);
// 				}
// 			}
// 		}
// 	}
// =======
    while (1)
    {
        if (ics52000_read(frame))
        {
            spectrum_compute(frame, spec);
			UART_MDMA_send_buffer(&spec[0][0]);
        }
    }
// >>>>>>> 76104a8 (Improved variable naming in spectrum + srp-phat module start)
}
