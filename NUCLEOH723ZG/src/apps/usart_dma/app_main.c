/* Circular DMA + USART3 ping-pong example.
 *
 * CubeMX: USART3_TX DMA request, Mode = CIRCULAR, Mem->Periph, byte/byte,
 *         Memory Increment ON, Peripheral Increment OFF.
 *         Both the DMA stream IRQ and the USART3 global IRQ enabled.
 *
 * The callbacks do nothing but record which half is free. All real work
 * happens in main context, where it can be preempted and where blocking
 * calls are legal.
 */

#include "main.h"
#include "usart.h"
#include <stdbool.h>
#include <stdint.h>

#define HALF_LEN 2400u
#define BUF_LEN (2u * HALF_LEN) /* both must be multiples of 32 */

static uint8_t stream_buf[BUF_LEN] __attribute__((section(".RAM_D1"), aligned(32)));

/* Which half main() is allowed to touch. -1 = neither, don't write anything. */
static volatile int8_t free_half = -1;

/* Missed-deadline counter: incremented when a new half comes free before
 * main() has serviced the previous one. This is your underrun detector --
 * the hardware will not tell you, so count it yourself. */
static volatile uint32_t underruns = 0;

/* --------- Callbacks ---------*/
/* Both run in the DMA IRQ. Keep them to a few instructions. */

void HAL_UART_TxHalfCpltCallback(UART_HandleTypeDef* huart)
{
    if (huart->Instance != USART3)
        return;

    if (free_half != -1)
        underruns++; // main() never got to the last one
    free_half = 0;   // DMA is reading half B now
}

void HAL_UART_TxCpltCallback(UART_HandleTypeDef* huart)
{
    if (huart->Instance != USART3)
        return;

    if (free_half != -1)
        underruns++;
    free_half = 1; /* DMA wrapped, reading half A now */
}

void HAL_UART_ErrorCallback(UART_HandleTypeDef* huart)
{
    if (huart->Instance != USART3)
        return;

    /* A transfer error has already cleared EN in hardware. On the H7 the
     * usual cause is a buffer the DMA cannot address (DTCM) or an MPU fault.
     * Restarting without fixing that will just fault again -- trap it. */
    __disable_irq();
    while (1)
    {
    }
}

/* --------- Payload ---------*/

static uint8_t pattern = 49;

static void fill_half(uint8_t* dst, uint32_t len)
{
    for (uint32_t i = 0; i < len; ++i)
    {
        dst[i] = pattern;
    }
    pattern++;
    if (pattern >= 60)
        pattern = 49;
}

/* ------------------------------------------------------------------ main */

void stream_start(void)
{
    /* Prime BOTH halves before starting. The DMA begins reading immediately
     * and the first HalfCplt will not arrive until half A is already gone. */
    fill_half(&stream_buf[0], HALF_LEN);
    fill_half(&stream_buf[HALF_LEN], HALF_LEN);

    free_half = -1;
    HAL_UART_Transmit_DMA(&huart3, stream_buf, BUF_LEN);
    // Circular mode: this never completes. It runs until stream_stop().
}

void stream_stop(void)
{
    HAL_UART_DMAStop(&huart3); // clears EN and DMAT
    free_half = -1;
}

void stream_service(void)
{
    int8_t h = free_half;
    if (h < 0)
    {
        return; // nothing to do yet
    }

    free_half = -1; /* claim it before doing the work */
    fill_half(&stream_buf[(uint32_t)h * HALF_LEN], HALF_LEN);
}

void app_main(void)
{
    stream_start();

    uint32_t last_blink = HAL_GetTick();

    while (1)
    {
        stream_service(); /* must be reached faster than the
                             half-buffer period -- no HAL_Delay
                             anywhere in this loop */

        if (HAL_GetTick() - last_blink >= 500u)
        {
            last_blink += 500u;
            HAL_GPIO_TogglePin(GPIOB, GPIO_PIN_0);
        }
    }
}
