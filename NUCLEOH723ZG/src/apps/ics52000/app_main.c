#include "app_entry.h"
#include "console.h"
#include "ics52000.h"

#include <math.h>
#include <stdio.h>

void app_main(void)
{
    const float32_t (*pcm)[AUDIO_SAMPLES_PER_BLOCK];
    audio_format_t fmt = ics52000_format();

    console_init();
    ics52000_start();

    while (1)
    {
        if (ics52000_read(&pcm))
        {
            for (uint32_t i = 0; i < fmt.mic_count; ++i)
            {
                float32_t sum_sq = 0.0f;
                float32_t peak   = 0.0f;
                for (uint32_t j = 0; j < fmt.samples_per_block; ++j)
                {
                    float32_t s = pcm[i][j];
                    sum_sq     += s * s;
                    float32_t a = fabsf(s);
                    if (a > peak)
                        peak = a;
                }
                float rms  = sqrtf(sum_sq / fmt.samples_per_block);
				float dbfs = 20.0f * log10f(rms + 1e-20f);
                // printf("%8ld %8ld %6d\t", (long)rms, (long)peak, (int)dbfs);
				printf("%.1f", dbfs);
				if (i + 1 < fmt.mic_count) printf(",");
            }
            printf("\r\n");
        }
    }
}
