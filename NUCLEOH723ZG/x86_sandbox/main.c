#include "simulation.h"
#include "utils.h"
#include "dsp.h"

#include "stdio.h"

#define LOGMEL
#define BEAMFORM
// #define BENCHMARK

#ifdef BENCHMARK
#include <time.h>
#include <x86intrin.h>
#endif

global rng_t R;
global AudioFrameView View;
global AngleDeg SourceDirection = {
    .az = -45.0f,
    .el = 30.0f
};
global const MicArray MicPositions = { {
    { 0.0000000f, 0.1335750f, 0.0f },
    { 0.1270370f, 0.0412770f, 0.0f },
    { 0.0785130f, -0.108064f, 0.0f },
    { -0.075183f, -0.108064f, 0.0f },
    { -0.127037f, 0.0412770f, 0.0f },
} };

global PrevAudioFrame Prev;
global FFT_Spectrum Spec;

global SRP_PHAT Srp;
global SRP_State State;
global const SRP_Grid Grid = {
    .az_start = -60.0f, .az_step = 1.0f,
    .el_start = -60.0f, .el_step = 1.0f
};

#ifdef LOGMEL

#define LOGMEL_MAGIC               0x4C454D4C
#define LOGMEL_Q_SCALE             1.5f
#define LOGMEL_Q_OFFSET            -100.0f
#define NUM_FRAMES                 61
static inline uint8_t quantize_db(float32_t db)
{
    float32_t byte_value = (db - LOGMEL_Q_OFFSET) * LOGMEL_Q_SCALE;
    if (byte_value < 0.0f) byte_value   = 0.0f;
    if (byte_value > 255.0f) byte_value = 255.0f;
    return (uint8_t)(byte_value + 0.5f);
}

typedef struct {
    uint32_t magic;       // LOGMEL_MAGIC
    uint32_t seq;         // increments every image; used to detect drops
    float32_t azimuth;
    float32_t elevation;
} logmel_header_t;

global Logmel  Mel;
global uint8_t MelPackets[NUM_MEL_BANDS];
global uint8_t FirstPacket[sizeof(logmel_header_t) + NUM_MEL_BANDS];

#ifdef BEAMFORM
global float32_t BeamSpectrum[DSP_BUFFER_LEN];
#endif // BEAMFORM END

#endif // LOGMEL END

int main()
{
    // SimState sim = {
    //     .angle = { .az = 40, .el = 30 },
    //     .array.pos = {
    //         { 0.0000000f, 0.1335750f, 0.0f },
    //         { 0.1270370f, 0.0412770f, 0.0f },
    //         { 0.0785130f, -0.108064f, 0.0f },
    //         { -0.075183f, -0.108064f, 0.0f },
    //         { -0.127037f, 0.0412770f, 0.0f },
    //     }
    // };
    // rng_seed_entropy(&R);
    rng_seed(&R, 100);
    sim_produce_frame(&R, &View, MicPositions, SourceDirection);

    // Fill first half of spectrum
    dsp_init_spectrum();
    dsp_compute_spectrum(View.frame, &Prev, &Spec);
    dsp_init_srp(&Grid, &MicPositions, &State);

    bool32 quit = false;

#ifdef LOGMEL
#ifndef BENCHMARK
    int vusart = open_vusart("/tmp/ttySIM0");
#endif

    uint16_t frame_idx = 0;
    uint32_t seq       = 0;
#endif

#ifdef BENCHMARK
    struct timespec last_time;
    clock_gettime(CLOCK_MONOTONIC, &last_time);
    uint64_t last_cycle_count = _rdtsc();
#endif

    while (!quit)
    {
        sim_produce_frame(&R, &View, MicPositions, SourceDirection);
        dsp_compute_spectrum(View.frame, &Prev, &Spec);

        // SRP-PHAT
        dsp_compute_srp(&State, &Spec, &Srp);
#ifndef LOGMEL
#ifndef BENCHMARK
        printf("azimuth: %.2f\televation: %.2f\n", Srp.azimuth, Srp.elevation);
#endif // NOT BENCHMARK
#endif // NOT LOGMEL

#ifdef LOGMEL
#ifdef BEAMFORM
        dsp_beamform_delay_sum(&Spec, &MicPositions, Srp.azimuth, Srp.elevation, BeamSpectrum);
        const float32_t* mel_input = BeamSpectrum;
#else
        const float32_t* mel_input = Spec.bins[0];
#endif
        dsp_compute_logmel_frame(Spec.scratch, mel_input, &Mel);
        uint8_t* out = MelPackets;
        uint8_t* cells;

        if (frame_idx == 0)
        {
            logmel_header_t* hdr = (logmel_header_t*)FirstPacket;
            *hdr                 = (logmel_header_t) {
                .magic     = LOGMEL_MAGIC,
                .seq       = seq,
                .azimuth   = Srp.azimuth,
                .elevation = Srp.elevation,
            };
            cells = FirstPacket + sizeof(logmel_header_t);
            for (uint32_t b = 0; b < NUM_MEL_BANDS; b++)
            {
                cells[b] = quantize_db(Mel.frame[b]);
            }
#ifndef BENCHMARK
            vusart_send(vusart, FirstPacket, sizeof(logmel_header_t) + NUM_MEL_BANDS);
#endif
        }
        else
        {
            cells = out;
            for (uint32_t b = 0; b < NUM_MEL_BANDS; b++)
            {
                cells[b] = quantize_db(Mel.frame[b]);
            }
#ifndef BENCHMARK
            vusart_send(vusart, cells, NUM_MEL_BANDS);
#endif
        }

        if (++frame_idx == NUM_FRAMES)
        {
            frame_idx = 0;
            seq++;
        }
#endif // LOGMEL END
#ifdef BENCHMARK
        struct timespec end_time;
        clock_gettime(CLOCK_MONOTONIC, &end_time);
        uint64_t end_cycle_count = _rdtsc();

        double elapsed_time_ms = (double)(end_time.tv_sec  - last_time.tv_sec)  * 1e3
                               + (double)(end_time.tv_nsec - last_time.tv_nsec) / 1e6;
        double mcpf = (double)(end_cycle_count - last_cycle_count) / 1e6;
        double fps = 1000.0 / elapsed_time_ms;

        printf("%.02fms/f, %.02ff/s, %.02fmc/f\r\n", elapsed_time_ms, fps, mcpf);

        clock_gettime(CLOCK_MONOTONIC, &last_time);
        last_cycle_count = _rdtsc();
#endif
#ifndef BENCHMARK
        // usleep(30840); // control the tx frequency
#endif
    }

    return 0;
}
