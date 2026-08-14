#ifndef MICDATADMA_H
#define MICDATADMA_H

#include "main.h"
#include <string.h>

extern volatile uint8_t mic_half_ready;
extern volatile uint8_t mic_full_ready;
extern UART_HandleTypeDef huart3;
extern DMA_HandleTypeDef hdma_usart3_tx;
extern char * const msg; // Change later, keep it just for simple demonstration

void UART_DMA_Send(void);
void UART_DMA_Send_Buffer(uint8_t *data, uint16_t len);
void DMA_Transfer_Complete(DMA_HandleTypeDef *hdma);
#endif /*MICDATADMA_H */
