#ifndef CONSOLE_H
#define CONSOLE_H

#include "arm_math_types.h"
#include "stdint.h"

void console_init(void);
void UART_MDMA_send_buffer(float32_t* block);
void UART_DMA_start(void);

#endif
