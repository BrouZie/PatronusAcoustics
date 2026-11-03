#ifndef CLOCK_H
#define CLOCK_H

#include <stdint.h>

void     clock_delay_ms(uint32_t delay);
uint32_t clock_millis(void);
void     clock_cycles_init(void);
uint32_t clock_cycles(void);
uint32_t clock_hz(void);

#endif
