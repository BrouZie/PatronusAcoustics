#include "app_entry.h"
#include "audio_config.h"
#include "console.h"
#include "ics52000.h"
#include "spectrum.h"

static float32_t spec[AUDIO_MIC_COUNT][SPECTRUM_FLOATS];

void app_main(void)
{
    const float32_t(*pcm)[AUDIO_SAMPLES_PER_BLOCK];

    UART_DMA_start();
    spectrum_init();
    ics52000_start();

    while (1)
    {
        if (ics52000_read(&pcm))
        {
            spectrum_compute(pcm, spec);
			UART_MDMA_send_buffer(&spec[0][0]);
        }
    }
}
