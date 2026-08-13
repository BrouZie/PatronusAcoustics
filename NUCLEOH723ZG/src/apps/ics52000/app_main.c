#include "app_entry.h"
#include "main.h"
#include "console.h"
#include "ics52000.h"

#include <math.h>
#include <stdio.h>

void app_main(void)
{
    ics_chunk_t chunk;

    ics52000_start();
    console_init();

    while (1)
    {
        if (ics52000_read(&chunk))
        {
            int64_t sum_sq = 0;
            int32_t peak   = 0;

            for (size_t i = 0; i < chunk.frames; ++i)
            {
                int32_t s  = chunk.data[i];
                sum_sq    += (int64_t)s * s;
                int32_t a  = s < 0 ? -s : s;
                if (a > peak)
                    peak = a;
            }

            float rms  = sqrtf((float)sum_sq / (chunk.frames));
            float dbfs = 20.0f * log10f(rms / 8388608.0f);
            printf("rms=%8ld peak=%8ld %6d dBFS\r\n", (long)rms, (long)peak, (int)dbfs);
        }
    }
}
