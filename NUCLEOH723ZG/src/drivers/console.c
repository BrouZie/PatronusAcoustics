#include "console.h"
#include "audio_config.h"
#include "main.h"
#include "mdma.h"
#include "mpu.h"
#include "usart.h"

#include "arm_math_types.h"
#include <stdio.h>

/*
 * Capture path
 * ------------
 * DTCM --> _block_fft_buf (DTCM, MPU non-cacheable)
 *                      |
 *                      | MDMA, no need for double buffer. MDMA transfers data before FFT function writes over buffer
 *                      v
 *                  _d2_output (RAM_D2, ping-pong)
 *                      |
 *                      | DMA: Double buffer
 *                      v
 *                    USART
 *
 * Output data stored in RAM_D2
 * MDMA sends data from DTCM to RAM_D2, DMA sends data from RAM_D2 to USART
 */

#define OUTPUT_RAM_BUF ".d2_buf" // -> RAM_D2

#define USART_MDMA_HANDLE hmdma_mdma_channel1_sw_0
#define USART_DMA_HANDLE  hdma_usart3_tx

/* Ping-pong staging halves, sized from the figure console.h publishes so the
 * two cannot drift apart. */
static float32_t _d2_output[2][CONSOLE_STAGING_BYTES / sizeof(float32_t)]
    __attribute__((section(OUTPUT_RAM_BUF), aligned(32)));

static volatile uint8_t _dma_active_idx   = 0;
static volatile uint8_t _dma_busy         = 0;
static volatile uint8_t _mdma_busy        = 0;
static uint8_t          _pending_fill_idx = 0;

/* Byte count of the transfer the MDMA is staging, handed to the UART DMA when
 * it lands. Payloads are not all the same size -- an SRP map is not an FFT
 * frame -- so the length cannot be a compile-time constant. */
static volatile uint32_t _pending_bytes = 0;

// Refused payloads plus hardware-reported transfer errors.
static volatile uint32_t _tx_errors = 0;

/* --------- Init  --------- */

void console_init(void)
{
    setvbuf(stdout, NULL, _IONBF, 0); // Non-Buffered output stream
}

int __io_putchar(int ch)
{
    HAL_UART_Transmit(&huart3, (uint8_t*)&ch, 1, HAL_MAX_DELAY);
    return ch;
}

/* --------- Callbacks --------- */

void DMA_transfer_complete(DMA_HandleTypeDef* hdma)
{
    (void)hdma; // Silence warning: unused parameter hdma. Parameter needed for HAL_DMA_RegisterCallback
    huart3.Instance->CR3 &= ~USART_CR3_DMAT;
    _dma_busy             = 0;
    HAL_GPIO_TogglePin(GPIOB, GPIO_PIN_0);
}

void MDMA_transfer_complete(MDMA_HandleTypeDef* hmdma)
{
    (void)hmdma;
    _mdma_busy            = 0;
    _dma_active_idx       = _pending_fill_idx;
    _dma_busy             = 1;
    huart3.Instance->CR3 |= USART_CR3_DMAT;
    HAL_DMA_Start_IT(&USART_DMA_HANDLE, (uint32_t)_d2_output[_dma_active_idx], (uint32_t)&huart3.Instance->TDR,
                     _pending_bytes);
}

/* A failed transfer never reaches the complete callback, so without these the
 * busy flags stay set and the next send spins forever. A lost packet is
 * recoverable; a deadlocked capture loop is not. */
void MDMA_transfer_error(MDMA_HandleTypeDef* hmdma)
{
    (void)hmdma;
    _mdma_busy = 0;
    _tx_errors++;
}

void DMA_transfer_error(DMA_HandleTypeDef* hdma)
{
    (void)hdma;
    huart3.Instance->CR3 &= ~USART_CR3_DMAT;
    _dma_busy             = 0;
    _tx_errors++;
}

/* --------- DMA & MDMA --------- */

void UART_DMA_start(void)
{
    _mpu_configure((uint32_t*)&_d2_output, sizeof(_d2_output));
    console_init();

    /* CubeMX generates this stream as DMA_CIRCULAR; imposed here the way
     * ics52000.c imposes the SAI format. In circular mode HAL_DMA_IRQHandler
     * never releases __HAL_LOCK on transfer-complete, so every
     * HAL_DMA_Start_IT after the first returns HAL_BUSY and exactly one buffer
     * would ever leave the board. */
    USART_DMA_HANDLE.Init.Mode = DMA_NORMAL;
    if (HAL_DMA_Init(&USART_DMA_HANDLE) != HAL_OK)
    {
        Error_Handler();
    }

    HAL_DMA_RegisterCallback(&USART_DMA_HANDLE, HAL_DMA_XFER_CPLT_CB_ID, &DMA_transfer_complete);
    HAL_DMA_RegisterCallback(&USART_DMA_HANDLE, HAL_DMA_XFER_ERROR_CB_ID, &DMA_transfer_error);
    HAL_MDMA_RegisterCallback(&USART_MDMA_HANDLE, HAL_MDMA_XFER_CPLT_CB_ID, &MDMA_transfer_complete);
    HAL_MDMA_RegisterCallback(&USART_MDMA_HANDLE, HAL_MDMA_XFER_ERROR_CB_ID, &MDMA_transfer_error);
}

uint32_t console_tx_errors(void) { return _tx_errors; }

void UART_MDMA_send_buffer(float32_t* block, uint32_t size)
{
    /* Refuse here, where the caller is identifiable, rather than let it become
     * an overrun of RAM_D2 or a transfer that silently never completes. */
    if (!CONSOLE_PAYLOAD_OK(size))
    {
        _tx_errors++;
        return;
    }

    uint8_t fill_idx = 1 - _dma_active_idx;
    while (_dma_busy && fill_idx == _dma_active_idx)
    {
    }
    while (_mdma_busy)
    {
    }
    _pending_fill_idx = fill_idx;
    _pending_bytes    = size;
    _mdma_busy        = 1;
    HAL_MDMA_Start_IT(&USART_MDMA_HANDLE, (uint32_t)block, (uint32_t)_d2_output[fill_idx], size, 1);
}
