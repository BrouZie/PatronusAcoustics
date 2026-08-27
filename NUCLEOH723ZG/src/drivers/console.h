#ifndef CONSOLE_H
#define CONSOLE_H

#include "stdint.h"

void console_init(void);
void UART_DMA_send_buffer(int32_t* block);
void UART_DMA_start(void);

#endif
