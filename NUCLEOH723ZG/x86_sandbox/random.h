/* rng.h -- xoshiro256++ PRNG. Header-only, C99 and C++, public domain.
 * Algorithm: Blackman & Vigna, https://prng.di.unimi.it/
 * Period 2^256-1, 32 B state, passes BigCrush. NOT cryptographically secure.
 *
 *   rng_t r;
 *   rng_seed_entropy(&r);          // or rng_seed(&r, 12345) for a reproducible run
 *   double u = rng_double(&r);     // [0, 1)
 *   size_t i = rng_below(&r, n);   // [0, n), unbiased
 *
 * State is explicit, so this is thread-safe by construction and gives the same
 * sequence from the same seed on every compiler. For a global, put
 * `extern rng_t g_rng;` here and `rng_t g_rng;` in one .c/.cpp file.
 */
#ifndef RNG_H
#define RNG_H

#include <stdint.h>
#include "arm_math.h"

#ifdef __cplusplus
extern "C"
{
#endif

    typedef struct
    {
        uint64_t s[4];
    } rng_t;

    static inline uint64_t rng__rotl(uint64_t x, int k)
    {
        return (x << k) | (x >> (64 - k));
    }

    /* ---------------------------CORE-------------------------------- */

    static inline uint64_t rng_next(rng_t* r)
    {
        const uint64_t result = rng__rotl(r->s[0] + r->s[3], 23) + r->s[0];
        const uint64_t t      = r->s[1] << 17;

        r->s[2] ^= r->s[0];
        r->s[3] ^= r->s[1];
        r->s[1] ^= r->s[2];
        r->s[0] ^= r->s[3];
        r->s[2] ^= t;
        r->s[3]  = rng__rotl(r->s[3], 45);

        return result;
    }

    /* -------------------------SEEDING------------------------------ */

    /* SplitMix64. Seeding s[] with the raw seed would be bad: xoshiro recovers slowly
     * from a near-zero state. */
    static inline uint64_t rng__mix(uint64_t* x)
    {
        uint64_t z = (*x += 0x9E3779B97F4A7C15ull);
        z          = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ull;
        z          = (z ^ (z >> 27)) * 0x94D049BB133111EBull;
        return z ^ (z >> 31);
    }

    static inline void rng_seed(rng_t* r, uint64_t seed)
    {
        int i;
        for (i = 0; i < 4; ++i)
            r->s[i] = rng__mix(&seed);
    }

/* Nondeterministic. Avoids std::random_device, which is deterministic on some
 * MinGW builds. Mixes wall clock, CPU clock and ASLR. */
#include <time.h>
    static inline void rng_seed_entropy(rng_t* r)
    {
        uint64_t seed  = (uint64_t)time(NULL);
        seed          ^= (uint64_t)(uintptr_t)(void*)r << 16;
        seed          ^= (uint64_t)clock() << 40;
        rng_seed(r, seed);
    }

    /* ----------------------FLOATING TYPES--------------------------- */

    /* Both half-open: [0, 1). Uses the high bits (xoshiro's low bits are weakest) and
     * scales by a power of two -- exact, no division. */
    static inline double rng_double(rng_t* r)
    {
        return (double)(rng_next(r) >> 11) * 0x1.0p-53;
    }
    static inline float rng_float(rng_t* r)
    {
        return (float)(rng_next(r) >> 40) * 0x1.0p-24f;
    }
    static inline float32_t arm_rng_f32(rng_t* r)
    {
        return (float32_t)(rng_next(r) >> 40) * 0x1.0p-24f;
    }

    static inline double rng_range(rng_t* r, double lo, double hi)
    {
        return lo + (hi - lo) * rng_double(r);
    }
    static inline float rng_rangef(rng_t* r, float lo, float hi)
    {
        return lo + (hi - lo) * rng_float(r);
    }
    static inline float32_t arm_rng_rangef32(rng_t* r, float32_t lo, float32_t hi)
    {
        return lo + (hi - lo) * arm_rng_f32(r);
    }

    /* -----------------------INTEGER TYPES---------------------------- */

    /* Unbiased [0, n) -- Lemire 2019. One multiply in the common case; the rejection
	 * branch is taken with probability < n/2^64. */
    static inline uint64_t rng_below(rng_t* r, uint64_t n)
    {
#if defined(__SIZEOF_INT128__)
#if defined(__GNUC__)
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wpedantic"
#endif
        unsigned __int128 m = (unsigned __int128)rng_next(r) * n;
        uint64_t low        = (uint64_t)m;
        if (low < n)
        {
            const uint64_t thresh = (0 - n) % n;
            while (low < thresh)
            {
                m   = (unsigned __int128)rng_next(r) * n;
                low = (uint64_t)m;
            }
        }
        return (uint64_t)(m >> 64);
#if defined(__GNUC__)
#pragma GCC diagnostic pop
#endif
#else /* portable fallback: reject on a power-of-two mask */
    uint64_t mask  = n - 1, x;
    mask          |= mask >> 1;
    mask          |= mask >> 2;
    mask          |= mask >> 4;
    mask          |= mask >> 8;
    mask          |= mask >> 16;
    mask          |= mask >> 32;
    do
    {
        x = rng_next(r) & mask;
    } while (x >= n);
    return x;
#endif
    }

    // inclusive [lo, hi]
    static inline int64_t rng_between(rng_t* r, int64_t lo, int64_t hi)
    {
        return lo + (int64_t)rng_below(r, (uint64_t)(hi - lo) + 1u);
    }

    /* ---------------------------STREAMS------------------------------- */

    /* Advance 2^128 draws. Seed once, then call k times to give replica/thread k its
     * own non-overlapping stream. */
    static inline void rng_jump(rng_t* r)
    {
        static const uint64_t J[4] = { 0x180EC6D33CFD0ABAull, 0xD5A61266F0C9392Cull, 0xA9582618E03FC9AAull,
                                       0x39ABDC4529B1661Cull };
        uint64_t t[4]              = { 0, 0, 0, 0 };
        int i, b, k;
        for (i = 0; i < 4; ++i)
            for (b = 0; b < 64; ++b)
            {
                if (J[i] & (1ull << b))
                    for (k = 0; k < 4; ++k)
                        t[k] ^= r->s[k];
                (void)rng_next(r);
            }
        for (k = 0; k < 4; ++k)
            r->s[k] = t[k];
    }

#ifdef __cplusplus
} /* extern "C" */
#endif

#endif /* RNG_H */
