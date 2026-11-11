#include "ics52000.h"

#include "linker.h"
#include "audio_config.h"

#include "sai.h"
#include "mpu.h"

#define ICS_SAI_HANDLE_1 hsai_BlockA1
#define STARTUP_DISCARD_HALVES ((uint32_t)(0.300f * SAMPLE_RATE_HZ / AUDIO_SAMPLES) + 1)

enum
{
    // NOTE: We are deliberately throwing away information by setting
    // datasize to 16 bits (ICS52000 provides 24 bits but we only use 16)
    SAI_DATASIZE     = SAI_DATASIZE_16,
    SAI_SLOT_SIZE    = 32,
    SAI_SLOT_COUNT   = (MIC_COUNT <= 2 ? 2 : MIC_COUNT <= 4 ? 4 : MIC_COUNT <= 8 ? 8 : 16),
    SAI_ACTIVE_SLOTS = (1 << MIC_COUNT) - 1,
};

_Static_assert(MIC_COUNT <= 8, "SAI frame is capped at 256 bits (8 x 32-bit slots)");
_Static_assert(2 * sizeof(AudioFrame) <= 16384, "Audio buffer exceeds its DMA_BUF region");

global AudioFrame PPAudioFrame[2] DMA_BUF; // Ping-pong audio frame
global volatile uint32_t Sequence;

static void _ws_pin_as_gpio(void)
{
    GPIO_InitTypeDef g = { 0 };

    g.Pin   = GPIO_PIN_6;
    g.Mode  = GPIO_MODE_OUTPUT_PP;
    g.Pull  = GPIO_NOPULL;
    g.Speed = GPIO_SPEED_FREQ_VERY_HIGH;

    HAL_GPIO_Init(GPIOE, &g);

}

static void _ws_pin_as_sai(void)
{
    GPIO_InitTypeDef g = { 0 };

    g.Pin       = GPIO_PIN_6;
    g.Mode      = GPIO_MODE_AF_PP;
    g.Pull      = GPIO_NOPULL;
    g.Speed     = GPIO_SPEED_FREQ_VERY_HIGH;
	g.Alternate = GPIO_AF6_SAI1;

    HAL_GPIO_Init(GPIOE, &g);
}

bool32 ics52000_init(void)
{
    configure_mpu((uint32_t*)PPAudioFrame, sizeof(PPAudioFrame));

    // Reconfiguring SAI so we can change mic count without any trouble
    HAL_SAI_DeInit(&ICS_SAI_HANDLE_1);
    ICS_SAI_HANDLE_1.Init.AudioFrequency   = SAMPLE_RATE_HZ;
    ICS_SAI_HANDLE_1.Init.DataSize         = SAI_DATASIZE;
    ICS_SAI_HANDLE_1.FrameInit.FrameLength = SAI_SLOT_COUNT * SAI_SLOT_SIZE;
    ICS_SAI_HANDLE_1.SlotInit.SlotNumber   = SAI_SLOT_COUNT;
    ICS_SAI_HANDLE_1.SlotInit.SlotActive   = SAI_ACTIVE_SLOTS;
    if (HAL_SAI_Init(&ICS_SAI_HANDLE_1) != HAL_OK)
    {
        Error_Handler();
    }

	_ws_pin_as_gpio(); // PE4 driven low
				   
    // DMA startup
    if (HAL_SAI_Receive_DMA(&ICS_SAI_HANDLE_1, (uint8_t*)PPAudioFrame,
                            sizeof(PPAudioFrame) / sizeof(sample_t)) != HAL_OK)
    {
        Error_Handler();
    }

	HAL_Delay(20);    // WS pin should be delayed from the start of SCK by atleast 10 ms
	_ws_pin_as_sai(); // PE4 configured
	HAL_Delay(300);   // Atleast 256 ms from startup time to valid data

    return true;
}

// TODO: Figure out if we need a "new frame" check of sorts
// - to prevent reads of the same frame. As we are simply
// comparing to previous frame (dsp.c), maybe it's irrelevant.
bool32 ics52000_read(AudioFrameView* view)
{
    uint32_t seq = Sequence;

    // Data is invalid while the mic is starting up
    if (seq <= STARTUP_DISCARD_HALVES)
    {
        return false;
    }

    view->seq   = seq;
    view->frame = &PPAudioFrame[(seq - 1) % 2];

    return true;
}

//------------------ SAI callbacks ---------------------//

void HAL_SAI_RxHalfCpltCallback(SAI_HandleTypeDef* hsai)
{
    if (hsai->Instance == SAI1_Block_A)
    {
        ++Sequence;
    }
}

void HAL_SAI_RxCpltCallback(SAI_HandleTypeDef* hsai)
{
    if (hsai->Instance == SAI1_Block_A)
    {
        ++Sequence;
    }
}

void HAL_SAI_ErrorCallback(SAI_HandleTypeDef* hsai)
{
    if (hsai->Instance != SAI1_Block_A)
    {
        // TODO: Add some clever shit that does something maybe?
        return;
    }
}
