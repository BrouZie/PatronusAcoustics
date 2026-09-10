#ifndef CONSOLE_H
#define CONSOLE_H

#include "audio_config.h"

#include "arm_math_types.h"
#include "stdint.h"

/* What UART_MDMA_send_buffer() will accept, and why:
 *
 *   size -- must fit one RAM_D2 staging half, or the MDMA writes past its end.
 *   alignment -- the USART MDMA writes DOUBLEWORDS (Core/Src/mdma.c), so a
 *                length that is not a multiple of 8 raises MDMA_CESR_BSE, the
 *                completion callback never fires and the transfer is lost. 32
 *                also suits the 128-byte buffer length and 16-beat burst.
 *
 * Pad payloads up to CONSOLE_TX_ALIGN_BYTES. Anything else is refused and
 * counted; assert CONSOLE_PAYLOAD_OK() at compile time rather than find out. */
#define CONSOLE_STAGING_BYTES  (AUDIO_MIC_COUNT * SPECTRUM_FLOATS * sizeof(float32_t))
#define CONSOLE_TX_ALIGN_BYTES 32U

#define CONSOLE_PAYLOAD_OK(n) ((n) <= CONSOLE_STAGING_BYTES && ((n) % CONSOLE_TX_ALIGN_BYTES) == 0U)

void console_init(void);
void UART_MDMA_send_buffer(float32_t* block, uint32_t size);
void UART_DMA_start(void);

/* Payloads refused for bad size or alignment, plus hardware-reported MDMA/DMA
 * errors. Non-zero means packets are being lost. */
uint32_t console_tx_errors(void);

#endif
