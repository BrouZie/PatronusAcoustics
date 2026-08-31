#ifndef ICS_52000_H
#define ICS_52000_H

#include "audio_config.h"
#include "audio_format.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef struct
{
    uint32_t delivered;
    uint32_t missed;      // reader too slow, block never seen
    uint32_t overwritten; // block clobbered mid-conversion
    uint32_t mdma_busy;   // kick refused, block never left D1
    uint32_t bus_errors;
    uint32_t mdma_errors;
    uint32_t last_hal_err;
} ics_stats_t;

void ics52000_start(void);
bool ics52000_read(float32_t* frame[AUDIO_MIC_COUNT]);
void ics52000_stop(void);

audio_format_t ics52000_format(void);
ics_stats_t*   ics52000_stats(void);

#endif
