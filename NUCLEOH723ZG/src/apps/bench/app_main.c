#include "app_entry.h"

#include "linker.h"
#include "ics52000.h"
#include "console.h"
#include "dsp.h"

#define BENCHMARK
#ifdef BENCHMARK
#include "arm_bench.h"
#endif

global AudioFrameView View  DTCM;
global PrevAudioFrame Prev  DTCM;
global FFT_Spectrum   Spec  RAM1;
global SRP_State      State RAM1;
global SRP_PHAT       Srp   DTCM;
global Logmel         Mel   DTCM;
global float32_t      BeamSpectrum[DSP_BUFFER_LEN] DTCM;
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

void app_main(void)
{
    ics52000_init();
    console_init();
    dsp_init_spectrum();
    dsp_init_srp(&Grid, &MicPositions, &State);

    BENCH_SETUP("DSP");

    uint32_t last_seq;

    while (true)
    {
        // Skip until a new half has landed (also skips seq == 0, before any data)
        if (!ics52000_read(&View) || View.seq == last_seq)
        {
            continue;
        }

        for (int i = 0; i < 100; ++i)
        {
            BENCH_BEGIN(DSP);
            dsp_compute_spectrum(View.frame, &Prev, &Spec);
            dsp_compute_srp(&State, &Spec, &Srp);
            dsp_beamform_delay_sum(&Spec, &MicPositions, Srp.azimuth, Srp.elevation, BeamSpectrum);
            const float32_t* mel_input = BeamSpectrum;
            dsp_compute_logmel_frame(Spec.scratch, mel_input, &Mel);
            BENCH_END(DSP);
        }
        bench_report();

        last_seq = View.seq;
    }
}
