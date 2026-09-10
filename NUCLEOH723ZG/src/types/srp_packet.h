#ifndef SRP_PACKET_H
#define SRP_PACKET_H

// ============================================================================
// Wire format for one SRP-PHAT map leaving the board over USART.
//
// A 64-byte header followed by az_steps * el_steps float32 cells, AZIMUTH
// MAJOR: cell (a, e) is at index a * el_steps + e.
//
// The header carries the grid geometry and both detection figures, so the host
// viewer configures its own axes and thresholds from the stream rather than
// duplicating constants that can drift out of step with the firmware. There
// are no framing bytes -- the reader syncs on SRP_PACKET_MAGIC, which on the
// wire reads as the ASCII "SRPP".
//
// LEAF HEADER: no HAL, no function declarations, no module headers.
// ============================================================================

#include <arm_math_types.h>
#include <stdint.h>

#define SRP_PACKET_MAGIC   0x50505253U // "SRPP" little-endian
#define SRP_PACKET_VERSION 3U

typedef struct __attribute__((packed))
{
    uint32_t magic;
    uint16_t version;
    uint16_t mic_count;

    uint16_t az_steps;
    uint16_t el_steps;

    float32_t az_start_deg;
    float32_t az_step_deg;
    float32_t el_start_deg;
    float32_t el_step_deg;

    /* Counts AUDIO frames, not packets sent. The viewer divides by the sender's
     * decimation to tell "we only stream every Nth map" apart from "packets are
     * being dropped". */
    uint32_t frame_index;

    float32_t peak_az_deg;
    float32_t peak_el_deg;

    /* The two detection figures and the thresholds they were judged against.
     * coherence says the bearing is trustworthy, level says there was anything
     * worth pointing at; see src/dsp/srp-phat.h. */
    float32_t coherence;
    float32_t level_db;
    float32_t gate_coherence;
    float32_t gate_level_db;

    uint16_t detected;  // 0 or 1
    uint16_t band_bins; // FFT bins in the SRP band -- lets the host place the
                        // coherent (M^2 * bins) and incoherent (M * bins)
                        // reference levels on the same axis as the map
    uint32_t reserved;
} srp_packet_header_t;

_Static_assert(sizeof(srp_packet_header_t) == 64,
               "srp_packet_header_t must stay 64 bytes -- the viewer parses it by offset");

#endif
