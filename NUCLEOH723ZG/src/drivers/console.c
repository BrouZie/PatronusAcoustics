#include "console.h"

#include "linker.h"
#include "usart.h"

#include <stdio.h>

#define CONSOLE_UART huart3
#define CONSOLE_DMA  hdma_usart3_tx

enum
{
    // NOTE: Maximum tx buffer-size is set to the size of Full_Packet (API-example)
    // with pcm[NUM_MICS][AUDIO_SAMPLES] accounted for. You'll never realistically need more.
    TX_MAX_SIZE = (MIC_COUNT * AUDIO_SAMPLES * 2) + (128 * 4) + 16
};

global uint8_t         TxBuf[TX_MAX_SIZE] RAM1;
global char            StdoutBuf[128]     RAM1; // Buffer for printf
global volatile bool32 TxBusy;

internal void tx_done(DMA_HandleTypeDef *h)
{
    (void)h;
    CONSOLE_UART.Instance->CR3 &= ~USART_CR3_DMAT;
    TxBusy = false;
}

internal void tx_error(DMA_HandleTypeDef *h)
{
    (void)h;
    __builtin_trap();
}

void console_init(void)
{
    HAL_DMA_RegisterCallback(&CONSOLE_DMA, HAL_DMA_XFER_CPLT_CB_ID, tx_done);
    HAL_DMA_RegisterCallback(&CONSOLE_DMA, HAL_DMA_XFER_ERROR_CB_ID, tx_error);
    setvbuf(stdout, StdoutBuf, _IOLBF, sizeof(StdoutBuf));
}

// _write is called by printf and should only be used in
// main context - i.e. no printfs in any ISR 
int _write(int file, char *ptr, int len)
{
    (void)file;
    ASSERT(__get_IPSR() == 0);

    size_t off = 0;
    while (off < (size_t)len)
    {
        size_t n = (size_t)len - off;
        if (n > sizeof(TxBuf))
        {
            n = sizeof(TxBuf);
        }
        while (!console_send_async(ptr + off, n))
        {
        }
        off += n;
    }
    return len;
}

bool32 console_busy(void)
{
    return TxBusy;
}

bool32 console_send_async(const void *data, size_t len)
{
    ASSERT(len <= sizeof(TxBuf));
    if (TxBusy)
    {
        return false;
    }

    memcpy(TxBuf, data, len);
    SCB_CleanDCache_by_Addr((void *)TxBuf, (int32_t)((len + 31) & ~31));

    TxBusy = true;
    CONSOLE_UART.Instance->CR3 |= USART_CR3_DMAT;
    HAL_DMA_Start_IT(&CONSOLE_DMA, (uint32_t)TxBuf, (uint32_t)&CONSOLE_UART.Instance->TDR, len);
    return true;
}
