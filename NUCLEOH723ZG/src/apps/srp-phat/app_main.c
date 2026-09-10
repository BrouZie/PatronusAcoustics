#include "app_entry.h"
#include "audio_config.h"
#include "console.h"
#include "ics52000.h"
#include "spectrum.h"
#include "srp-phat.h"
#include "srp_packet.h"
#include <stdio.h>

/*
 * Live bearing estimation.
 *
 *   ics52000_read()  -- one 50%-overlapped frame per microphone
 *   spectrum_compute() -- DC removal, Hann, real FFT (shared with log-mel)
 *   srp_phat_compute() -- steer the array over the grid, find the peak
 *   USART           -- the whole map, for tools/srp_viewer.py
 *
 * The map is the useful thing to look at during bring-up, not just the peak:
 * a wrong bearing and a genuinely ambiguous one look identical in a single
 * az/el pair, and completely different as a picture.
 */

#define SRP_DTCM_BUF ".dtcm_buf"

/* Frames between transmitted maps, derived rather than guessed.
 *
 * A packet is 48 B of header plus 4 B per direction, and frames land at
 * AUDIO_SAMPLE_RATE_HZ / ICS_HOP_SAMPLES (93.75/s at 48 kHz with a 512 hop).
 * Sending every frame would need packet_bytes * 93.75 B/s, which for the full
 * 72x19 grid is 517 kB/s against a 92 kB/s link. So decimate to fit a budget.
 *
 * A one-elevation-row grid, which is all a linear pair can use, comes out at
 * every frame; the full sphere grid comes out at every 10th. Both without a
 * constant that has to be remembered when the grid changes. */
/* The USART MDMA refuses a length that is not a multiple of
 * CONSOLE_TX_ALIGN_BYTES, so the packet carries trailing padding to reach one.
 * The viewer never reads it: the header states the map size, and the reader
 * resynchronises on the magic word, so the padding is simply skipped. */
#define SRP_PACKET_PAYLOAD (sizeof(srp_packet_header_t) + sizeof(float32_t) * SRP_DIRECTIONS)
#define SRP_PACKET_PAD     (CONSOLE_TX_ALIGN_BYTES - (SRP_PACKET_PAYLOAD % CONSOLE_TX_ALIGN_BYTES))
#define SRP_PACKET_BYTES   (SRP_PACKET_PAYLOAD + SRP_PACKET_PAD)
#define SRP_FRAMES_PER_SEC (AUDIO_SAMPLE_RATE_HZ / ICS_HOP_SAMPLES)

/* 8N1 puts 10 bits on the wire per byte; aim at 60% of the link so the send
 * always finishes well before the next one is due. */
#define SRP_LINK_BYTES_PER_SEC (921600U / 10U)
#define SRP_STREAM_BUDGET      ((SRP_LINK_BYTES_PER_SEC * 6U) / 10U)

#define SRP_STREAM_EVERY_N_FRAMES                                                                                      \
    (((SRP_PACKET_BYTES * SRP_FRAMES_PER_SEC + SRP_STREAM_BUDGET - 1U) / SRP_STREAM_BUDGET) < 1U                       \
         ? 1U                                                                                                          \
         : ((SRP_PACKET_BYTES * SRP_FRAMES_PER_SEC + SRP_STREAM_BUDGET - 1U) / SRP_STREAM_BUDGET))

/* The MDMA source must live in DTCM. The D-cache is on and no MPU region
 * covers .d1_buf, so a packet staged there would sit in cache while the MDMA
 * read stale SRAM -- see LOGMEL_STREAM_FIXES.md section 4. */
static struct
{
    srp_packet_header_t header;
    float32_t           map[SRP_DIRECTIONS];
    uint8_t             pad[SRP_PACKET_PAD];
} _packet __attribute__((section(SRP_DTCM_BUF), aligned(32)));

_Static_assert(sizeof(_packet) % CONSOLE_TX_ALIGN_BYTES == 0,
               "packet length must suit the USART MDMA -- see CONSOLE_TX_ALIGN_BYTES");

_Static_assert(AUDIO_MIC_COUNT >= 2,
               "srp-phat needs at least two microphones -- set AUDIO_MIC_COUNT in src/config/audio_config.h");

_Static_assert(sizeof(_packet) <= CONSOLE_STAGING_BYTES,
               "SRP packet is larger than one RAM_D2 staging half -- coarsen the grid or enlarge _d2_output");

static void _fill_header(const srp_doa_t* doa, uint32_t frame_index)
{
    _packet.header.magic     = SRP_PACKET_MAGIC;
    _packet.header.version   = SRP_PACKET_VERSION;
    _packet.header.mic_count = AUDIO_MIC_COUNT;

    _packet.header.az_steps     = SRP_AZ_STEPS;
    _packet.header.el_steps     = SRP_EL_STEPS;
    _packet.header.az_start_deg = SRP_AZ_START_DEG;
    _packet.header.az_step_deg  = SRP_AZ_STEP_DEG;
    _packet.header.el_start_deg = SRP_EL_START_DEG;
    _packet.header.el_step_deg  = SRP_EL_STEP_DEG;

    _packet.header.frame_index = frame_index;
    _packet.header.peak_az_deg = doa->azimuth_deg;
    _packet.header.peak_el_deg = doa->elevation_deg;

    _packet.header.coherence      = doa->coherence;
    _packet.header.level_db       = doa->level_db;
    _packet.header.gate_coherence = doa->coherence_floor + SRP_DETECT_MARGIN;
    _packet.header.gate_level_db  = SRP_DETECT_LEVEL_DB;

    _packet.header.detected  = doa->detected ? 1U : 0U;
    _packet.header.band_bins = SRP_BAND_BINS;
}

void app_main(void)
{
    // Array of pointers to audio frame
    float32_t* frame[AUDIO_MIC_COUNT];

    // Pointer to array containing spectrum samples
    const float32_t(*spectrum)[SPECTRUM_FLOATS];

    srp_doa_t doa;
    uint32_t  frame_index = 0;

    UART_DMA_start();
    spectrum_init();
    srp_phat_init();
    ics52000_start();

    // console_init(); // NOTE: COMMENT OUT IF USING USART TX

    while (1)
    {
        if (ics52000_read(frame))
        {
            spectrum_compute(frame, &spectrum);

            /* Written straight into the packet -- the map is 5.5 KB and there
             * is no reason to build it somewhere else and copy it here. */
            srp_phat_compute(spectrum, _packet.map, &doa);

            frame_index++;

            if (frame_index % SRP_STREAM_EVERY_N_FRAMES == 0)
            {
				_fill_header(&doa, frame_index);
            // printf("[%c] az %6.1f  el %5.1f  coh %4.2f  level %6.1f dBFS\r\n", doa.detected ? 'x' : ' ',
            //        doa.azimuth_deg, doa.elevation_deg, doa.coherence, doa.level_db);
				UART_MDMA_send_buffer((float32_t*)&_packet, sizeof(_packet));
            }
        }
    }
}
