#include "app_entry.h"
#include "console.h"
#include "main.h"
#include "mdma.h"

#include <string.h>

// NB: Don't superseed MPU_REGION_SIZE_ defined in
// main.c (it'll cause cache incoherency).
#define BUF_FULL 8192
#define BUF_HALF (BUF_FULL / 2)
#define TX_BYTES (BUF_HALF * 4)

int32_t dma_buf[BUF_FULL] __attribute__((section(".raw_buf"), aligned(8)));
int32_t dtcm_buf[2][BUF_HALF] __attribute__((section(".dtcm_buf"), aligned(8)));

void mdma_complete_callback(MDMA_HandleTypeDef* h)
{
    (void)h;
    HAL_GPIO_TogglePin(GPIOB, GPIO_PIN_0);
}

void app_main(void)
{
    HAL_MDMA_RegisterCallback(&hmdma_mdma_channel0_sw_0, HAL_MDMA_XFER_CPLT_CB_ID, mdma_complete_callback);

    console_init();

    while (1)
    {
        memset(dma_buf, 0, BUF_HALF * sizeof(int32_t));
        HAL_MDMA_Start_IT(&hmdma_mdma_channel0_sw_0, (uint32_t)&dma_buf, (uint32_t)dtcm_buf[0], TX_BYTES, 1);

        memset(dma_buf + BUF_HALF, 17, BUF_HALF * sizeof(int32_t));
        HAL_MDMA_Start_IT(&hmdma_mdma_channel0_sw_0, (uint32_t)&dma_buf[BUF_HALF], (uint32_t)dtcm_buf[1], TX_BYTES, 1);

        HAL_Delay(10);
    }
}
