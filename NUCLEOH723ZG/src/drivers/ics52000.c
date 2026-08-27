#include "ics52000.h"

#include "arm_math_types.h"
#include "audio_config.h"
#include "audio_format.h"
#include "mpu.h"
#include "main.h"
#include "mdma.h"
#include "sai.h"
#include "tim.h"

/*
 * Capture path
 * ------------
 * SAI1_A --DMA2--> _d1_capture (RAM_D1, circular, MPU non-cacheable)
 *                      |
 *                      | MDMA, one half per transfer, SW triggered
 *                      v
 *                  _dtcm_block (DTCM, ping-pong)
 *                      |
 *                      | CPU: de-interleave + window + int->float
 *                      v
 *                   caller
 *
 * The CPU never touches _d1_capture. No cache maintenance is needed anywhere:
 * the source is non-cacheable by MPU, the destination is DTCM (never cached).
 *
 * Samples arrive left-justified in a 32-bit slot, so the raw word reinterpreted
 * as int32_t is already a valid Q31 sample. No shifting, ever.
 */

/* --------- HARDWARE & LINKER BINDINGS --------- */

#define ICS_SAI_HANDLE_1 hsai_BlockA1
#define ICS_MDMA_HANDLE hmdma_mdma_channel0_sw_0
#define ICS_RAM_BUF ".d1_buf"    // -> RAM_D1
#define ICS_DTCM_BUF ".dtcm_buf" // -> DTCMRAM

// TDM frames are padded to the next supported slot count.
#define ICS_SLOT_COUNT (AUDIO_MIC_COUNT <= 2 ? 2 : AUDIO_MIC_COUNT <= 4 ? 4 : 8)

// Ping-pong: the DMA buffer holds two blocks, halves signalled separately. */
#define ICS_DMA_WORDS (AUDIO_BLOCK_SAMPLES * 2)
#define ICS_BLOCK_BYTES (AUDIO_BLOCK_SAMPLES * sizeof(int32_t))

// The only place a HAL constant is tied to the configured sample depth. */
#if AUDIO_SAMPLE_BITS == 32
#define ICS_SAI_DATASIZE SAI_DATASIZE_32
#else
#error "No SAI_DATASIZE_* mapping for this AUDIO_SAMPLE_BITS"
#endif

/* Datasheet: valid data only after 262144 SCK. At 12.288 MHz that is 21.3 ms,
 * so TIM7 (1 kHz tick) holds WS low for 30 ms before handing PE4 to the SAI. */
#define ICS_WS_HOLD_MS 30

/* --------- AUDIO BUFFERS --------- */

// Written by the SAI DMA only
static uint32_t _d1_capture[ICS_DMA_WORDS] __attribute__((section(ICS_RAM_BUF), aligned(32)));

// Written by MDMA, read by the CPU. Interleaved Q31, [mic0 mic1 .. micN] per frame
static int32_t _dtcm_block[2][AUDIO_BLOCK_SAMPLES]
    __attribute__((section(ICS_DTCM_BUF), aligned(32)));

/* De-interleaved, normalized to [-1, 1). One row per mic.
 * Valid until the next ics52000_read(). */
static audio_sample_t _pcm[AUDIO_MIC_COUNT][AUDIO_SAMPLES_PER_BLOCK]
    __attribute__((section(ICS_DTCM_BUF), aligned(32)));

/* --------- STATE --------- */

static volatile ics_stats_t _stats; // written from ISRs, read from main

static volatile uint32_t _blocks_sent;    // halves handed to the MDMA
static volatile uint32_t _blocks_landed;  // halves landed in _raw_block
static volatile uint32_t _half_in_flight; // which half is in flight
static volatile uint32_t _half_landed;    // which half last landed
static uint32_t _blocks_taken;            // main context only

/* --------- MDMA --------- */

static void _mdma_cplt(MDMA_HandleTypeDef* hmdma)
{
    (void)hmdma;
    _half_landed = _half_in_flight;
    ++_blocks_landed;
}

