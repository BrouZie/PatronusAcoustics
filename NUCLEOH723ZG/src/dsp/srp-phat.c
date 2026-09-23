#include "srp-phat.h"

#include <math.h>

/*
 * The formula in srp-phat.h wants a phase term at every (bin, mic, direction).
 * Tabulating those is what a desktop implementation does, and it is what makes
 * SRP-PHAT look too big for a microcontroller: 26 bins x 8 mics x 1368
 * directions is 1.6 MB of complex floats. Two observations remove the table
 * without approximating anything:
 *
 *   1. Across bins the phase is a geometric sequence -- e^(+j 2pi k tau / N) is
 *      w^k -- so the band is walked with one complex multiply per bin.
 *   2. tau is a 3-term dot product, cheaper to recompute than to store.
 *
 * Memory is then O(directions + mics) instead of O(directions x mics x bins).
 * What remains costs directions x bins x mics complex MACs per frame, plus four
 * table sin/cos per (direction, mic) to seed the recursion: roughly 1.8 ms at
 * 2 mics and 7 ms at 8, against the 10.7 ms a 512-sample hop leaves. Those are
 * estimates at 550 MHz optimised -- Debug builds -O0 and can miss frames, so
 * watch ics52000_stats()->missed.
 */

doa_t srp_compute(const float32_t (*spectrum)[SPECTRUM_FLOATS], srp_t* srp)
{
}
