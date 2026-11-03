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
    { -0.078513f, -0.108064f, 0.0f }, // mic 0: lower left
    {  0.078513f, -0.108064f, 0.0f }, // mic 1: lower right
    {  0.127037f,  0.041277f, 0.0f }, // mic 2: right
    {  0.000000f,  0.133575f, 0.0f }, // mic 3: top
    { -0.127037f,  0.041277f, 0.0f }, // mic 4: left
} };

global PrevAudioFrame Prev;
global FFT_Spectrum Spec;

global SRP_PHAT Srp;
global SRP_State State;
global const SRP_Grid Grid = {
    .az_start = -45.0f, .az_step = 1.0f,
    .el_start = -45.0f, .el_step = 1.0f
};

#ifdef LOGMEL

#define LOGMEL_MAGIC               0x314C4D4C // "LML1": one packet per frame
#define LOGMEL_Q_SCALE             1.5f
#define LOGMEL_Q_OFFSET            -100.0f
static inline uint8_t quantize_db(float32_t db)
{
    float32_t byte_value = (db - LOGMEL_Q_OFFSET) * LOGMEL_Q_SCALE;
    if (byte_value < 0.0f) byte_value   = 0.0f;
    if (byte_value > 255.0f) byte_value = 255.0f;
    return (uint8_t)(byte_value + 0.5f);
}

typedef struct {
    uint32_t magic;       // LOGMEL_MAGIC
    uint32_t seq;         // increments every frame; used to detect drops
    float32_t azimuth;
    float32_t elevation;
} logmel_header_t;

typedef struct {
    logmel_header_t header;
    uint8_t         cells[NUM_MEL_BANDS];
} logmel_packet_t;

global Logmel          Mel;
global logmel_packet_t Packet;

    #ifdef BEAMFORM
global float32_t BeamSpectrum[DSP_BUFFER_LEN];
    #endif // BEAMFORM END

#endif // LOGMEL END

int main()
{
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

    uint32_t seq = 0;
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
        Packet.header = (logmel_header_t) {
            .magic     = LOGMEL_MAGIC,
            .seq       = seq++,
            .azimuth   = Srp.azimuth,
            .elevation = Srp.elevation,
        };
        for (uint32_t b = 0; b < NUM_MEL_BANDS; b++)
        {
            Packet.cells[b] = quantize_db(Mel.frame[b]);
        }
    #ifndef BENCHMARK
        vusart_send(vusart, &Packet, sizeof(Packet));
    #endif
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
        last_cycle_count = end_cycle_count;
#endif
#ifndef BENCHMARK
        usleep(30840); // control the tx frequency
#endif
    }

    return 0;
}