static void _mdma_error(MDMA_HandleTypeDef* hmdma)
{
    _stats.mdma_errors++;
    _stats.last_hal_err = hmdma->ErrorCode;
}

/* Move one half of _dma_buf into the matching _raw_block. On HAL_BUSY the
 * transfer never starts, so _chunks_kicked must not advance either -- that is
 * what keeps _kicked_half and _ready_half in agreement. */
static void _mdma_kick(uint32_t half)
{
    if (HAL_MDMA_Start_IT(&ICS_MDMA_HANDLE, (uint32_t)&_d1_capture[half * AUDIO_BLOCK_SAMPLES],
                          (uint32_t)_dtcm_block[half], ICS_BLOCK_BYTES, 1) != HAL_OK)
    {
        _stats.mdma_busy++;
        return;
    }

    _half_in_flight = half;
    ++_blocks_sent;
}

// The source is AXI SRAM and the destination is DTCM via the AHBS port
static void _mdma_configure(void)
{
    ICS_MDMA_HANDLE.Init.SourceBurst = MDMA_SOURCE_BURST_16BEATS;
    ICS_MDMA_HANDLE.Init.DestBurst   = MDMA_DEST_BURST_SINGLE;
    ICS_MDMA_HANDLE.Init.Priority    = MDMA_PRIORITY_HIGH;

    if (HAL_MDMA_Init(&ICS_MDMA_HANDLE) != HAL_OK)
        Error_Handler();

    ICS_MDMA_HANDLE.XferCpltCallback  = _mdma_cplt;
    ICS_MDMA_HANDLE.XferErrorCallback = _mdma_error;
}

/* --------- SAI CALLBACKS --------- */

void HAL_SAI_RxHalfCpltCallback(SAI_HandleTypeDef* hsai)
{
    if (hsai->Instance == SAI1_Block_A)
        _mdma_kick(0);
}

void HAL_SAI_RxCpltCallback(SAI_HandleTypeDef* hsai)
{
    if (hsai->Instance == SAI1_Block_A)
        _mdma_kick(1);
}

void HAL_SAI_ErrorCallback(SAI_HandleTypeDef* hsai)
{
    if (hsai->Instance != SAI1_Block_A)
        return;

    _stats.bus_errors++;
    _stats.last_hal_err = hsai->ErrorCode;
}

/* --------- STARTUP SEQUENCE --------- */

/* The ICS-52000 assigns itself a TDM slot by counting SCK edges while WS is
 * held low, so PE4 starts as a GPIO and only becomes the SAI frame-sync pin
 * once the microphones have finished enumerating. */

static void _ws_pin_as_gpio(void)
{
    GPIO_InitTypeDef g = { 0 };

    g.Pin   = GPIO_PIN_4;
    g.Mode  = GPIO_MODE_OUTPUT_PP;
    g.Pull  = GPIO_NOPULL;
    g.Speed = GPIO_SPEED_FREQ_VERY_HIGH;

    HAL_GPIO_Init(GPIOE, &g);
    HAL_GPIO_WritePin(GPIOE, GPIO_PIN_4, GPIO_PIN_RESET);
}

static void _ws_pin_as_sai(void)
{
    GPIO_InitTypeDef g = { 0 };

    g.Pin       = GPIO_PIN_4;
    g.Mode      = GPIO_MODE_AF_PP;
    g.Pull      = GPIO_NOPULL;
    g.Speed     = GPIO_SPEED_FREQ_VERY_HIGH;
    g.Alternate = GPIO_AF6_SAI1;

    HAL_GPIO_Init(GPIOE, &g);
}

void HAL_TIM_PeriodElapsedCallback(TIM_HandleTypeDef* htim)
{
    if (htim->Instance != TIM7)
        return;

    HAL_TIM_Base_Stop_IT(&htim7);
    _ws_pin_as_sai();
}

/* --------- PUBLIC API --------- */

