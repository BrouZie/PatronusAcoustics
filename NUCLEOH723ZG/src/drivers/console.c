#include "main.h"
#include "usart.h"
#include "console.h"

#include <stdio.h>

void console_init(void)
{
    setvbuf(stdout, NULL, _IONBF, 0); // Non-Buffered output stream
}

int __io_putchar(int ch)
{
    HAL_UART_Transmit(&huart3, (uint8_t*)&ch, 1, HAL_MAX_DELAY);
    return ch;
}
