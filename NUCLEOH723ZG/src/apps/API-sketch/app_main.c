#include "app_entry.h"

#include "linker.h"
#include "ics52000.h"
#include "console.h"

#include "dsp.h"

#define BEAMFORM
#define SRP_ONLY

#ifdef SRP_ONLY
#include <stdio.h>
#endif

#ifdef REPORT_FRAMES
#include "clock.h"
#endif

#define PACKED __attribute__((packed))

// NOTE: The packet size should not exceed 13 421 bytes (at a baudrate of 4194304)
// Baudrate / frame rate = max transfer per frame
typedef struct PACKED
{
    uint32_t  magic;
    uint32_t  seq;
#ifdef X86_DEBUG
    int16_t   pcm[MIC_COUNT][AUDIO_SAMPLES];
#endif
    float32_t mel[NUM_MEL_BANDS];
    float32_t azimuth;
    float32_t elevation;
} Full_Packet;

global AudioFrameView View                         DTCM;
global PrevAudioFrame Prev                         DTCM;
global FFT_Spectrum   Spec                         RAM1;
global SRP_State      State                        RAM1;
global SRP_PHAT       Srp                          DTCM;
global Logmel         Mel                          DTCM;
global float32_t      BeamSpectrum[DSP_BUFFER_LEN] DTCM;
global Full_Packet    Packet                       RAM1;


// NOTE: SRP_Grid and MicArray will be dropped/removed eventually, as
// they could be defined at compiletime in headers instead.
// This would eliminate most if not all of the srp_init stuff.
global const SRP_Grid Grid = {
    .az_start = -45.0f, .az_step = 1.0f,
    .el_start = -45.0f, .el_step = 1.0f
};
global const MicArray MicPositions = { {
    { -0.078513f, -0.108064f, 0.0f }, // mic 0: lower left
    {  0.078513f, -0.108064f, 0.0f }, // mic 1: lower right
    {  0.127037f,  0.041277f, 0.0f }, // mic 2: right
    {  0.000000f,  0.133575f, 0.0f }, // mic 3: top
    { -0.127037f,  0.041277f, 0.0f }, // mic 4: left
} };

void pack_full(const SRP_PHAT* srp, const Logmel* mel, Full_Packet* packet)
{
    packet->magic     = 0xDEADBEA7;
#ifdef X86_DEBUG
    memcpy(packet->pcm, View.frame->pcm, sizeof(View.frame->pcm));
#endif
    memcpy(packet->mel, mel, sizeof(*mel));
    packet->azimuth   = srp->azimuth;
    packet->elevation = srp->elevation;
}

void app_main(void)
{
    ics52000_init();
    console_init();
    dsp_init_spectrum();
    dsp_init_srp(&Grid, &MicPositions, &State); // NOTE: Might be redundant/not needed upon
                                                // deletion of SRP_Grid and MicArray.
    uint32_t last_seq = 0;

#ifdef REPORT_FRAMES
    FRAME_TIMER_INIT("Report");
#endif

    while (true)
    {
        if (!ics52000_read(&View) || View.seq == last_seq)
        {
            continue;
        }

        dsp_compute_spectrum(View.frame, &Prev, &Spec);
        dsp_compute_srp(&State, &Spec, &Srp);
#ifdef SRP_ONLY
        printf("x: %.2f\ty: %.2f\r\n", Srp.azimuth, Srp.elevation);
#else
    #ifdef BEAMFORM
        dsp_beamform_delay_sum(&Spec, &MicPositions, Srp.azimuth, Srp.elevation, BeamSpectrum);
        const float32_t* mel_input = BeamSpectrum;
    #else
        const float32_t* mel_input = Spec.bins[0];
    #endif
        dsp_compute_logmel_frame(Spec.scratch, mel_input, &Mel);

    #ifndef REPORT_FRAMES
        if (!console_busy())
        {
            pack_full(&Srp, &Mel, &Packet);
            console_send_async(&Packet, sizeof(Packet));
        }
    #endif // !REPORT_FRAMES

    #ifdef REPORT_FRAMES
    FRAME_TIMER_LAP();
    #endif
#endif
        last_seq = View.seq;
    }
}
