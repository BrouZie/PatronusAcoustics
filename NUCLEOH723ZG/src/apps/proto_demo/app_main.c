#include "app_entry.h"
#include "linker.h"

#include "ics52000.h"
#include "console.h"
#include "dsp.h"

#include <stdio.h>

#define LOGMEL
#define BEAMFORM
// #define BENCHMARK

#ifdef BENCHMARK
#include "clock.h"
#endif

#ifdef LOGMEL

#include "main.h"
#include "mpu.h"
#include "usart.h"

// LOGMEL SHIT START
#define LOGMEL_FRAME_DTCM_BUF     ".dtcm_buf" // -> DTCMRAM
#define LOGMEL_MAGIC               0x314C4D4C // "LML1": one packet per frame
#define LOGMEL_Q_SCALE             1.5f
#define LOGMEL_Q_OFFSET            -100.0f

typedef struct __attribute__((packed)) {
    uint32_t magic;       // LOGMEL_MAGIC
    uint32_t seq;         // increments every frame; used to detect drops
    float32_t azimuth;
    float32_t elevation;
} logmel_header_t;

typedef struct __attribute__((packed)) {
    logmel_header_t header;
    uint8_t         cells[NUM_MEL_BANDS];
} logmel_packet_t;

// MDMA writes doublewords, so every send must be a multiple of 8 bytes
_Static_assert(sizeof(logmel_packet_t) % 8 == 0, "logmel_packet_t must be a multiple of 8 bytes");

static uint8_t  _active_write_buf  = 0;

// Ping-pong, so the MDMA can still be reading one packet while the next is built
static logmel_packet_t _logmel_packet[2] __attribute__((section(LOGMEL_FRAME_DTCM_BUF), aligned(32)));
static uint8_t _logmel_tx[2][sizeof(logmel_packet_t)] DMA_BUF;

global Logmel Mel DTCM;

/* Maps a float32 dB value to the 0–255 uint8_t range, with rounding and clamp*/
static inline uint8_t quantize_db(float32_t db)
{
    float32_t byte_value = (db - LOGMEL_Q_OFFSET) * LOGMEL_Q_SCALE;
    if (byte_value < 0.0f) byte_value   = 0.0f;
    if (byte_value > 255.0f) byte_value = 255.0f;
    return (uint8_t)(byte_value + 0.5f);
}

    #ifdef BEAMFORM
global float32_t BeamSpectrum[DSP_BUFFER_LEN] DTCM;
    #endif // BEAMFORM END

#endif // LOGMEL END

global const MicArray MicPositions = { {
    { -0.078513f, -0.108064f, 0.0f }, // mic 0: lower left
    {  0.078513f, -0.108064f, 0.0f }, // mic 1: lower right
    {  0.127037f,  0.041277f, 0.0f }, // mic 2: right
    {  0.000000f,  0.133575f, 0.0f }, // mic 3: top
    { -0.127037f,  0.041277f, 0.0f }, // mic 4: left
} };

// TODO: Benchmark different placements and
// look for ways to reduce memory footprint
global AudioFrameView View  DTCM;
global PrevAudioFrame Prev  DTCM;
global FFT_Spectrum   Spec  RAM1; // slight penalty (~0.10ms) for placing 
global SRP_State      State RAM1; // these two in RAM1 instead of DTCM
global SRP_PHAT       Srp   DTCM;
global const SRP_Grid Grid = {
    .az_start = -45.0f, .az_step = 1.0f,
    .el_start = -45.0f, .el_step = 1.0f
};

void app_main(void)
{
    ics52000_init();
    dsp_init_spectrum();
    dsp_init_srp(&Grid, &MicPositions, &State);

#ifndef LOGMEL
    console_init();
#endif // NOT LOGMEL
#ifdef LOGMEL
    #ifndef BENCHMARK
    UART_DMA_start((uint32_t)_logmel_tx, sizeof(_logmel_tx[0]));
    #endif

    uint32_t seq = 0;
#endif // LOGMEL

    uint32_t last_seq = 0;

#ifdef BENCHMARK
    console_init();
    clock_cycles_init();
    uint32_t last_cycle_count = clock_cycles();

    float32_t elapsed_time, fps, mcpf;
#endif

    while (true)
    {
        // Skip until a new half has landed (also skips seq == 0, before any data)
        if (!ics52000_read(&View) || View.seq == last_seq)
        {
            continue;
        }
        dsp_compute_spectrum(View.frame, &Prev, &Spec);
        dsp_compute_srp(&State, &Spec, &Srp);

#ifndef LOGMEL
    #ifndef BENCHMARK
        printf("azimuth: %.2f\televation: %.2f\r\n", Srp.azimuth, Srp.elevation);
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
        logmel_packet_t* packet = &_logmel_packet[_active_write_buf];
        packet->header = (logmel_header_t) {
            .magic     = LOGMEL_MAGIC,
            .seq       = seq++,
            .azimuth   = Srp.azimuth,
            .elevation = Srp.elevation,
        };
        for (uint32_t b = 0; b < NUM_MEL_BANDS; b++)
        {
            packet->cells[b] = quantize_db(Mel.frame[b]);
        }
    #ifndef BENCHMARK
        UART_MDMA_send_buffer(packet, sizeof(*packet));
    #endif
        _active_write_buf ^= 1U;
#endif // LOGMEL
#ifdef BENCHMARK
        uint32_t end_cycle_count = clock_cycles();
        uint32_t elapsed_cycles = end_cycle_count - last_cycle_count;
        float hz = clock_hz();

        elapsed_time = (float)elapsed_cycles * 1000.0f / hz;
        fps          = hz / (float)elapsed_cycles;
        mcpf         = (float)elapsed_cycles / 1e6f;

        // NOTE: One event loop should consistently hit fs / AUDIO_SAMPLES => 16kHz / 512 = 31.25 fps
        // DSP pipeline should ideally have a higher fps rate ~25% higher (to provide some headroom).
        printf("%.02fms/f, %.02ff/s, %.02fmc/f\r\n", elapsed_time, fps, mcpf);

        last_cycle_count = clock_cycles();
#endif
        last_seq = View.seq;
    }
}
