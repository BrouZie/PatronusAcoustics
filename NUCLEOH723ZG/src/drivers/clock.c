#include "main.h"
#include "clock.h"

#include <stdint.h>

void clock_delay_ms(uint32_t delay) { HAL_Delay(delay); }
uint32_t clock_millis() { return HAL_GetTick(); }
