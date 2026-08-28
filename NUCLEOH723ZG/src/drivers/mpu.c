#include "mpu.h"

/* Smallest power-of-two region that covers the buffer, as an MPU size code. */
static inline uint8_t _mpu_size(uint32_t bytes)
{
    uint32_t size = 32;

    while (size < bytes)
        size <<= 1;

    return (uint8_t)(__builtin_ctz(size) - 1);
}

/* Marks _dma_buf as Normal non-cacheable (TEX=001, C=0, B=0) so the SAI DMA
 * and the MDMA see the same bytes the CPU would. Note the region is rounded up
 * to a power of two -- the linker script must pad .d1_buf to match so no other
 * data falls inside it. */
void _mpu_configure(uint32_t *memory_address, uint32_t size_bytes)
{
    MPU_Region_InitTypeDef r = { 0 };

    HAL_MPU_Disable();

    r.Enable           = MPU_REGION_ENABLE;
    r.Number           = MPU_REGION_NUMBER0;
    r.BaseAddress      = (uint32_t)memory_address;
    r.Size             = _mpu_size(size_bytes);
    r.SubRegionDisable = 0x0;
    r.TypeExtField     = MPU_TEX_LEVEL1;
    r.AccessPermission = MPU_REGION_FULL_ACCESS;
    r.DisableExec      = MPU_INSTRUCTION_ACCESS_DISABLE;
    r.IsShareable      = MPU_ACCESS_SHAREABLE;
    r.IsCacheable      = MPU_ACCESS_NOT_CACHEABLE;
    r.IsBufferable     = MPU_ACCESS_NOT_BUFFERABLE;

    HAL_MPU_ConfigRegion(&r);
    HAL_MPU_Enable(MPU_HFNMI_PRIVDEF);
}
