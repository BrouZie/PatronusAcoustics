#include "simulation.h"
#include "random.h"

#define ICS_SAMPLE_RATE_HZ SAMPLE_RATE_HZ
#define SPEED_OF_SOUND 343.0f

// An array of 2 frames just because the STM32 will have two of them
// It is strictly unnecessary on x86, but kept so that both platforms
// are almost identical
global AudioFrame g_PlatformAudioFrame[2];
global uint32_t   g_Sequence;

global const float g_BaseToneHz = 300.0f;
global const float g_HarmonicLevels[] = { 1.0f, 0.6f, 0.4f, 0.25f };

// Local array frame: mics in x–y plane, boresight = +z
// az: deflection toward +x (left/right), el: deflection toward +y (up/down)
// (0, 0) = straight out of the board
static inline Vec3 angles_to_vec3(float32_t az_deg, float32_t el_deg)
{
    float32_t sin_az, cos_az, sin_el, cos_el;
    arm_sin_cos_f32(az_deg, &sin_az, &cos_az);
    arm_sin_cos_f32(el_deg, &sin_el, &cos_el);

    return (Vec3) {
        .x = cos_el * sin_az,
        .y = sin_el,
        .z = cos_el * cos_az,
    };
}

internal inline float mic_delay_seconds(Vec3 mic, Vec3 sound_src)
{
    return - (mic.x * sound_src.x + mic.y * sound_src.y + mic.z * sound_src.z) / SPEED_OF_SOUND;
}

internal inline float linear_interpolation(float start, float end, float alpha)
{
    return start + alpha * (end - start);
}

bool32 sim_produce_frame(rng_t* r, AudioFrameView* view, MicArray array, AngleDeg direction)
{
    local_persist uint64_t sample_idx_offset = 0;
    local_persist AngleDeg prev_direction;
    local_persist bool32 has_prev = false;

    if (!has_prev)
    {
        prev_direction = direction;
        has_prev = true;
    }

    Vec3 sound_src_start = angles_to_vec3(prev_direction.az, prev_direction.el);
    Vec3 sound_src_end   = angles_to_vec3(direction.az, direction.el);

    for (uint32_t mic_idx = 0; mic_idx < MIC_COUNT; mic_idx++)
    {
        float tau_start = mic_delay_seconds(array.pos[mic_idx], sound_src_start);
        float tau_end   = mic_delay_seconds(array.pos[mic_idx], sound_src_end);

        for (uint32_t sample_idx = 0; sample_idx < AUDIO_SAMPLES; sample_idx++)
        {
            float alpha = (float)sample_idx / AUDIO_SAMPLES;
            float tau   = linear_interpolation(tau_start, tau_end, alpha);

            uint64_t n = sample_idx_offset + sample_idx;
            float t = (float)n / ICS_SAMPLE_RATE_HZ - tau;

            float sample = 0.0f;
            for (uint32_t level_idx = 0; level_idx < ARRAY_COUNT(g_HarmonicLevels); level_idx++)
            {
                sample += g_HarmonicLevels[level_idx] * sinf(2 * PI * ((float)level_idx + 1) * g_BaseToneHz * t);
            }
            float noise  = rng_gaussf(r) * 0.006f;
            sample =  sample * 0.3f + noise;
            sample = fmaxf(-1.0f, fminf(1.0f, sample));

            g_PlatformAudioFrame[g_Sequence % 2].pcm[sample_idx][mic_idx] = (sample_t)(sample * SCALING_FACTOR(sample_t));
        }
    }

    prev_direction = direction;
    sample_idx_offset += AUDIO_SAMPLES;
    view->seq   = g_Sequence;
    view->frame = &g_PlatformAudioFrame[g_Sequence++ % 2];

    return 1;
}
