#ifndef CLOCK_H
#define CLOCK_H

#include <stdint.h>

inline void     clock_delay_ms(uint32_t delay);
inline uint32_t clock_millis(void);
inline void     clock_cycles_init(void);
inline uint32_t clock_cycles(void);
inline uint32_t clock_hz(void);

#endif
