#include "ics52000.h"
#include "main.h"
#include "sai.h"

/* --------- CONFIG ---------*/
#define ICS_MIC_COUNT 1
#define ICS_SLOT_COUNT (ICS_MIC_COUNT <= 2 ? 2 : ICS_MIC_COUNT <= 4 ? 4 : 8)
#define ICS_SAI_HANDLE_1 hsai_BlockA1
#define ICS_DMA_SECTION ".RAM_D1"
#define ICS_SAMPLES_PER_MIC 512 // controls latency & buffer size
#define ICS_BLOCK_SAMPLES (ICS_SAMPLES_PER_MIC * ICS_MIC_COUNT)
#define ICS_DMA_WORDS (ICS_BLOCK_SAMPLES * 2)

/* --------- AUDIO BUFFERS ---------*/
static uint32_t _dma_buf[ICS_DMA_WORDS] __attribute__((section(ICS_DMA_SECTION), aligned(32)));
static int32_t _block_buf[ICS_BLOCK_SAMPLES];

/* --------- Stats instance ---------*/
static ics_stats_t _stats; // surfaced through ics52000_stats(ics_stats_t)

/* --------- Callback/ISR variables ---------*/
static volatile uint32_t _blocks_produced; // ISR increments
static uint32_t _blocks_consumed;          // buffer halfs read by CPU

/* --------- Callback functions ---------*/

// SAI1_Block_A:
void HAL_SAI_RxHalfCpltCallback(SAI_HandleTypeDef* hsai)
{
    if (hsai->Instance != SAI1_Block_A)
        return;
    ++_blocks_produced;
}

void HAL_SAI_RxCpltCallback(SAI_HandleTypeDef* hsai)
{
    if (hsai->Instance != SAI1_Block_A)
        return;

    HAL_GPIO_TogglePin(GPIOB, GPIO_PIN_14);
    ++_blocks_produced;
}

void HAL_SAI_ErrorCallback(SAI_HandleTypeDef* hsai)
{
    if (hsai->Instance != SAI1_Block_A)
        return;
    _stats.bus_errors++;
    _stats.last_hal_err = hsai->ErrorCode;
}

/* Convert raw uint32_t value to a signed int32_t
 * utilizing two's complement*/
static inline int32_t _sample(uint32_t raw)
{
    return (raw & 0x00800000u) ? raw | 0xFF000000u : raw; // positive or negative
}

void ics52000_start(void)
{
    HAL_SAI_DeInit(&ICS_SAI_HANDLE_1);

    ICS_SAI_HANDLE_1.FrameInit.FrameLength = ICS_SLOT_COUNT * 32;
    ICS_SAI_HANDLE_1.SlotInit.SlotNumber   = ICS_SLOT_COUNT;
    ICS_SAI_HANDLE_1.SlotInit.SlotActive   = (1u << ICS_MIC_COUNT) - 1u;

    if (HAL_SAI_Init(&ICS_SAI_HANDLE_1) != HAL_OK)
        Error_Handler();

    _blocks_produced = 0;
    _blocks_consumed = 0;

    if (HAL_SAI_Receive_DMA(&ICS_SAI_HANDLE_1, (uint8_t*)_dma_buf, ICS_DMA_WORDS) != HAL_OK)
        Error_Handler();
}

void ics52000_stop(void)
{
    HAL_SAI_DMAStop(&ICS_SAI_HANDLE_1);
    _blocks_produced = 0;
    _blocks_consumed = 0;
}

bool ics52000_read(ics_chunk_t* chunk)
{
    uint32_t p = _blocks_produced;
    if (_blocks_consumed == p)
        return false;

    if (p - _blocks_consumed > 1)
        _stats.dropped += p - _blocks_consumed - 1;

    uint32_t* src = &_dma_buf[((p - 1) % 2) * (ICS_DMA_WORDS / 2)];
    for (int i = 0; i < ICS_BLOCK_SAMPLES; ++i)
    {
        _block_buf[i] = _sample(src[i]);
    }

    chunk->data   = _block_buf;
    chunk->frames = ICS_SAMPLES_PER_MIC;

    _blocks_consumed = p;
    _stats.blocks++;

    return true;
}

ics_stats_t ics52000_stats(void)
{
    return _stats;
}
