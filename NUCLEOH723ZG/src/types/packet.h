#ifndef PACKET_H
#define PACKET_H

// TODO: Move the packet header/restructure elsewhere etc. This is
// just a temporary solution - I think atleast.

#include "dsp.h"

#include <stdint.h>

#define PACKED __attribute__((packed))

#define MAGIC 0xDEADBEA7

typedef float float32_t;

// NOTE: The packet size should not exceed 13 421 bytes (at a baudrate of 4194304)
// Baudrate / frame rate = max transfer per frame
typedef struct PACKED
{
    uint32_t  magic;
    uint32_t  seq;
#define X86_DEBUG // TODO: Change macro name - potentially tie it to "x86 as orchestrator builds"
#ifdef X86_DEBUG
    AudioFrame frame;
#endif
    float32_t mel[NUM_MEL_BANDS];
    float32_t azimuth;
    float32_t elevation;
} Full_Packet;

#endif // PACKET_H
