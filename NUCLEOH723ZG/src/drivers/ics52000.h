#ifndef ICS_52000_H
#define ICS_52000_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef int32_t ics_sample_t;

typedef struct
{
	uint32_t ics_samples_per_mic;
	uint32_t ics_mic_count;
	uint32_t sample_rate;
} ics_config_t;

typedef struct
{
    uint32_t chunks;
    uint32_t dropped;
    uint32_t lapped;
    uint32_t bus_errors;
    uint32_t last_hal_err;
} ics_stats_t;

void ics52000_start(void);
bool ics52000_read(const ics_sample_t** data);
void ics52000_stop(void);

ics_config_t ics52000_config(void);
ics_stats_t ics52000_stats(void);

#endif
