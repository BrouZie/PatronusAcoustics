#ifndef ICS_52000_H
#define ICS_52000_H

#include "audio_format.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef struct
{
    uint32_t chunks;
    uint32_t dropped;
    uint32_t lapped;
    uint32_t bus_errors;
    uint32_t last_hal_err;
} ics_stats_t;

void ics52000_start_fft(void);
bool ics52000_read_fft(const audio_sample_t** data);
void ics52000_stop_fft(void);

audio_format_t ics52000_format(void);
ics_stats_t* ics52000_stats(void);

#endif
