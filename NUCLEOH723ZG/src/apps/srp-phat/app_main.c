#include "app_entry.h"
#include "audio_config.h"
#include "console.h"
#include "ics52000.h"
#include "spectrum.h"
#include "srp-phat.h"

static doa_t doa;
static srp_t srp;

void app_main(void)
{
    // Array of pointers to audio frame
    float32_t* frame[AUDIO_MIC_COUNT];

    // Pointer to array containing spectrum samples
    const float32_t(*spectrum)[SPECTRUM_FLOATS];

    UART_DMA_start();
    spectrum_init();
    ics52000_start();

	volatile int w = 1; // not sure
    while (1)
    {
        if (ics52000_read(frame))
        {
			// Puts the shit into spectrum
            spectrum_compute(frame, &spectrum);

			doa = srp_compute(spectrum, &srp);
			if (!UART_tx_busy())
			{
				// Maybe send a header of some sorts eventually.
				UART_MDMA_send_buffer(&doa.azimuth, sizeof(doa.azimuth));
				w = w ^ 1;
			}
        }
    }
}
