#include "app_entry.h"
#include "audio_config.h"
#include "console.h"
#include "spectrum.h"
#include "log-mel_spectogram.h"

typedef struct __attribute__((packed)) {
    uint32_t magic;       // LOGMEL_MAGIC
    uint32_t seq;         // increments every image; used to detect drops
} logmel_header_t;


#define LOGMEL_FRAME_DTCM_BUF     ".dtcm_buf" // -> DTCMRAM
#define LOGMEL_SPECTOGRAM_RAM_BUF ".d1_buf"   // -> RAM_D1
#define LOGMEL_MAGIC              0x4C454D4C
#define LOGMEL_Q_SCALE            1.5f
#define LOGMEL_Q_OFFSET           -100.0f

#define ICS_RAM_BUF ".d1_buf"    // -> RAM_D1
#define ICS_DTCM_BUF ".dtcm_buf" // -> DTCMRAM

static audio_sample_t _rx_ram[ICS_DMA_WORDS] __attribute__((section(ICS_RAM_BUF), aligned(32)));
static audio_sample_t _rx_hist[AUDIO_MIC_COUNT][2 * ICS_FRAME_SAMPLES] __attribute__((section(ICS_DTCM_BUF), aligned(32)));

static uint32_t          _hist_pos;       // multiple of ICS_HOP_SAMPLES, in [0, 2*ICS_FRAME_SAMPLES)
static bool              _hist_primed;    // false until the first hop has been folded in

/* Maps a float32 dB value to the 0–255 uint8_t range, with rounding and clamping, to reduce memory usage. */
static inline uint8_t quantize_db(float32_t db)
{
	float32_t byte_value = (db - LOGMEL_Q_OFFSET) * LOGMEL_Q_SCALE;
	if (byte_value < 0.0f) byte_value   = 0.0f;
	if (byte_value > 255.0f) byte_value = 255.0f;
	return (uint8_t)(byte_value + 0.5f);
}

// Receive data over UART
static volatile uint8_t _rx_done;

static void _rx_dma_done(DMA_HandleTypeDef* hdma)
{
    (void)hdma;
    huart3.Instance->CR3 &= ~USART_CR3_DMAR;   // stop UART requesting DMA
    _rx_done = 1;
}

void peripheral_input(void)
{
    _rx_done = 0;
    __HAL_UART_CLEAR_OREFLAG(&huart3);
    (void)huart3.Instance->RDR;

    hdma_usart3_rx.XferCpltCallback = _rx_dma_done;
    HAL_DMA_Start_IT(&hdma_usart3_rx,
                     (uint32_t)&huart3.Instance->RDR,
                     (uint32_t)&_rx_hist[_hist_pos],
                     HOP_BYTES);
    huart3.Instance->CR3 |= USART_CR3_DMAR;   // enable after DMA is armed
}

static void _extract_channel(const int32_t* src, uint32_t ch, uint32_t pos, uint32_t mirror)
{
	for (uint32_t n = 0; n < ICS_HOP_SAMPLES; ++n)
	{
		audio_sample_t sample = (audio_sample_t)src[n * AUDIO_MIC_COUNT + ch] * AUDIO_SAMPLE_SCALE;
		_pcm_hist[ch][pos + n] = sample;
		_pcm_hist[ch][mirror + n] = sample;

	}
}

bool peripheral_history(float32_t* frame[AUDIO_MIC_COUNT])
{
	const uint32_t mirror = (_hist_pos + ICS_FRAME_SAMPLES) % (2 * ICS_FRAME_SAMPLES);
    for (uint32_t ch = 0; ch < AUDIO_MIC_COUNT; ++ch)
        _extract_channel(_rx_ram, ch, _hist_pos, mirror);

	_hist_pos = (_hist_pos + ICS_HOP_SAMPLES) % (2 * ICS_FRAME_SAMPLES);
	if (!_hist_primed)
	{
	 	_hist_primed = true;
		return false;
	}

	/* Pointer to the first sample of the frame*/
	const uint32_t frame_start = _hist_pos % ICS_FRAME_SAMPLES;
	for (uint32_t ch = 0; ch < AUDIO_MIC_COUNT; ++ch)
		frame[ch] = &_pcm_hist[ch][frame_start];

	return true
}

void app_main(void)
{
	// Pointer to array containing spectrum samples
	const float32_t (*spectrum)[SPECTRUM_FLOATS];
	UART_DMA_start((uint32_t)_logmel_spectogram, sizeof(_logmel_spectogram[0]));
    spectrum_init();
	mel_filterbank_init();

	uint16_t frame_idx = 0;
	uint32_t seq       = 0;

	while(1)
	{
		if (peripheral_history)
		{
            spectrum_compute(frame, &spectrum);
			get_logmel_frame(spectrum, _logmel_frame_f32);
	        uint8_t* out = _logmel_frame[_active_write_buf];
            uint8_t* cells;

		}
	}
}

