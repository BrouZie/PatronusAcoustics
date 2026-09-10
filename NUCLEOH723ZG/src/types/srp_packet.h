#ifndef SRP_PACKET_H
#define SRP_PACKET_H

// ============================================================================
// Wire format for one SRP-PHAT map leaving the board over USART: this header,
// then az_steps * el_steps float32 cells, AZIMUTH MAJOR -- cell (a, e) is at
// index a * el_steps + e.
//
// The header carries the grid geometry and both detection figures so the host
// viewer configures itself from the stream instead of duplicating constants
// that can drift. There are no framing bytes; the reader syncs on
// SRP_PACKET_MAGIC, which reads as the ASCII "SRPP" on the wire.
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

    // Counts AUDIO frames, not packets, so the viewer can tell decimation from drops
    uint32_t frame_index;

    float32_t peak_az_deg;
    float32_t peak_el_deg;

    // The two detection figures and the gates they were judged against

    float32_t coherence;
    float32_t level_db;
    float32_t gate_coherence;
    float32_t gate_level_db;

    uint16_t detected;  // 0 or 1
    uint16_t band_bins; // lets the host place the M*bins and M^2*bins reference
                        // levels on the same axis as the map
    uint32_t reserved;
} srp_packet_header_t;

_Static_assert(sizeof(srp_packet_header_t) == 64,
               "srp_packet_header_t must stay 64 bytes -- the viewer parses it by offset");

#endif
