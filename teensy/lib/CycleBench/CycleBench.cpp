#include "CycleBench.hpp"

#include <stdlib.h>

namespace
{
int compare_u32(const void* a, const void* b)
{
    uint32_t x { *static_cast<const uint32_t*>(a) };
    uint32_t y { *static_cast<const uint32_t*>(b) };
    return (x > y) - (x < y);
}
} // namespace

namespace CycleBench
{
void begin()
{
    ARM_DEMCR    |= ARM_DEMCR_TRCENA;
    ARM_DWT_CTRL |= ARM_DWT_CTRL_CYCCNTENA;
}

Stats stats_from(uint32_t* samples, int n)
{
    qsort(samples, n, sizeof(uint32_t), compare_u32);
    uint64_t sum {};
    for (int i {}; i < n; ++i)
        sum += samples[i];
    return Stats { samples[0], samples[n / 2], samples[n - 1], static_cast<float>(sum) / n };
}

void print_row(Stream& out, const char* name, const Stats& s, float per_item)
{
    out.printf("%-36s median %10lu  min %10lu  mean %12.1f  max %10lu", name,
               (unsigned long)s.median, (unsigned long)s.min, s.mean, (unsigned long)s.max);
    if (per_item > 0.0f)
        out.printf("  | %.3f/item", s.median / per_item);
    out.println();
}
} // namespace CycleBench
