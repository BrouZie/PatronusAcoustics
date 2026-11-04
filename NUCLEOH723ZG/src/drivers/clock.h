#ifndef CLOCK_H
#define CLOCK_H

#include <types.h>

void     clock_delay_ms(uint32_t delay);
uint32_t clock_millis(void);

// Utils for benchmarking specific functions/execution of code.
// See `src/apps/bench/app_main.c` for a usage example.
// TODO: Add different benchmarking zones - see struct scaffolding in clock.h
void BENCHMARK_INIT(const char* name);
// Wrap `BEGIN` and `END` around the desired section you want benchmarked
void BENCHMARK_BEGIN();
void BENCHMARK_END();
// The report should be called in the outer scope (after N iterations of `BEGIN` and `END`)
void BENCHMARK_REPORT();


// Sanity checker functions to ensure your application reaches the expected fps target.
// Drop `FRAME_TIMER_INIT` into the startup and `FRAME_TIMER_LAP` inside your main loop.
void FRAME_TIMER_INIT(const char* name);
void FRAME_TIMER_LAP();

#endif
