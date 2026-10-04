// Simple SRP-PHAT test with two microphones
// Prints continuous azimuth, elevation (fixed at 90)
// and power over UART

#include "app_entry.h"
#include "audio_config.h"
#include "console.h"
#include "ics52000.h"
#include "spectrum.h"
#include "srp-phat.h"

#include <stdio.h>

// 1D microphone array with a ~12cm gap
static const vec3_t MIC_POSITIONS[AUDIO_MIC_COUNT] = {
    { -0.06f, 0.0f, 0.0f },
    { 0.06f, 0.0f, 0.0f },
};
static const mic_array_t MIC_ARRAY = { .mic = MIC_POSITIONS, .count = AUDIO_MIC_COUNT };

// The grid controls the resolution of out scan - the starting
// point of our grid search, the step size and how many steps
static const grid_t GRID = {
    .az0 = 30.0f, .az_step = 1.0f, .az_steps = SRP_AZIMUTH_DIRECTIONS,
    .el0 = 90.0f, .el_step = 1.0f, .el_steps = 1,
};

#define DTCM __attribute__((section(".dtcm_buf"), aligned(32)))

static srp_t g_srp DTCM;

void app_main(void)
{
    // Array of pointers to audio frame
    float32_t* frame[AUDIO_MIC_COUNT];

    // Pointer to array containing spectrum samples
    const float32_t(*spectrum)[SPECTRUM_FLOATS];

    console_init();
    spectrum_init();
    ics52000_start();

    srp_init(&g_srp, &MIC_ARRAY, &GRID);

    while (1)
    {
        if (ics52000_read(frame))
        {
			// Puts the shit into spectrum
            spectrum_compute(frame, &spectrum);

            // computes azimuth-elevation (direction of arrival)
			doa_t doa = srp_compute(&g_srp, spectrum);

			printf("az %.1f el %.1f power %.3f\r\n", doa.az, doa.el, doa.power);
        }
    }
}
