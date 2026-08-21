#ifndef AUDIO_CONFIG_H
#define AUDIO_CONFIG_H

// ============================================================================
// The single source of truth for what the capture stage produces. The driver
// imposes these values on the SAI peripheral at init (overriding whatever the
// .ioc last generated into Core/Src/sai.c) and republishes them at runtime as
// an audio_format_t, so downstream modules never need to include this file.
//
// LEAF HEADER: No HAL, no function declarations, no module
// headers -- that is what keeps it safe for every module to depend on.
//
// Each tunable is #ifndef-guarded so a whole build tree can be reconfigured
// from the command line:
//
//   cmake -S . -B build/8mic -DPATRONUS_MIC_COUNT=8 ...
// ============================================================================

#include <stdint.h>

// --------- Tunables ---------

#ifndef AUDIO_MIC_COUNT
#define AUDIO_MIC_COUNT 1
#endif

#ifndef AUDIO_SAMPLE_RATE_HZ
#define AUDIO_SAMPLE_RATE_HZ 48000
#endif

#ifndef AUDIO_SAMPLE_BITS
#define AUDIO_SAMPLE_BITS 32
#endif

// Controls latency and buffer size: one block is
// AUDIO_SAMPLES_PER_BLOCK / AUDIO_SAMPLE_RATE_HZ seconds of audio.
#ifndef AUDIO_SAMPLES_PER_BLOCK
#define AUDIO_SAMPLES_PER_BLOCK 512
#endif

// Fast Fourier Tranform buffer
#ifndef FFT_BUFFER_SIZE
#define FFT_BUFFER_SIZE AUDIO_SAMPLES_PER_BLOCK
#endif

//--------- Derived. Don't edit by hand! ---------


// Largest positive sample magnitude, i.e. 0 dBFS. Replaces the 8388608.0f
// that used to be hardcoded in src/dsp/.
#define AUDIO_FULL_SCALE (1L << (AUDIO_SAMPLE_BITS - 1))

// Total samples in one interleaved block, all microphones.
#define AUDIO_BLOCK_SAMPLES (AUDIO_SAMPLES_PER_BLOCK * AUDIO_MIC_COUNT)

// --------- Invariants ---------

_Static_assert(AUDIO_MIC_COUNT >= 1 && AUDIO_MIC_COUNT <= 8,
               "SAI TDM frames carry at most 8 slots");

_Static_assert((AUDIO_SAMPLES_PER_BLOCK & (AUDIO_SAMPLES_PER_BLOCK - 1)) == 0,
               "AUDIO_SAMPLES_PER_BLOCK must be a power of two for the FFT");

// AUDIO_FULL_SCALE and audio_format_t.full_scale are signed 32-bit, so 24 is
// the largest depth that cannot overflow. Widen both to int64_t/float before
// raising this.
_Static_assert(AUDIO_SAMPLE_BITS >= 8 && AUDIO_SAMPLE_BITS <= 32,
               "AUDIO_FULL_SCALE would overflow int32_t above 32 bits");

#endif
