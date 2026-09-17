#include "console.h"
#include "audio_config.h"
#include "main.h"
#include "mdma.h"
#include "mpu.h"
#include "usart.h"

#include "arm_math_types.h"
#include <stdint.h>
#include <stdio.h>

/*
 * Capture path
 * ------------
 * DTCM --> (DTCM, MPU non-cacheable)
 *                      |
 *                      | MDMA, transfers data from DTCM to caller allocated location in RAM 
 *                      v
 *                  _output_buffer (Location chosen by caller, ping-pong)
 *                      |
 *                      | DMA: Double buffer
 *                      v
 *                    USART
 *
 * Caller-provided output buffer; double-buffered to allow one buffer to be transmitted while the other is filled
 * MDMA sends data from DTCM to outputbuffer, DMA sends data from buffer address to USART
 */

#define OUTPUT_BUF_SIZE SPECTRUM_FLOATS

#define USART_MDMA_HANDLE hmdma_mdma_channel1_sw_0
#define USART_DMA_HANDLE hdma_usart3_tx

// Output buffer and flags
static uint32_t _output_buffer[2];
static uint32_t _output_buffer_size;
static uint32_t _fill_offset[2] = {0, 0};
static uint32_t _pending_size   = 0;

static volatile uint8_t _dma_active_idx = 0;
static volatile uint8_t _dma_busy       = 0;
static volatile uint8_t _mdma_busy      = 0;
static uint8_t _pending_fill_idx        = 0;

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
    _mdma_busy = 0;

    uint8_t idx = _pending_fill_idx;
    _fill_offset[idx] += _pending_size;

    if (_fill_offset[idx] < _output_buffer_size) {
        return; // half not full yet — wait for the next UART_MDMA_send_buffer() call
    }
	
	_fill_offset[idx] = 0;

    _dma_active_idx = idx;
    _dma_busy       = 1;
    huart3.Instance->CR3 |= USART_CR3_DMAT;
    HAL_DMA_Start_IT(&USART_DMA_HANDLE, _output_buffer[_dma_active_idx], (uint32_t)&huart3.Instance->TDR,
                     _output_buffer_size);
}

/* --------- DMA & MDMA --------- */

void UART_DMA_start(uint32_t output_buffer, uint32_t size)
{
	_output_buffer[0] = output_buffer;
	_output_buffer[1] = output_buffer + size;
	_output_buffer_size = size;
	
    _mpu_configure((uint32_t*)output_buffer, size * 2);
    console_init();
    HAL_DMA_RegisterCallback(&USART_DMA_HANDLE, HAL_DMA_XFER_CPLT_CB_ID, &DMA_transfer_complete);
    HAL_MDMA_RegisterCallback(&USART_MDMA_HANDLE, HAL_MDMA_XFER_CPLT_CB_ID, &MDMA_transfer_complete);
}

void UART_MDMA_send_buffer(uint8_t* dtcm_block, uint32_t size)
{
    uint8_t fill_idx = 1 - _dma_active_idx;
    while (_dma_busy && fill_idx == _dma_active_idx) { }
    while (_mdma_busy) { }

    _pending_fill_idx = fill_idx;
	_pending_size     = size;
    _mdma_busy        = 1;


    uint32_t dest = _output_buffer[fill_idx] + _fill_offset[fill_idx];
    HAL_MDMA_Start_IT(&USART_MDMA_HANDLE, (uint32_t)dtcm_block, dest, size, 1);
}
