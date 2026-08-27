#include "audio_format.h"
#include "main.h"
#include "usart.h"
#include "console.h"
#include "mpu.h"
#include "audio_config.h"
#include <stdio.h>
#include <stm32h723xx.h>
#include <stm32h7xx_hal_dma.h>

#define OUTPUT_RAM_BUF ".d2_buf"    // -> RAM_D2
#define OUTPUT_BUF_SIZE AUDIO_SAMPLES_PER_BLOCK	

// Output buffer 
static float32_t _d2_output[OUTPUT_BUF_SIZE] __attribute__((section(OUTPUT_RAM_BUF), aligned(32)));

void console_init(void)
{
    setvbuf(stdout, NULL, _IONBF, 0); // Non-Buffered output stream
}

int __io_putchar(int ch)
{
    HAL_UART_Transmit(&huart3, (uint8_t*)&ch, 1, HAL_MAX_DELAY);
    return ch;
}

void DMA_transfer_complete(DMA_HandleTypeDef *hdma)
{
	(void)hdma; // Silence warning: unused parameter hdma. Parameter needed for HAL_DMA_RegisterCallback 
	huart3.Instance->CR3 &= ~USART_CR3_DMAT;

	HAL_GPIO_TogglePin(GPIOB, GPIO_PIN_0);
}

void UART_DMA_start(void)
{
	_mpu_configure((uint32_t*)&_d2_output, OUTPUT_BUF_SIZE);
	console_init();
	HAL_DMA_RegisterCallback(&hdma_usart3_tx, HAL_DMA_XFER_CPLT_CB_ID, &DMA_transfer_complete);
}

void UART_DMA_send_buffer(int32_t* block)
{
	memcpy(_d2_output, block, OUTPUT_BUF_SIZE);
	huart3.Instance->CR3 |= USART_CR3_DMAT;
	HAL_DMA_Start_IT(&hdma_usart3_tx,  (uint32_t)_d2_output, (uint32_t)&huart3.Instance->TDR, OUTPUT_BUF_SIZE);
}
