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

#endif
