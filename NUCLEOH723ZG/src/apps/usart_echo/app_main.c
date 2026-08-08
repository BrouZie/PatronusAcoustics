#include "app_entry.h"
#include "clock.h"
#include "console.h"

#include <stdio.h>

void app_main(void)
{
	console_init();

    for (;;)
    {
        // HAL_GPIO_TogglePin(GPIOB, GPIO_PIN_0);
        printf("The tick is currently: %lu\r\n", clock_millis());
		clock_delay_ms(250);
    }
}
