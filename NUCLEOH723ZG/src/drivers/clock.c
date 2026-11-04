#include "clock.h"

#include "main.h"

#include <stdio.h>

//----- Scaffolding -----//
typedef struct
{
    const char* name;
    uint64_t    delta_cycles;
    uint32_t    hits;
    uint32_t    start;
    uint32_t    end;
    uint32_t    hz;
} BenchZone;

typedef struct
{
    const char* name;
    uint32_t    start;
    uint32_t    end;
    uint32_t    hz;
} FrameTimer;
//-----------------------//

global uint32_t    StartupClockSpeedHz;

global const char* BenchName;
global uint32_t    BenchStart;
global uint32_t    BenchEnd;
global uint64_t    BenchTotalDeltaCycles;
global uint32_t    Hits;

global const char* FrameTimerName;
global uint32_t    FrameTimerStart;
global uint32_t    FrameTimerEnd;

void     clock_delay_ms(uint32_t delay) { HAL_Delay(delay); }
uint32_t clock_millis() { return HAL_GetTick(); }

internal void enable_timing()
{
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->LAR = 0xC5ACCE55;
    DWT->CYCCNT = 0;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
    StartupClockSpeedHz = SystemCoreClock;
}

internal void present_report(const char* name, uint32_t delta_cycles, size_t iterations)
{
    float32_t avg_time = ((delta_cycles * 1000.0f) / StartupClockSpeedHz) / (float32_t)iterations;
    float32_t avg_fps  = (StartupClockSpeedHz * (float32_t)iterations) / delta_cycles;
    float32_t avg_mcpf = (delta_cycles / 1000000.0f) / (float32_t)iterations;
    printf("%s: %.02fms/f, %.02ff/s, %.02fmc/f\r\n", name, avg_time, avg_fps, avg_mcpf);
}

void BENCHMARK_INIT(const char* name)
{
    enable_timing();
    BenchName = name;
}

void BENCHMARK_BEGIN()
{
    BenchStart = DWT->CYCCNT;
}

void BENCHMARK_END()
{
    BenchEnd = DWT->CYCCNT;
    uint32_t delta_cycles = BenchEnd - BenchStart;
    BenchTotalDeltaCycles += delta_cycles;
    Hits++;
}

void BENCHMARK_REPORT()
{
    present_report(BenchName, BenchTotalDeltaCycles, Hits);
    BenchTotalDeltaCycles = 0;
    Hits = 0;
}

void FRAME_TIMER_INIT(const char* name)
{
    enable_timing();
    FrameTimerName = name;
    FrameTimerStart = DWT->CYCCNT;
}

void FRAME_TIMER_LAP()
{
    FrameTimerEnd = DWT->CYCCNT;
    uint32_t delta_cycles = FrameTimerEnd - FrameTimerStart;
    present_report(FrameTimerName, delta_cycles, 1);
    FrameTimerStart = FrameTimerEnd;
}
