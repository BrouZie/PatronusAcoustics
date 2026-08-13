#ifndef ICS_52000_H
#define ICS_52000_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef struct
{
    const int32_t* data;
    size_t frames;
} ics_chunk_t;

typedef struct
{
    uint32_t blocks;
    uint32_t dropped;
    uint32_t bus_errors;
    uint32_t last_hal_err;
} ics_stats_t;

void ics52000_start(void);
bool ics52000_read(ics_chunk_t* chunk);
void ics52000_stop(void);

ics_stats_t ics52000_stats(void);

#endif
