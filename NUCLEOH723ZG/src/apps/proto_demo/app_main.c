#include "app_entry.h"
#include "linker.h"

#include "ics52000.h"
#include "console.h"
#include "dsp.h"

#include <stdio.h>

#define LOGMEL
#define BEAMFORM

#ifdef LOGMEL

#include "main.h"
#include "mpu.h"
#include "usart.h"

// LOGMEL SHIT START
#define LOGMEL_FRAME_DTCM_BUF     ".dtcm_buf" // -> DTCMRAM
#define LOGMEL_SPECTOGRAM_RAM_BUF ".d1_buf"   // -> RAM_D1
#define LOGMEL_MAGIC               0x4C454D4C
#define LOGMEL_Q_SCALE             1.5f
#define LOGMEL_Q_OFFSET            -100.0f
#define NUM_FRAMES                 61

typedef struct __attribute__((packed)) {
    uint32_t magic;       // LOGMEL_MAGIC
    uint32_t seq;         // increments every image; used to detect drops
    float32_t azimuth;
    float32_t elevation;
} logmel_header_t;

static uint8_t  _active_write_buf  = 0;

/* Header is only needed for the first frame; omit it from the ping-pong buffer. */
static uint8_t _logmel_first_frame[sizeof(logmel_header_t) + NUM_MEL_BANDS]
    __attribute__((section(LOGMEL_FRAME_DTCM_BUF), aligned(32)));
static uint8_t _logmel_frame[2][NUM_MEL_BANDS] __attribute__((section(LOGMEL_FRAME_DTCM_BUF), aligned(32)));
static uint8_t _logmel_spectogram[2][sizeof(logmel_header_t) + NUM_FRAMES * NUM_MEL_BANDS]
    __attribute__((section(LOGMEL_SPECTOGRAM_RAM_BUF), aligned(32)));

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
    { 0.0000000f, 0.1335750f, 0.0f },
    { 0.1270370f, 0.0412770f, 0.0f },
    { 0.0785130f, -0.108064f, 0.0f },
    { -0.075183f, -0.108064f, 0.0f },
    { -0.127037f, 0.0412770f, 0.0f },
} };

// TODO: Benchmark different placements and
// look for ways to reduce memory footprint
global AudioFrameView View;
global PrevAudioFrame Prev DTCM; // NOTE: Interesting to benchmark

global FFT_Spectrum Spec RAM1;

global SRP_PHAT       Srp   DTCM;  // Storing wasteful things? Can it be moved
global SRP_State      State RAM1; // This one is HUUUGE!
global const SRP_Grid Grid = {
    .az_start = -50.0f, .az_step = 2.0f,
    .el_start = -50.0f, .el_step = 2.0f
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
    UART_DMA_start((uint32_t)_logmel_spectogram, sizeof(_logmel_spectogram[0]));

    uint16_t frame_idx = 0;
    uint32_t seq       = 0;
#endif // LOGMEL

    uint32_t last_seq = 0;

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
        printf("azimuth: %.2f\televation: %.2f\r\n", -Srp.azimuth, -Srp.elevation);
#endif // NOT LOGMEL

#ifdef LOGMEL
#ifdef BEAMFORM
        dsp_beamform_delay_sum(&Spec, &MicPositions, Srp.azimuth, Srp.elevation, BeamSpectrum);
        const float32_t* mel_input = BeamSpectrum;
#else
        const float32_t* mel_input = Spec.bins[0];
#endif
        dsp_compute_logmel_frame(Spec.scratch, mel_input, &Mel);
        uint8_t* out = _logmel_frame[_active_write_buf];
        uint8_t* cells;

        if (frame_idx == 0)
        {
            logmel_header_t* hdr = (logmel_header_t*)_logmel_first_frame;
            *hdr                 = (logmel_header_t) {
                .magic     = LOGMEL_MAGIC,
                .seq       = seq,
                .azimuth   = Srp.azimuth,
                .elevation = Srp.elevation,
            };
            cells = _logmel_first_frame + sizeof(logmel_header_t);
            for (uint32_t b = 0; b < NUM_MEL_BANDS; b++)
            {
                cells[b] = quantize_db(Mel.frame[b]);
            }
            UART_MDMA_send_buffer(_logmel_first_frame, sizeof(logmel_header_t) + NUM_MEL_BANDS);
        }
        else
        {
            cells = out;
            for (uint32_t b = 0; b < NUM_MEL_BANDS; b++)
            {
                cells[b] = quantize_db(Mel.frame[b]);
            }
            UART_MDMA_send_buffer(cells, NUM_MEL_BANDS);
            _active_write_buf ^= 1U;
        }

        if (++frame_idx == NUM_FRAMES)
        {
            frame_idx = 0;
            seq++;
        }
#endif // LOGMEL
        ++last_seq;
    }
}
