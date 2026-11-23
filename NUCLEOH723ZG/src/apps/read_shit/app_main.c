#include "app_entry.h"
#include "usart.h"

#include "console.h"

#include <stdio.h>

void app_main(void)
{
    console_init();

    while (true)
    {
        uint8_t ch;
        HAL_UART_Receive(&huart3, &ch, 1, HAL_MAX_DELAY);

        char result = ch + 1;
        printf("out is this: %c\r\n", result);
    }
}
