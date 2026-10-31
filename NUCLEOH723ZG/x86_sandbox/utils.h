// Usage example:
//
// int num_blocks = 100;
// sample_t contiguous_samples[num_blocks * AUDIO_SAMPLES * MIC_COUNT];
//
// for (int i = 0; i < num_blocks; ++i)
// {
//     populate_frame(&R, &View, MicPositions, SourceDirection);
//     sample_t* block = &contiguous_samples[i * AUDIO_SAMPLES * MIC_COUNT];
//     for (uint32_t sample_idx = 0; sample_idx < AUDIO_SAMPLES; ++sample_idx)
//     {
//         for (uint32_t mic_idx = 0; mic_idx < MIC_COUNT; ++mic_idx)
//         {
//             block[sample_idx * MIC_COUNT + mic_idx] = View.frame->pcm[sample_idx][mic_idx];
//         }
//     }
// }
// write_audio_to_disk(contiguous_samples, MIC_COUNT, num_blocks, "x86_sandbox/data/test.wav");

#ifndef UTILS_H
#define UTILS_H

#include "types.h"

#define DR_WAV_IMPLEMENTATION
#include "dr_wav.h"

#include <stdio.h>
#include <unistd.h>
#include <fcntl.h>
#include <termios.h>
#include <pty.h>

#define WAV_FORMAT(type) _Generic((type), \
    int16_t:   DR_WAVE_FORMAT_PCM,        \
    int32_t:   DR_WAVE_FORMAT_PCM,        \
    float32_t: DR_WAVE_FORMAT_IEEE_FLOAT  \
)

// Writes interleaved samples (data[frame * num_mics + mic]) to a WAV file at SAMPLE_RATE_HZ.
// num_blocks: number of AUDIO_SAMPLES-long blocks. sample_t must be int16_t, int32_t or float32_t.
static inline void write_audio_to_disk(sample_t* data, int num_mics, int num_blocks, const char* filepath)
{
    drwav wav = {};
    drwav_data_format format = {
        .container     = drwav_container_riff,
        .format        = WAV_FORMAT(data[0]),
        .channels      = (uint32_t)num_mics,
        .sampleRate    = (uint32_t)SAMPLE_RATE_HZ,
        .bitsPerSample = sizeof(sample_t) * 8,
    };

    drwav_init_file_write(&wav, filepath, &format, NULL);
    drwav_uint64 frames_written = drwav_write_pcm_frames(&wav, (drwav_uint64)(AUDIO_SAMPLES * num_blocks), data);
    drwav_uninit(&wav);

    float duration = ((float)num_blocks * AUDIO_SAMPLES) / SAMPLE_RATE_HZ;
    printf("Written: %llu sample frames (%.2f seconds)\n", (unsigned long long)frames_written, duration);
}

// TODO: Smash into one unified util.h THIS IS NOT GOOD ENOUGH!

static inline int open_vusart(const char* port_name)
{
    int master, slave;
    char name[64];
    struct termios tio;

    if (openpty(&master, &slave, name, NULL, NULL) < 0)
    {
        perror("openpty failed");
    }

    tcgetattr(slave, &tio);
    cfmakeraw(&tio);
    tcsetattr(slave, TCSANOW, &tio);

    // Non-blocking: if nobody is reading, drop data like a real UART would
    fcntl(master, F_SETFL, fcntl(master, F_GETFL) | O_NONBLOCK);

    // Symlinking to more meaningful dev name
    unlink(port_name);
    if (symlink(name, port_name) < 0)
    {
        perror("symlink");
    }

    printf("Simulated UART over %s (%s)\n", port_name, name);

    return master;
}

static inline void vusart_send(int fd, const void* data, size_t len)
{
    // Not handling perror - so as to not flood stdout
    // whenever nothing is connected
    if (write(fd, data, len) < 0)
    {
        // perror("write");
    }
}

#endif // UTILS_H
