#include "ics52000fft.h"

#include "arm_math_types.h"
#include "audio_config.h"
#include "main.h"
#include "sai.h"
#include <tim.h>

#include "console.h"
#include <stdio.h>

/* --------- HARDWARE & LINKER BINDINGS ---------*/
#define ICS_SAI_HANDLE_1 hsai_BlockA1
#define ICS_RAM_BUF ".raw_buf"
#define ICS_DTCM_RAW_BUF ".dtcm_raw_buf"
#define ICS_DTCM_WINDOWED_BUF ".dtcm_windowed_buf"

// TDM frames are padded to the next supported slot count.
#define ICS_SLOT_COUNT (AUDIO_MIC_COUNT <= 2 ? 2 : AUDIO_MIC_COUNT <= 4 ? 4 : 8)

// Ping-pong: the DMA buffer holds two blocks, halves signalled separately.
#define ICS_DMA_WORDS (AUDIO_BLOCK_SAMPLES * 2)

// The only place a HAL constant is tied to the configured sample depth.
#if AUDIO_SAMPLE_BITS == 32
#define ICS_SAI_DATASIZE SAI_DATASIZE_32
#else
#error "No SAI_DATASIZE_* mapping for this AUDIO_SAMPLE_BITS"
#endif

/* --------- AUDIO BUFFERS ---------*/
static uint32_t _dma_buf[ICS_DMA_WORDS] __attribute__((section(ICS_RAM_BUF), aligned(32)));
static audio_sample_t _block_raw_buf[AUDIO_BLOCK_SAMPLES] __attribute__((section(ICS_DTCM_RAW_BUF)));
static audio_sample_t _block_windowed_buf[AUDIO_BLOCK_SAMPLES] __attribute__((section(ICS_DTCM_WINDOWED_BUF)));

/* --------- Stats structs ---------*/
static ics_stats_t _stats; // surfaced through func ics52000_stats(ics_stats_t)

/* --------- Callback/ISR variables ---------*/
static volatile uint32_t _chunks_produced; // ISR increments
static uint32_t _chunks_consumed;          // buffer halfs read by CPU
																					 
/* --------- Hann window variable ---------*/
static float32_t hann_win[FFT_BUFFER_SIZE];

/* --------- Callback functions ---------*/

// SAI1_Block_A:
void HAL_SAI_RxHalfCpltCallback(SAI_HandleTypeDef* hsai)
{
    if (hsai->Instance != SAI1_Block_A)
        return;
    ++_chunks_produced;
}

void HAL_SAI_RxCpltCallback(SAI_HandleTypeDef* hsai)
{
    if (hsai->Instance != SAI1_Block_A)
        return;

    HAL_GPIO_TogglePin(GPIOB, GPIO_PIN_14);
    ++_chunks_produced;
}

void HAL_SAI_ErrorCallback(SAI_HandleTypeDef* hsai)
{
    if (hsai->Instance != SAI1_Block_A)
        return;
    _stats.bus_errors++;
    _stats.last_hal_err = hsai->ErrorCode;
}

/* --------- Callback functions ---------*/

static inline uint8_t _mpu_size(uint32_t bytes)
{
    uint32_t size = 32;

    while (size < bytes)
    {
        size <<= 1;
    }

    return (uint8_t)(__builtin_ctz(size) - 1);
}

void _MPU_resize(void)
{
    HAL_MPU_Disable();
    MPU_Region_InitTypeDef MPU_InitStruct = { 0 };

    MPU_InitStruct.Enable           = MPU_REGION_ENABLE;
    MPU_InitStruct.Number           = MPU_REGION_NUMBER0;
    MPU_InitStruct.BaseAddress      = 0x24000000;
    MPU_InitStruct.Size             = _mpu_size(ICS_DMA_WORDS * sizeof(uint32_t));
    MPU_InitStruct.SubRegionDisable = 0x0;
    MPU_InitStruct.TypeExtField     = MPU_TEX_LEVEL0;
    MPU_InitStruct.AccessPermission = MPU_REGION_FULL_ACCESS;
    MPU_InitStruct.DisableExec      = MPU_INSTRUCTION_ACCESS_ENABLE;
    MPU_InitStruct.IsShareable      = MPU_ACCESS_SHAREABLE;
    MPU_InitStruct.IsCacheable      = MPU_ACCESS_NOT_CACHEABLE;
    MPU_InitStruct.IsBufferable     = MPU_ACCESS_BUFFERABLE;

    HAL_MPU_ConfigRegion(&MPU_InitStruct);
    HAL_MPU_Enable(MPU_HFNMI_PRIVDEF);
}

/* --------- Hann windowing ---------*/
// Need to apply a Hann window for the Fast Fourier Transform
// An FFT assumes audio blocks repeats perfectly, this is almost always not the case
// The edges of the signal fades the tones at the edges reducing FFT spectral leakage

void init_hann_window(void)
{
		for (int i = 0; i < FFT_BUFFER_SIZE; i++) {
			hann_win[i] = 0.5f * (1.0f - cosf(2.0f * PI * (float32_t)i / (float32_t)(FFT_BUFFER_SIZE - 1)));
		}
}

void apply_hann_window(const float32_t *signal_in, float32_t *output_out)
{
    arm_mult_f32((float32_t *)signal_in, hann_win, output_out, FFT_BUFFER_SIZE);
}

