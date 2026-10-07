// Simple SRP-PHAT test with two microphones
// Sends one packet per audio hop over UART: header + SRP map
// View it with tools/srp_viewer.py

#include "app_entry.h"
#include "audio_config.h"
#include "console.h"
#include "ics52000.h"
#include "spectrum.h"
#include "srp-phat.h"

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

// Wire format - tools/srp_viewer.py must match
#define SRP_PACKET_MAGIC 0x50505253 // "SRPP" on the wire

typedef struct
{
    uint32_t  magic;
    uint32_t  seq;          // increments per packet, used to detect drops
    grid_t    grid;
    doa_t     doa;
    uint8_t   reserved[20]; // pads the header to 64 bytes (for convenience)
    float32_t map[SRP_AZIMUTH_DIRECTIONS];
} srp_packet_t;

// MDMA writes doublewords, so the packet must be a multiple of 8 bytes
_Static_assert(sizeof(srp_packet_t) == 64 + sizeof(float32_t) * SRP_AZIMUTH_DIRECTIONS, "srp_packet_t has padding");
_Static_assert(sizeof(srp_packet_t) % 8 == 0, "srp_packet_t must be a multiple of 8 bytes");

#define DTCM __attribute__((section(".dtcm_buf"), aligned(32)))
#define D2   __attribute__((section(".d2_buf"), aligned(32)))

static srp_t        g_srp DTCM;
static srp_packet_t g_packet DTCM;
static uint8_t      g_uart_staging[2][sizeof(srp_packet_t)] D2; // ping-pong halves for console

void app_main(void)
{
    // Array of pointers to audio frame
    float32_t* frame[AUDIO_MIC_COUNT];

    // Pointer to array containing spectrum samples
    const float32_t(*spectrum)[SPECTRUM_FLOATS];

    UART_DMA_start((uint32_t)g_uart_staging, sizeof(srp_packet_t));
    spectrum_init();
    ics52000_start();

    srp_init(&g_srp, &MIC_ARRAY, &GRID);

    g_packet.magic = SRP_PACKET_MAGIC;
    g_packet.grid  = GRID;

    while (1)
    {
        if (ics52000_read(frame))
        {
			// Puts the shit into spectrum
            spectrum_compute(frame, &spectrum);

            // computes azimuth-elevation (direction of arrival)
			g_packet.doa = srp_compute(&g_srp, spectrum);

            memcpy(g_packet.map, g_srp.map, sizeof(g_packet.map));
            ++g_packet.seq;
            UART_MDMA_send_buffer((uint8_t*)&g_packet, sizeof(g_packet));
        }
    }
}
