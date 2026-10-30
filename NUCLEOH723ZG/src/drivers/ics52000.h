#ifndef ICS_52000_H
#define ICS_52000_H

#include "types.h"

// TODO(sok): Throw away ~300ms of frame samples at startup
bool32 ics52000_init(void);
bool32 ics52000_read(AudioFrameView* view);

#endif
