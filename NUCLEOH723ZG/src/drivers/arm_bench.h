#include "usart.h"
#include "console.h"

#include <stdio.h>

#ifndef BENCHMARK_H
#define BENCHMARK_H

#define HANDLE_USART huart3;

static const char* BenchName;
static float32_t   TotalCycles;
static uint32_t    StartupClockSpeedHz;
static uint32_t    Hits;

#define BENCH_SETUP(name) do {                      \
    BenchName = name;                               \
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk; \
    DWT->LAR = 0xC5ACCE55;                          \
    DWT->CYCCNT = 0;                                \
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;            \
    StartupClockSpeedHz = SystemCoreClock; } while (0)

#define BENCH_BEGIN()                        \
    uint32_t start_cycle_count = DWT->CYCCNT

#define BENCH_END() do {                            \
    TotalCycles += DWT->CYCCNT - start_cycle_count; \
    ++Hits; } while (0)

static inline void bench_report(void)
{
    float32_t avg_time = ((TotalCycles * 1000.0f) / StartupClockSpeedHz) / (float32_t)Hits;
    float32_t avg_fps  = (StartupClockSpeedHz * (float32_t)Hits) / TotalCycles;
    float32_t avg_mcpf = (TotalCycles / 1000000.0f) / (float32_t)Hits;

    printf("%s: %.02fms/f, %.02ff/s, %.02fmc/f\r\n", BenchName, avg_time, avg_fps, avg_mcpf);
}

#endif // BENCHMARK_H
