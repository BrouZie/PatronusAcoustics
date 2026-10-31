#include "clock.h"
#include "main.h"

#include <stdint.h>

inline void clock_delay_ms(uint32_t delay) { HAL_Delay(delay); }
inline uint32_t clock_millis() { return HAL_GetTick(); }

inline void clock_cycles_init()
{
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->LAR = 0xC5ACCE55;
    DWT->CYCCNT = 0;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
}

inline uint32_t clock_cycles()
{
    return DWT->CYCCNT;
}

inline uint32_t clock_hz()
{
    return SystemCoreClock;
}
