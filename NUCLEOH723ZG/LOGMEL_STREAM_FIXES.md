# What had to change to get the log-mel image off the board

Baseline: `153cfe2`. At that commit the log-mel app compiled and ran, but no
usable image could reach the host. Four things had to change on the firmware
side and two on the host side. Everything else in the diff was optional.

## Required — without these, nothing usable arrives

### 1. USART3 TX DMA: `DMA_CIRCULAR` → `DMA_NORMAL`

Imposed in `UART_DMA_start()` (`src/drivers/console.c`). `Core/Src/usart.c:119`
is CubeMX-generated and left alone, same way `ics52000.c` imposes the SAI format.

`HAL_DMA_IRQHandler` only restores `State = READY` and releases `__HAL_LOCK` on
transfer-complete when `CIRC` is clear
(`Drivers/STM32H7xx_HAL_Driver/Src/stm32h7xx_hal_dma.c:1363-1372`). In circular
mode the handle stays locked forever, so **every `HAL_DMA_Start_IT` after the
first returns `HAL_BUSY` without reprogramming anything**. The stream just
re-sent whatever was in the staging half, racing the MDMA writing it.

Pre-existing, and it affects the `fft` app too — this is what
`tools/README.md` was blaming on the baud rate.

### 2. UART DMA length must be the caller's byte count

`MDMA_transfer_complete()` passed `AUDIO_MIC_COUNT * OUTPUT_BUF_SIZE *
sizeof(float32_t)` (4104 B) as the DMA length regardless of the `size` argument.
Any transfer that was not exactly 4104 B went out at the wrong length.

### 3. The transfer has to fit the D2 staging half

At HEAD the app handed `UART_MDMA_send_buffer` 94×64×4 = **24064 B** against a
4104 B half — a 20 KB overrun of `_d2_output`.

Either chunk the send or shrink the payload and enlarge the half. Took the
second: `uint8` cells give a 6048 B packet, half enlarged to 12288 B.

### 4. The MDMA source must live in DTCM, not RAM_D1

`SCB_EnableDCache()` is on (`Core/Src/main.c:80`). `.d1_buf` is cacheable
write-back and **no MPU region covers it** — `_mpu_configure` is called only for
`_d2_output` (`console.c`) and `_d1_capture` (`ics52000.c`), and both pass
`MPU_REGION_NUMBER0`, so the second call replaces the first anyway.

The CPU's writes sat in the D-cache while the MDMA read stale physical SRAM.
`spectrum.c:28` already stages its MDMA source in `.dtcm_buf` — that is exactly
why the fft path produced bytes and log-mel produced nothing.

The float image stays in RAM_D1; only the packet the MDMA reads moved to DTCM.

## Required on the host side

### 5. Re-apply `setRect` after every `setImage`

pyqtgraph resets an `ImageItem`'s rect to the array's pixel dimensions on
`setImage`, so a 1125-column image gets drawn across a 12-unit view. Symptom is
a completely blank plot, not a distorted one.

### 6. Draw columns at capture rate, not one image at a time

An image is 1 s of audio delivered in a 66 ms burst. Painting it on arrival
leaves the display frozen 93% of the time. Columns are queued and drained at
`rate / hop` per second.

## Not required — kept for other reasons

- **uint8 quantisation + packet header.** Chunking float32 would also have
  worked. Kept because the burst drops 261 ms → 66 ms, which now finishes
  inside the second the next image takes to fill, so **no audio frames are
  dropped at all**. The header also makes the viewer self-configuring and makes
  a dropped image visible instead of silent.
- **`src/apps/fft/app_main.c` call site.** Broken at HEAD (one argument against
  a two-argument prototype), but `make` builds one target at a time
  (`--target $(APP)`), so it never blocked log-mel.

## Traps still in the tree

- `MEL_WEIGHT_POOL_SIZE` (384) has **no bounds check** in
  `mel_filterbank_init()` — `pool_ptr += num_bins` runs off the end silently.
  Needs 320 today, 436 at 16 kHz/FFT 512, 804 at 16 kHz/FFT 1024.
- `_mpu_configure` hardcodes `MPU_REGION_NUMBER0`, so its two callers overwrite
  each other and only one region is ever live. Harmless today because neither
  buffer is CPU-written, but the comment above it claims protection that is not
  there for both.
