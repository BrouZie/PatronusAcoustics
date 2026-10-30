#include "app_entry.h"

#include "console.h"
#include "ics52000.h"

#include <stdio.h>

global AudioFrameView View;

void app_main(void)
{
    console_init();
    ics52000_init();

    uint32_t last_seq = 0;

    while (true)
    {
        // Skip until a new half has landed (also skips seq == 0, before any data)
        if (!ics52000_read(&View) || View.seq == last_seq)
        {
            continue;
        }
        last_seq = View.seq;

        for (uint32_t mic_idx = 0; mic_idx < MIC_COUNT; ++mic_idx)
        {
            float32_t sum_sq = 0.0f;

            for (uint32_t sample_idx = 0; sample_idx < AUDIO_SAMPLES; ++sample_idx)
            {
                // Interleaved: pcm[sample][mic]
                float32_t sample  = (float32_t)View.frame->pcm[sample_idx][mic_idx];
                sum_sq += sample * sample;
            }

            float32_t rms  = sqrtf(sum_sq / AUDIO_SAMPLES) / SCALING_FACTOR(sample_t);
            float32_t dbfs = 20.0f * log10f(rms + 1e-20f);

            printf("%.1f", dbfs);
            if (mic_idx + 1 < MIC_COUNT)
            {
                printf(",");
            }
        }
        printf("\r\n");
    }
}
