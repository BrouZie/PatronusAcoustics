#ifndef LINKER_H
#define LINKER_H

#define DTCM __attribute__((section(".dtcm_buf")))
#define RAM1 __attribute__((section(".d1_buf")))
#define RAM2 __attribute__((section(".d2_buf")))

// For buffers passed to configure_mpu(): each one starts its own 16 KB region
// in RAM_D1. Must be at most 16 KB, as MPU regions must be aligned to their size.
#define DMA_BUF __attribute__((section(".dma_buf"), aligned(16384)))

#endif
