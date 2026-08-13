#include "app_entry.h"
#include "console.h"
#include "ics52000.h"
#include "main.h"

#include <math.h>
#include <stdio.h>

void app_main(void)
{
    const ics_sample_t* data;
    ics_config_t conf = ics52000_config();
	ics_stats_t stats;

    console_init();
    ics52000_start();

    while (1)
    {
        if (ics52000_read(&data))
        {
            for (uint32_t i = 0; i < conf.ics_mic_count; ++i)
            {
                int64_t sum_sq = 0;
                int32_t peak   = 0;
                for (uint32_t j = 0; j < conf.ics_samples_per_mic; ++j)
                {
                    int32_t s  = data[j * conf.ics_mic_count + i];
                    sum_sq    += (int64_t)s * s;
                    int32_t a  = s < 0 ? -s : s;
                    if (a > peak)
                        peak = a;
                }
                float rms  = sqrtf((float)sum_sq / (conf.ics_samples_per_mic));
                float dbfs = 20.0f * log10f(rms / 8388608.0f);
                printf("rms=%8ld peak=%8ld %6d dBFS\t", (long)rms, (long)peak, (int)dbfs);
            }
            printf("\r\n");
        }
    }
}
