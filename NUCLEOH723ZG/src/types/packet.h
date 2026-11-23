#ifndef PACKET_H
#define PACKET_H

// TODO: Move the packet header/restructure elsewhere etc. This is
// just a temporary solution - I think atleast.

#include "dsp.h"

#include <stdint.h>

#define PACKED __attribute__((packed))

#define MAGIC 0xDEADBEA7

typedef float float32_t;

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

#endif // PACKET_H
