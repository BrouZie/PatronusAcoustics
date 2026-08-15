#include "app_entry.h"
#include "console.h"
#include "ics52000.h"

#include <math.h>
#include <stdio.h>

void app_main(void)
{
    const audio_sample_t* data;
    audio_format_t fmt = ics52000_format();

    console_init();
    ics52000_start();

    while (1)
    {
        if (ics52000_read(&data))
        {
            for (uint32_t i = 0; i < fmt.mic_count; ++i)
            {
                int64_t sum_sq = 0;
                int32_t peak   = 0;
                for (uint32_t j = 0; j < fmt.samples_per_block; ++j)
                {
                    int32_t s  = data[j * fmt.mic_count + i];
                    sum_sq    += (int64_t)s * s;
                    int32_t a  = s < 0 ? -s : s;
                    if (a > peak)
                        peak = a;
                }
                float rms  = sqrtf((float)sum_sq / (fmt.samples_per_block));
				float dbfs = 20.0f * log10f((rms < 1.0f ? 1.0f : rms) / (float)fmt.full_scale);
                // printf("%8ld %8ld %6d\t", (long)rms, (long)peak, (int)dbfs);
				printf("%ld", (long)dbfs);
				if (i + 1 < fmt.mic_count) printf(",");
            }
            printf("\r\n");
        }
    }
}
