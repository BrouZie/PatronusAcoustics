#include "app_entry.h"
#include "arm_math.h"
#include "audio_config.h"
#include "console.h"
#include "ics52000.h"
#include "spectrum.h"
#include "log-mel_spectogram.h"
#include <stdint.h>

#define LOGMEL_FRAME_DTCM_BUF ".dtcm_buf" // -> DTCMRAM
#define LOGMEL_SPECTOGRAM_RAM_BUF ".d1_buf" // -> RAM_D1
#define LOGMEL_MAGIC 0x4C454D4C
#define LOGMEL_Q_SCALE   2.83f     // ~0.35 dB/step over ~90 dB range — tune to your data
#define LOGMEL_Q_OFFSET  -80.0f    // dB value that maps to byte 0
#define LOGMEL_FRAME_BUF_SIZE (sizeof(logmel_header_t) + NUM_MEL_BANDS)

typedef struct __attribute__((packed)) {
    uint32_t magic;       // must be LOGMEL_MAGIC
    uint32_t seq;         // increments every image; used to detect drops
} logmel_header_t;

static uint8_t  _active_write_buf  = 0;
static uint8_t _logmel_frame[2][LOGMEL_FRAME_BUF_SIZE] __attribute__((section(LOGMEL_FRAME_DTCM_BUF), aligned(32))); // Waste memory in DTCM for header, when it is only used for first frame, fix if constrained
static uint8_t _logmel_spectogram[2][sizeof(logmel_header_t) + NUM_FRAMES * NUM_MEL_BANDS] __attribute__((section(LOGMEL_SPECTOGRAM_RAM_BUF), aligned(32)));

static float32_t _logmel_frame_f32[NUM_MEL_BANDS]; // scratch: raw dB output of get_logmel_frame

/* Converts from float32 to uint_8 */
static inline uint8_t quantize_db(float32_t db)
{
    float32_t byte_value = (db - LOGMEL_Q_OFFSET) * LOGMEL_Q_SCALE;
    if (byte_value < 0.0f) byte_value   = 0.0f;
    if (byte_value > 255.0f) byte_value = 255.0f;
    return (uint8_t)(byte_value + 0.5f);
}

void app_main(void)
{
	// Array of pointers to audio frame
	float32_t* frame[AUDIO_MIC_COUNT];

	// Pointer to array containing spectrum samples
	const float32_t (*spectrum)[SPECTRUM_FLOATS];
	UART_DMA_start((uint32_t)_logmel_spectogram, sizeof(_logmel_spectogram[0]));
    spectrum_init();
	mel_filterbank_init();
    ics52000_start();

    uint16_t frame_idx = 0;
    uint32_t seq       = 0;

    while (1)
    {
        if (ics52000_read(frame))
        {
            spectrum_compute(frame, &spectrum);
			get_logmel_frame(spectrum, _logmel_frame_f32);

	        uint8_t* out = _logmel_frame[_active_write_buf];
            uint32_t send_size;
            uint8_t* cells;

            if (frame_idx == 0) {
                logmel_header_t* hdr = (logmel_header_t*)out;
                *hdr = (logmel_header_t){
                    .magic    = LOGMEL_MAGIC,
                    .seq      = seq,
                };
                cells     = out + sizeof(logmel_header_t);
                send_size = sizeof(logmel_header_t) + NUM_MEL_BANDS;
            } else {
                cells     = out;
                send_size = NUM_MEL_BANDS;
            }


			for (uint32_t b = 0; b < NUM_MEL_BANDS; b++)
						cells[b] = quantize_db(_logmel_frame_f32[b]);

			UART_MDMA_send_buffer(out, send_size);

			_active_write_buf ^= 1U;
			if (++frame_idx == NUM_FRAMES) { frame_idx = 0; seq++; }
		}
	}
}

