#include "app_entry.h"
#include "audio_config.h"
#include "linker.h"

#include "ics52000.h"
#include "console.h"
#include <stdint.h>

#define PCM_MAGIC 0x50434D31 // PCM1

typedef struct __attribute__((packed)) {
	uint32_t magic;
	uint32_t seq;         // increments every frame; used to detect drops
} pcm_header;

typedef struct __attribute__((packed)) {
    pcm_header header;
	int16_t frame[AUDIO_SAMPLES][MIC_COUNT];
} pcm_packet;

global AudioFrameView View  DTCM;

static pcm_packet _pcm_frame_tx[2] DMA_BUF;

void app_main(void)
{
	ics52000_init();
    UART_DMA_start((uint32_t)_pcm_frame_tx, sizeof(pcm_packet));

    uint32_t seq      = 0;
	uint32_t last_seq = 0;
	uint8_t  tx_idx   = 0;

	while (true)
	{
        if (!ics52000_read(&View) || View.seq == last_seq)
        {
            continue;
        }

        pcm_packet* packet = &_pcm_frame_tx[tx_idx];

        packet->header = (pcm_header) {
            .magic     = PCM_MAGIC,
            .seq     = seq++,
		};
		memcpy(packet->frame, View.frame->pcm, sizeof(packet->frame));

        UART_MDMA_send_buffer(packet, sizeof(*packet));

        last_seq = View.seq;
		tx_idx ^= 1;
	}
}