void ics52000_start(void)
{
    _mpu_configure(_d1_capture, sizeof(_d1_capture));
    _mdma_configure();

    HAL_SAI_DeInit(&ICS_SAI_HANDLE_1);

    /* Whatever the .ioc last generated into Core/Src/sai.c is overwritten here,
     * so audio_config.h stays the single source of truth across a CubeMX
     * regeneration. */
    ICS_SAI_HANDLE_1.Init.AudioFrequency   = AUDIO_SAMPLE_RATE_HZ;
    ICS_SAI_HANDLE_1.Init.DataSize         = ICS_SAI_DATASIZE;
    ICS_SAI_HANDLE_1.FrameInit.FrameLength = ICS_SLOT_COUNT * 32;
    ICS_SAI_HANDLE_1.SlotInit.SlotNumber   = ICS_SLOT_COUNT;
    ICS_SAI_HANDLE_1.SlotInit.SlotActive   = (1u << AUDIO_MIC_COUNT) - 1u;

    if (HAL_SAI_Init(&ICS_SAI_HANDLE_1) != HAL_OK)
        Error_Handler();

    _blocks_sent    = 0;
    _blocks_landed  = 0;
    _blocks_taken   = 0;
    _half_in_flight = 0;
    _half_landed    = 0;

    for (uint32_t i = 0; i < sizeof(_stats) / sizeof(uint32_t); ++i)
        ((volatile uint32_t*)&_stats)[i] = 0;

    // WS low, then start the clocks: the mics enumerate during the hold
    _ws_pin_as_gpio();

    if (HAL_SAI_Receive_DMA(&ICS_SAI_HANDLE_1, (uint8_t*)_d1_capture, ICS_DMA_WORDS) != HAL_OK)
        Error_Handler();

    __HAL_TIM_SET_AUTORELOAD(&htim7, ICS_WS_HOLD_MS - 1);
    __HAL_TIM_SET_COUNTER(&htim7, 0);
    HAL_TIM_Base_Start_IT(&htim7);
}

void ics52000_stop_fft(void)
{
    HAL_TIM_Base_Stop_IT(&htim7);
    HAL_MDMA_Abort(&ICS_MDMA_HANDLE);
    HAL_SAI_DMAStop(&ICS_SAI_HANDLE_1);

    _blocks_sent   = 0;
    _blocks_landed = 0;
    _blocks_taken  = 0;
}

static void _extract_channel(const int32_t* src, uint32_t ch, audio_sample_t* dst)
{
	for (uint32_t n = 0; n < AUDIO_SAMPLES_PER_BLOCK; ++n)
		dst[n] = (audio_sample_t)src[n * AUDIO_MIC_COUNT + ch] * AUDIO_SAMPLE_SCALE;
}

/* On success *pcm points at [AUDIO_MIC_COUNT][AUDIO_SAMPLES_PER_BLOCK] floats
 * in [-1, 1), valid until the next call. */
bool ics52000_read(const float32_t (**pcm)[AUDIO_SAMPLES_PER_BLOCK])
{
    uint32_t landed = _blocks_landed;

    if (landed == _blocks_taken)
        return false;

    /* More than one block landed since the last call: the older ones are gone. */
    if (landed - _blocks_taken > 1)
        _stats.missed += landed - _blocks_taken - 1;

    const int32_t* block = _dtcm_block[_half_landed];

    /* Copying out of the ping-pong buffer is what bounds the overwrite window.
     * Nothing above this layer may hold a pointer into _dtcm_block. */
    for (uint32_t ch = 0; ch < AUDIO_MIC_COUNT; ++ch)
        _extract_channel(block, ch, _pcm[ch]);

    /* Ping-pong: block N and N+2 share memory. If two more landed while we
     * were copying, what we just read was overwritten underneath us. */
    if (_blocks_landed - landed >= 2)
    {
        _stats.overwritten++;
        _blocks_taken = _blocks_landed;
        return false;
    }

    _blocks_taken = landed;
    _stats.delivered++;
    *pcm = (const float32_t (*)[AUDIO_SAMPLES_PER_BLOCK])_pcm;

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
    return (ics_stats_t*)&_stats;
}