/* --------- Hann windowing ---------*/

void _disable_fs_SAI(void)
{
    GPIO_InitTypeDef g = { 0 };

    // PE4 as GPIO low: SCK runs, WS held quiet
    g.Pin   = GPIO_PIN_4;
    g.Mode  = GPIO_MODE_OUTPUT_PP;
    g.Pull  = GPIO_NOPULL;
    g.Speed = GPIO_SPEED_FREQ_VERY_HIGH;
    HAL_GPIO_Init(GPIOE, &g);
}

void _enable_fs_SAI(void)
{
    GPIO_InitTypeDef g = { 0 };

    // Now hand PE4 to the SAI
    g.Pin       = GPIO_PIN_4;
    g.Mode      = GPIO_MODE_AF_PP;
    g.Pull      = GPIO_NOPULL;
    g.Speed     = GPIO_SPEED_FREQ_VERY_HIGH;
    g.Alternate = GPIO_AF6_SAI1;
    HAL_GPIO_Init(GPIOE, &g);
}

// Timer callback
void HAL_TIM_PeriodElapsedCallback(TIM_HandleTypeDef* htim)
{
    if (htim->Instance == TIM7)
    {
        _enable_fs_SAI();
        HAL_TIM_Base_Stop_IT(&htim7);
        __HAL_TIM_SET_AUTORELOAD(&htim7, 99);
        __HAL_TIM_SET_COUNTER(&htim7, 0);
        HAL_TIM_Base_Start_IT(&htim7);
    }
}

// Not confident this works at all
static void _ics_dma_start_fft(void)
{
    _disable_fs_SAI();
    __HAL_SAI_ENABLE(&ICS_SAI_HANDLE_1);

    HAL_TIM_Base_Start_IT(&htim7);

    if (HAL_SAI_Receive_DMA(&ICS_SAI_HANDLE_1, (uint8_t*)_dma_buf, ICS_DMA_WORDS) != HAL_OK)
        Error_Handler();
}

void ics52000_start_fft(void)
{   init_hann_window(); 
    _MPU_resize();

    HAL_SAI_DeInit(&ICS_SAI_HANDLE_1);

    /* Whatever the .ioc last generated into Core/Src/sai.c is
     * overwritten here, so audio_config.h stays the single
     * source of truth across a CubeMX regeneration. */
    ICS_SAI_HANDLE_1.Init.AudioFrequency   = AUDIO_SAMPLE_RATE_HZ;
    ICS_SAI_HANDLE_1.Init.DataSize         = ICS_SAI_DATASIZE;
    ICS_SAI_HANDLE_1.FrameInit.FrameLength = ICS_SLOT_COUNT * 32;
    ICS_SAI_HANDLE_1.SlotInit.SlotNumber   = ICS_SLOT_COUNT;
    ICS_SAI_HANDLE_1.SlotInit.SlotActive   = (1u << AUDIO_MIC_COUNT) - 1u;

    if (HAL_SAI_Init(&ICS_SAI_HANDLE_1) != HAL_OK)
        Error_Handler();

    _chunks_produced = 0;
    _chunks_consumed = 0;

    _ics_dma_start_fft();
}

void ics52000_stop_fft(void)
{
    HAL_SAI_DMAStop(&ICS_SAI_HANDLE_1);
    _chunks_produced = 0;
    _chunks_consumed = 0;
}

bool ics52000_read_fft(const audio_sample_t** data)
{
	// console_init();
    uint32_t p0 = _chunks_produced;
    if (_chunks_consumed == p0)
        return false;

    if (p0 - _chunks_consumed > 1)
        _stats.dropped += p0 - _chunks_consumed - 1;

    uint32_t* src = &_dma_buf[((p0 - 1) % 2) * (ICS_DMA_WORDS / 2)];
    for (int i = 0; i < AUDIO_BLOCK_SAMPLES; ++i)
	{
		// _block_raw_buf[i] = (float32_t)(int32_t)src[i] / AUDIO_FULL_SCALE;
		_block_raw_buf[i] = (float32_t)(int32_t)src[i] / 2147483648.0f;
	}
	// Used to remove DC bias 
	float32_t mean;
	arm_mean_f32(_block_raw_buf, AUDIO_BLOCK_SAMPLES, &mean);
	for (int i = 0; i < AUDIO_BLOCK_SAMPLES; ++i)
		_block_raw_buf[i] -= mean;

	apply_hann_window((float32_t*) _block_raw_buf, (float32_t*) _block_windowed_buf);

    uint32_t p1 = _chunks_produced;

    _chunks_consumed = p1;

    if (p1 - p0 >= 2) // ping-pong: chunk N and N+2 share memory
    {
        ++_stats.lapped;
        return false;
    }

    _stats.chunks++;
    // *data = _block_raw_buf;
    *data = _block_windowed_buf;

    return true;
}

audio_format_t ics52000_format(void)
{
    return (audio_format_t) {
        .samples_per_block = AUDIO_SAMPLES_PER_BLOCK,
        .mic_count         = AUDIO_MIC_COUNT,
        .sample_rate_hz    = AUDIO_SAMPLE_RATE_HZ,
        .sample_bits       = AUDIO_SAMPLE_BITS,
        .full_scale        = AUDIO_FULL_SCALE,
    };
}

ics_stats_t* ics52000_stats(void)
{
    return &_stats;
}
