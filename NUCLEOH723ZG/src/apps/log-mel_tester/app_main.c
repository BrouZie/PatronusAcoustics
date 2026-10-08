#include "app_entry.h"
#include "audio_format.h"
#include "usart.h"
#include "console.h"
#include "mpu.h"
#include "audio_config.h"
#include "spectrum.h"
#include "log-mel_spectogram.h"

#include <string.h>
#include <stdbool.h>

#define RAM_BUF  ".d1_buf" // -> RAM_D1
#define DTCM_BUF ".dtcm_buf" // -> DTCMRAM

#define RAM_WORDS       1024
#define RAM_BLOCK_WORDS RAM_WORDS/2
#define RAM_SIZE        RAM_WORDS * sizeof(int32_t)

#define DTCM_WORDS RAM_WORDS * 2

#define LOGMEL_MAGIC              0x4C454D4C
#define LOGMEL_Q_SCALE            1.5f
#define LOGMEL_Q_OFFSET           -100.0f

typedef struct __attribute__((packed)) {
    uint32_t magic;       // LOGMEL_MAGIC
    uint32_t seq;         // increments every image; used to detect drops
} logmel_header_t;

static int32_t _rx_ram[RAM_WORDS] __attribute__((section(RAM_BUF), aligned(32)));
static audio_sample_t _rx_overlap[AUDIO_MIC_COUNT][DTCM_WORDS]  __attribute__((section(DTCM_BUF), aligned(4096)));

/* Header is only needed for the first frame; omit it from the ping-pong buffer. */
static uint8_t _logmel_first_frame[sizeof(logmel_header_t) + NUM_MEL_BANDS] __attribute__((section(DTCM_BUF), aligned(32)));
static uint8_t _logmel_frame[2][NUM_MEL_BANDS] __attribute__((section(DTCM_BUF), aligned(32)));
static uint8_t _logmel_spectogram[2][sizeof(logmel_header_t) + NUM_FRAMES * NUM_MEL_BANDS] __attribute__((section(RAM_BUF), aligned(32)));

static float32_t _logmel_frame_f32[NUM_MEL_BANDS]; // scratch: raw dB output of get_logmel_frame

static bool              _hist_primed = false;    // false until the first hop has been folded in
static volatile uint32_t _frame_start = 0;
static volatile bool     _frame_ready = false;    // false until the first hop has been folded in
static uint8_t           _active_write_buf  = 0;

void overlapping_data(uint32_t pos)
{
	const uint32_t mirror = (pos + RAM_WORDS) % (2 * RAM_WORDS);

	for (uint32_t i = 0; i < RAM_BLOCK_WORDS; i++)
	{
		audio_sample_t sample = (audio_sample_t)_rx_ram[pos + i] * AUDIO_SAMPLE_SCALE;
		_rx_overlap[0][pos + i] = sample;
		_rx_overlap[0][mirror + i] = sample;
	}
	_frame_start = (pos + RAM_BLOCK_WORDS) % RAM_WORDS;

	if (_hist_primed)
		_frame_ready = true;
	_hist_primed = true;      /* skip the first, half-empty frame */
}

static inline uint8_t quantize_db(float32_t db)
{
    float32_t byte_value = (db - LOGMEL_Q_OFFSET) * LOGMEL_Q_SCALE;
    if (byte_value < 0.0f) byte_value   = 0.0f;
    if (byte_value > 255.0f) byte_value = 255.0f;
    return (uint8_t)(byte_value + 0.5f);
}

void HAL_UART_RxHalfCpltCallback(UART_HandleTypeDef *huart3)
{
	if (huart3->Instance != USART3) return;
	overlapping_data(0); // First half of buffer filled up
}

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart3)
{
	if (huart3->Instance != USART3) return;
	overlapping_data(RAM_BLOCK_WORDS); // Second half of buffer filled up
}

void app_main()
{
	const float32_t (*spectrum)[SPECTRUM_FLOATS];
	UART_DMA_start((uint32_t)_logmel_spectogram, sizeof(_logmel_spectogram[0]));
	_mpu_configure((uint32_t*) _rx_ram, sizeof(_rx_ram));
	HAL_UART_Receive_DMA(&huart3, (uint8_t*)_rx_ram, sizeof(_rx_ram));
	spectrum_init();
	console_init();
	mel_filterbank_init();

	uint16_t frame_idx = 0;
	uint32_t seq       = 0;

	while(1)
	{
		if (_frame_ready)
		{
			_frame_ready = false;

			float32_t *frame[AUDIO_MIC_COUNT];
			for (uint32_t ch = 0; ch < AUDIO_MIC_COUNT; ++ch)
				frame[ch] = &_rx_overlap[ch][_frame_start];

			spectrum_compute(frame, &spectrum);
			get_logmel_frame(spectrum, _logmel_frame_f32);

	        uint8_t* out = _logmel_frame[_active_write_buf];
            uint8_t* cells;

			if (frame_idx == 0) {
				logmel_header_t* hdr = (logmel_header_t*)_logmel_first_frame;
				*hdr = (logmel_header_t){
					.magic = LOGMEL_MAGIC,
					.seq   = seq,
				};
				cells = _logmel_first_frame + sizeof(logmel_header_t);
				for (uint32_t b = 0; b < NUM_MEL_BANDS; b++)
					cells[b] = quantize_db(_logmel_frame_f32[b]);

				UART_MDMA_send_buffer(_logmel_first_frame, sizeof(logmel_header_t) + NUM_MEL_BANDS);
			} else {
				cells = out;
				for (uint32_t b = 0; b < NUM_MEL_BANDS; b++)
					cells[b] = quantize_db(_logmel_frame_f32[b]);

				UART_MDMA_send_buffer(cells, NUM_MEL_BANDS);
				_active_write_buf ^= 1U;
			}
			if (++frame_idx == NUM_FRAMES) { frame_idx = 0; seq++; }
		}

	}
}
