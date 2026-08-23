#ifndef ICS_52000_H
#define ICS_52000_H

#include "audio_format.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef struct
{
    uint32_t blocks_delivered;
    uint32_t mdma_busy;
    uint32_t overwritten;
    uint32_t bus_errors;
    uint32_t last_hal_err;
	uint32_t mdma_errors;
} ics_stats_t;

void ics52000_start(void);
bool ics52000_read(const audio_sample_t** data);
void ics52000_stop(void);

audio_format_t ics52000_format(void);
ics_stats_t* ics52000_stats(void);

#endif
