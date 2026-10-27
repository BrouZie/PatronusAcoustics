#include "platform.h"
#include "dsp.h"

#include <stdint.h>
#include <stdio.h>

global rng_t R;
global AudioViewFrame View;
global AngleDeg SourceDirection = {
    .azimuth   = -45.0f,
    .elevation = 30.0f
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

global Logmel Mel;

int main()
{
    // rng_seed_entropy(&R);
    rng_seed(&R, 100);
    populate_frame(&R, &View, MicPositions, SourceDirection);

    // Fill first half of spectrum
    dsp_init_spectrum();
    dsp_compute_spectrum(View.frame, &Prev, &Spec);

    bool32 quit = false;
    int do_something = 0;

    while (!quit)
    {
        if (do_something % 100 == 0)
        {
            SourceDirection.azimuth += 0.1f;
            SourceDirection.elevation += 0.1f;
        }
        populate_frame(&R, &View, MicPositions, SourceDirection);
        dsp_compute_spectrum(View.frame, &Prev, &Spec);

        // SRP-PHAT
        dsp_init_srp(&Grid, &MicPositions, &State);
        dsp_compute_srp(&State, &Spec, &Srp);
        printf("azimuth: %.2f\televation: %.2f\n", Srp.azimuth, Srp.elevation);

        // Logmel   
#define BEAMFORM
#ifdef BEAMFORM
        float32_t beam_spectrum[DSP_BUFFER_LEN];
        dsp_beamform_ds(&Spec, &MicPositions, Srp.azimuth, Srp.elevation, beam_spectrum);
        const float32_t* mel_input = beam_spectrum;
#else
        const float32_t* mel_input = Spec.bins[0];
#endif
        dsp_compute_logmel_frame(Spec.scratch, mel_input, &Mel);
    }

    return 0;
}
