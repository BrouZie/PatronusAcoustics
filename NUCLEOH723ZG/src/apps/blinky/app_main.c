#include "app_entry.h"
#include "main.h"

static void blinky(void)
{
    HAL_GPIO_TogglePin(GPIOB, GPIO_PIN_0);
    HAL_Delay(450);

    HAL_GPIO_TogglePin(GPIOE, GPIO_PIN_1);
    HAL_Delay(450);

    HAL_GPIO_TogglePin(GPIOB, GPIO_PIN_14);
}

void app_main(void)
{
	while (1)
	{
		blinky();
	}
}
