#ifndef CONSOLE_H
#define CONSOLE_H

#include "types.h"

void console_init(void);

// Used in async mode - avoid mixing use of printf and async
// transmission, as we only have one USART/dataline
bool32 console_busy(void);
bool32 console_send_async(const void *data, size_t len);

#endif
