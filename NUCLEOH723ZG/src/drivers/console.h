#ifndef CONSOLE_H
#define CONSOLE_H

#include "arm_math_types.h"
#include "stdint.h"

void console_init(void);
void UART_MDMA_send_buffer(uint8_t* dtcm_block, uint32_t size);
void UART_DMA_start(uint32_t buffer, uint32_t size);

#endif
