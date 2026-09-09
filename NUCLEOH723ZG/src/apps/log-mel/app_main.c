#include "app_entry.h"
#include "arm_math_types.h"
#include "audio_config.h"
#include "console.h"
#include "ics52000.h"
#include "spectrum.h"
#include "log-mel_spectogram.h"

#define ICS_RAM_BUF ".d1_buf" // -> RAM_D1

static bool      _spectogram_full   = false;
static uint16_t  _current_frame_idx = 0;
static uint8_t   _active_write_buf  = 0;
// Currently spectogram takes way to much space for RAM_D2
static float32_t _logmel_spectogram[2][NUM_FRAMES][NUM_MEL_BANDS] __attribute__((section(ICS_RAM_BUF), aligned(32)));

void app_main(void)
{
	// Array of pointers to audio frame
	float32_t* frame[AUDIO_MIC_COUNT];

	// Pointer to array containing spectrum samples
	const float32_t (*spectrum)[SPECTRUM_FLOATS];

    UART_DMA_start();
    spectrum_init();
	mel_filterbank_init();
    ics52000_start();

    while (1)
    {
        if (ics52000_read(frame))
        {
            spectrum_compute(frame, &spectrum);
			get_logmel_frame(spectrum, _logmel_spectogram[_active_write_buf][_current_frame_idx]);	
			_current_frame_idx++;

			if (_current_frame_idx >= NUM_FRAMES)
			{
				_spectogram_full = true;
			}
			if (_spectogram_full)
			{
				UART_MDMA_send_buffer((float32_t*)_logmel_spectogram[_active_write_buf], 
									  NUM_FRAMES * NUM_MEL_BANDS * sizeof(float32_t));
									  _active_write_buf = 1U - _active_write_buf;
									  _current_frame_idx = 0;
									  _spectogram_full = false;
			}
        }
    }
}
