#include "mic_data_dma.h"

void DMA_Transfer_Complete(DMA_HandleTypeDef *hdma) {
	// Disable UART DMA mode
	huart3.Instance->CR3 &= ~USART_CR3_DMAT;

	//Toggle LED
	HAL_GPIO_TogglePin(GPIOB, GPIO_PIN_0); // Green build in LED turns on
}

// Generic buffer sender — waits for any in-flight UART DMA to finish first
void UART_DMA_Send_Buffer(uint8_t *data, uint16_t len) {
	while (hdma_usart3_tx.State != HAL_DMA_STATE_READY) {
		// previous UART DMA transfer still running — wait for it to free up
	}
	huart3.Instance->CR3 |= USART_CR3_DMAT;
	HAL_DMA_Start_IT(&hdma_usart3_tx, (uint32_t)data,
	                  (uint32_t)&huart3.Instance->TDR, len);
}
