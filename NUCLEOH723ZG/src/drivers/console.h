#ifndef CONSOLE_H
#define CONSOLE_H

#include "audio_config.h"

#include "arm_math_types.h"
#include "stdint.h"

/* Capacity of one RAM_D2 staging half, in bytes: the largest payload
 * UART_MDMA_send_buffer() accepts. Anything larger is dropped and counted --
 * see the guard in console.c. Apps should _Static_assert their payload against
 * this rather than discover it at runtime. */
#define CONSOLE_STAGING_BYTES (AUDIO_MIC_COUNT * SPECTRUM_FLOATS * sizeof(float32_t))

/* The USART MDMA writes DOUBLEWORDS to RAM_D2 (Core/Src/mdma.c), so a transfer
 * whose length is not a multiple of 8 raises MDMA_CESR_BSE (Block Size Error),
 * the completion callback never fires, and the transfer is lost. 32 keeps the
 * 128-byte buffer transfer length and 16-beat destination burst tidy as well.
 * Pad payloads up to this; UART_MDMA_send_buffer() refuses anything else. */
#define CONSOLE_TX_ALIGN_BYTES 32U

void console_init(void);
void UART_MDMA_send_buffer(float32_t* block, uint32_t size);
void UART_DMA_start(void);

/* Payloads refused for exceeding CONSOLE_STAGING_BYTES. Non-zero means an app
 * is asking to send more than the staging half can hold and its stream is
 * silently incomplete. */
uint32_t console_oversized_drops(void);

/* Transfers refused for bad length, plus MDMA/DMA errors reported by hardware.
 * Non-zero means packets are being lost rather than silently corrupted. */
uint32_t console_tx_errors(void);

#endif
