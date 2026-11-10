#include "app_entry.h"
#include "linker.h"

#include "ics52000.h"
#include "console.h"
#include "dsp.h"

#include <stdio.h>

#define LOGMEL
#define BEAMFORM
// #define REPORT_FRAMES

#ifdef REPORT_FRAMES
#include "clock.h"
#endif

#ifdef LOGMEL
#define LOGMEL_MAGIC    0x314C4D4C // "LML1": one packet per frame
#define LOGMEL_Q_SCALE  1.5f
#define LOGMEL_Q_OFFSET -100.0f

#define PACKED __attribute__((packed))

typedef struct
{
    uint32_t  magic;
    uint32_t  seq;
    float32_t azimuth;
    float32_t elevation;

} PacketHeader;

typedef struct PACKED
{
    PacketHeader header;
    uint8_t      cells[NUM_MEL_BANDS];
} QuantizedPacket;

/* Maps a float32 dB value to the 0–255 uint8_t range, with rounding and clamp*/
static inline uint8_t quantize_db(float32_t db)
{
    float32_t byte_value = (db - LOGMEL_Q_OFFSET) * LOGMEL_Q_SCALE;
    if (byte_value < 0.0f) byte_value   = 0.0f;
    if (byte_value > 255.0f) byte_value = 255.0f;
    return (uint8_t)(byte_value + 0.5f);
}

global Logmel          Mel    DTCM;
global QuantizedPacket Packet DTCM;
    #ifdef BEAMFORM
global float32_t BeamSpectrum[DSP_BUFFER_LEN] DTCM;
    #endif // BEAMFORM
#endif // LOGMEL

global AudioFrameView  View   DTCM;
global PrevAudioFrame  Prev   DTCM;
global FFT_Spectrum    Spec   RAM1; // slight penalty (~0.10ms) for placing
global SRP_State       State  RAM1; // these two in RAM1 instead of DTCM
global SRP_PHAT        Srp    DTCM;

global const MicArray MicPositions = { {
    { -0.078513f, -0.108064f, 0.0f }, // mic 0: lower left
    {  0.078513f, -0.108064f, 0.0f }, // mic 1: lower right
    {  0.127037f,  0.041277f, 0.0f }, // mic 2: right
    {  0.000000f,  0.133575f, 0.0f }, // mic 3: top
    { -0.127037f,  0.041277f, 0.0f }, // mic 4: left
} };
global const SRP_Grid Grid = {
    .az_start = -45.0f, .az_step = 1.0f,
    .el_start = -45.0f, .el_step = 1.0f
};

void app_main(void)
{
    ics52000_init();
    dsp_init_spectrum();
    dsp_init_srp(&Grid, &MicPositions, &State);
    console_init();

#ifdef REPORT_FRAMES
    FRAME_TIMER_INIT("Frame timer");
#endif

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
    #ifndef REPORT_FRAMES
        printf("azimuth: %.2f\televation: %.2f\r\n", Srp.azimuth, Srp.elevation);
    #endif // !(LOGMEL || REPORT_FRAMES)
#endif

#ifdef LOGMEL
    #ifdef BEAMFORM
        dsp_beamform_delay_sum(&Spec, &MicPositions, Srp.azimuth, Srp.elevation, BeamSpectrum);
        const float32_t* mel_input = BeamSpectrum;
    #else
        const float32_t* mel_input = Spec.bins[0];
    #endif
        dsp_compute_logmel_frame(Spec.scratch, mel_input, &Mel);

        if (!console_busy())
        {
            PacketHeader header = {
                .magic     = LOGMEL_MAGIC,
                .seq       = View.seq,
                .azimuth   = Srp.azimuth,
                .elevation = Srp.elevation
            };
            Packet.header = header;
            for (uint32_t b = 0; b < NUM_MEL_BANDS; b++)
            {
                Packet.cells[b] = quantize_db(Mel.frame[b]);
            }
    #ifndef REPORT_FRAMES
            console_send_async(&Packet, sizeof(Packet));
    #endif // !REPORT_FRAMES
        }
#endif // LOGMEL

#ifdef REPORT_FRAMES
        // NOTE: Loop should hit: 32.00ms/f, 31.25f/s, 17.60mc/f
        // - if it isn't, we are dropping audio frames!
        FRAME_TIMER_LAP();
#endif // REPORT_FRAMES

        last_seq = View.seq;
    }
}
