#include "console.h"
#include "main.h"
#include "usart.h"
#include "mdma.h"
#include "mpu.h"

#include "arm_math_types.h"
#include <stm32h7xx_hal_mdma.h>
#include <stdio.h>
#include <stm32h723xx.h>

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

#define OUTPUT_RAM_BUF ".d2_buf"    // -> RAM_D2
#define OUTPUT_BUF_SIZE 514

#define USART_MDMA_HANDLE hmdma_mdma_channel1_sw_0
#define USART_DMA_HANDLE hdma_usart3_tx

// Output buffer and flags
static float32_t _d2_output[2][OUTPUT_BUF_SIZE] __attribute__((section(OUTPUT_RAM_BUF), aligned(32)));

static volatile uint8_t _dma_active_idx = 0;
static volatile uint8_t _dma_busy = 0;
static volatile uint8_t _mdma_busy = 0;   
static uint8_t _pending_fill_idx = 0;    

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

void DMA_transfer_complete(DMA_HandleTypeDef *hdma)
{
	(void)hdma; // Silence warning: unused parameter hdma. Parameter needed for HAL_DMA_RegisterCallback 
	huart3.Instance->CR3 &= ~USART_CR3_DMAT;
	_dma_busy = 0;
	HAL_GPIO_TogglePin(GPIOB, GPIO_PIN_0);
}

void MDMA_transfer_complete(MDMA_HandleTypeDef *hmdma)
{
	(void)hmdma; // Silence warning
	_mdma_busy = 0;

	_dma_active_idx = _pending_fill_idx;
	_dma_busy = 1;

	huart3.Instance->CR3 |= USART_CR3_DMAT;
	HAL_DMA_Start_IT(&USART_DMA_HANDLE,  
					 (uint32_t)_d2_output[_dma_active_idx], 
					 (uint32_t)&huart3.Instance->TDR, 
					 OUTPUT_BUF_SIZE * sizeof(float32_t));
}

/* --------- DMA & MDMA --------- */

void UART_DMA_start(void)
{
	_mpu_configure((uint32_t*)&_d2_output, sizeof(_d2_output));
	console_init();
	HAL_DMA_RegisterCallback(&USART_DMA_HANDLE, HAL_DMA_XFER_CPLT_CB_ID, &DMA_transfer_complete);
	HAL_MDMA_RegisterCallback(&USART_MDMA_HANDLE, HAL_MDMA_XFER_CPLT_CB_ID, &MDMA_transfer_complete);
}

void UART_MDMA_send_buffer(float32_t* block)
{
	uint8_t fill_idx = 1 - _dma_active_idx;

	while (_dma_busy && fill_idx == _dma_active_idx)
	{
		// If dma is busy and fill idx is same as active idx buffer wait for the buffer to become ready
	}

	while (_mdma_busy)
	{
		// Wait while DMA is busy
	}

	_pending_fill_idx = fill_idx;
	_mdma_busy = 1;

	HAL_MDMA_Start_IT(&USART_MDMA_HANDLE,
					 (uint32_t)block, 
					 (uint32_t)_d2_output[fill_idx], 
					 OUTPUT_BUF_SIZE * sizeof(float32_t), 
					 1);
}
