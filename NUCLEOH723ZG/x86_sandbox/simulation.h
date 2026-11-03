#ifndef SIMULATION_H
#define SIMULATION_H

#include "types.h"
#include "audio_config.h"

#include "random.h"
#include "dsp.h"

typedef struct
{
    float32_t az, el;
} AngleDeg;

typedef struct
{
    rng_t r;
    AngleDeg angle;
    MicArray array;
} SimState;

bool32 sim_produce_frame(rng_t* r, AudioFrameView* view, MicArray array, AngleDeg direction);

#endif // SIMULATION_H
