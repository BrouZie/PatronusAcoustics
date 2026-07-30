#pragma once

#include <Arduino.h>

namespace CycleBench
{
// Enable the DWT cycle counter. Call once before any measurement.
void begin();

// Current cycle count (wraps every ~7 s at 600 MHz; measure short intervals).
inline uint32_t now()
{
    return ARM_DWT_CYCCNT;
}

struct Stats
{
    uint32_t min;
    uint32_t median;
    uint32_t max;
    float mean;
};

// Sorts samples in place.
Stats stats_from(uint32_t* samples, int n);

// Runs fn() reps times; samples must hold reps entries.
template <typename F> Stats measure(F&& fn, uint32_t* samples, int reps)
{
    for (int i {}; i < reps; ++i)
    {
        uint32_t t0 { now() };
        fn();
        samples[i] = now() - t0;
    }
    return stats_from(samples, reps);
}

// One formatted result row: "name: median cycles (min/mean/max) [per-item]".
// per_item > 0 adds a median/per_item column (e.g. cycles per op).
void print_row(Stream& out, const char* name, const Stats& s, float per_item = 0.0f);
} // namespace CycleBench
