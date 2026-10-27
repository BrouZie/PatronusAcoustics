#include <stdio.h>
#include "platform.h"

#define DR_WAV_IMPLEMENTATION
#include "dr_wav.h"

void write_audio_to_disk(float* data, int num_mics, int num_blocks, const char* filepath)
{
    // NOTE: Function uses:
    //      - Sample rate at 16kHz
    //      - Amount of samples per block is 512
    //      - float32_t for audio data, but will change to int16_t later!
    //
    // data:       pointer to audio data to write
    // num_mics:   amount of microphones/channels
    // num_blocks: how many AUDIO_SAMPLES * MIC_COUNT you want to write
    // filepath:   desired output path

    // Usage example:
    // const char* filepath = "x86_sandbox/data/test.wav";
    // int num_blocks = 100;
    // float contiguous_data[num_blocks * AUDIO_SAMPLES * MIC_COUNT];
    //
    // for (int i = 0; i < num_blocks; ++i)
    // {
    //     populate_frame(&R, &View, MicArray, Direction);
    //     for (uint32_t mic_idx = 0; mic_idx < MIC_COUNT; ++mic_idx)
    //     {
    //         for (uint32_t sample_idx = 0 ; sample_idx < AUDIO_SAMPLES; ++sample_idx)
    //         {
    //             contiguous_data[(i * AUDIO_SAMPLES * MIC_COUNT)
    //                             + (sample_idx * MIC_COUNT)
    //                             + mic_idx] = View.frame->pcm[sample_idx][mic_idx];
    //         }
    //     }
    // }
    // write_audio_to_disk(contiguous_data, MIC_COUNT, num_blocks, filepath);

    drwav wav = {};
    drwav_data_format format;
    format.container = drwav_container_riff;     // <-- drwav_container_riff = normal WAV files, drwav_container_w64 = Sony Wave64.
    format.format = DR_WAVE_FORMAT_IEEE_FLOAT;          // <-- Any of the DR_WAVE_FORMAT_* codes.
    format.channels = num_mics;
    format.sampleRate = (uint32_t)SAMPLE_RATE_HZ;
    format.bitsPerSample = 32;

    drwav_init_file_write(&wav, filepath, &format, NULL);
    drwav_uint64 frames_written = drwav_write_pcm_frames(&wav, AUDIO_SAMPLES * num_blocks, data);
    drwav_uninit(&wav);

    printf("Written: %lld sample frames\n", frames_written);

    float duration = ((float)num_blocks * AUDIO_SAMPLES) / SAMPLE_RATE_HZ;
    printf("Duration: %.2f seconds\n", duration);
}
