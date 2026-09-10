#include "app_entry.h"
#include "audio_config.h"
#include "console.h"
#include "ics52000.h"
#include "spectrum.h"

void app_main(void)
{
    // Array of pointers to audio frame
    float32_t* frame[AUDIO_MIC_COUNT];

    // Pointer to array containing spectrum samples
    const float32_t(*spectrum)[SPECTRUM_FLOATS];

    UART_DMA_start();
    spectrum_init();
    ics52000_start();

    while (1)
    {
        if (ics52000_read(frame))
        {
            spectrum_compute(frame, &spectrum);
            UART_MDMA_send_buffer((float32_t*)*spectrum, AUDIO_MIC_COUNT * SPECTRUM_FLOATS * sizeof(float32_t));
        }
    }
}
