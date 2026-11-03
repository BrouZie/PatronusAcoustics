#include "clock.h"
#include "main.h"

#include <stdint.h>

void clock_delay_ms(uint32_t delay) { HAL_Delay(delay); }
uint32_t clock_millis() { return HAL_GetTick(); }

void clock_cycles_init()
{
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->LAR = 0xC5ACCE55;
    DWT->CYCCNT = 0;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
}

uint32_t clock_cycles()
{
    return DWT->CYCCNT;
}

inline uint32_t clock_hz()
{
    return SystemCoreClock;
}
