#include "srp-phat.h"

#include "array_geometry.h"
#include "audio_config.h"

#include <math.h>

/*
 * The formula in srp-phat.h asks for a phase term e^(+j 2pi k tau_m / N) at
 * every (bin, mic, direction). Tabulating those is what a desktop
 * implementation does -- py-simulation precomputes exactly that tensor -- and
 * it is also what makes SRP-PHAT look like it cannot fit on a microcontroller:
 * 26 bins x 8 mics x 1368 directions is 1.6 MB of complex floats.
 *
 * Two observations remove the table entirely, without approximating anything:
 *
 *   1. Across bins, the phase is a geometric sequence. For a fixed mic and
 *      direction, e^(+j 2pi k tau / N) is just w^k with w = e^(+j 2pi tau / N).
 *      So the band is walked with ONE complex multiply per bin, seeded once.
 *
 *   2. tau itself is a 3-term dot product. Cheaper to recompute than to store,
 *      and it means memory here is O(directions + mics) rather than
 *      O(directions x mics x bins) -- the array can grow without the buffers
 *      growing with it.
 *
 * What is left costs directions x bins x mics complex multiply-accumulates per
 * frame, plus four table-based sin/cos per (direction, mic) to seed the
 * recursion. That is the honest price of SRP-PHAT and it is the thing that
 * will eventually bind. Estimated at 550 MHz, optimised: ~1.8 ms at 2 mics and
 * ~7 ms at 8, against the 10.7 ms a 512-sample hop leaves.
 *
 * Two warnings about that figure. It is an estimate -- measure it with the DWT
 * cycle counter before trusting it. And the default build type is Debug, which
 * compiles -O0: expect several times the above, quite possibly more than the
 * frame period. Use BUILD=Release for anything timing-sensitive, and watch
 * ics52000_stats()->missed for the truth.
 */

/* --------- LINKER BINDINGS --------- */

#define SRP_DTCM_BUF ".dtcm_buf"

/* --------- CONSTANTS --------- */

/* Magnitude floor for the PHAT division, so a silent bin yields 0 instead of a
 * NaN. Matches py-simulation/src/constants.py:EPS_NORM. */
#define SRP_EPS 1.0e-10f

#define SRP_DEG_TO_RAD (PI / 180.0f)

/* --------- BUFFERS --------- */

/* PHAT-whitened spectra, band bins only: [mic][bin - SRP_K_MIN][re, im].
 * Whitening once per frame keeps it out of the direction loop, where it would
 * be repeated SRP_DIRECTIONS times for the same answer. */
static float32_t _whitened[AUDIO_MIC_COUNT][SRP_BAND_BINS][2] __attribute__((section(SRP_DTCM_BUF), aligned(32)));

/* Every angle the grid ever uses, resolved once at init. The direction loop
 * then builds unit vectors with two multiplies and no trigonometry. */
static float32_t _sin_az[SRP_AZ_STEPS];
static float32_t _cos_az[SRP_AZ_STEPS];
static float32_t _sin_el[SRP_EL_STEPS];
static float32_t _cos_el[SRP_EL_STEPS];

/* Running average of the map. The peak is picked from THIS rather than from
 * the current frame, and this is what the caller is handed. */
static float32_t _averaged[SRP_DIRECTIONS] __attribute__((section(SRP_DTCM_BUF), aligned(32)));
static bool      _averaged_primed;

/* --------- DIFFUSE-FIELD FLOOR --------- */

/* In a diffuse (reverberant) field two omnidirectional microphones d apart are
 * correlated by sinc(2*pi*f*d/c) with no source present at all. Averaged over
 * the band and over every pair, that is exactly what the coherence metric
 * reads for an empty room -- the number the detector has to beat.
 *
 * Computed once, from the geometry actually built, so it stays right when the
 * array changes instead of being a constant that silently goes stale. */
static float32_t _coherence_floor;

static void _coherence_floor_init(void)
{
    float32_t total = 0.0f;
    uint32_t  pairs = 0;

    for (uint32_t a = 0; a < AUDIO_MIC_COUNT; ++a)
    {
        for (uint32_t b = a + 1; b < AUDIO_MIC_COUNT; ++b)
        {
            const float32_t dx = ARRAY_MIC_POSITIONS[a][0] - ARRAY_MIC_POSITIONS[b][0];
            const float32_t dy = ARRAY_MIC_POSITIONS[a][1] - ARRAY_MIC_POSITIONS[b][1];
            const float32_t dz = ARRAY_MIC_POSITIONS[a][2] - ARRAY_MIC_POSITIONS[b][2];
            const float32_t d  = sqrtf(dx * dx + dy * dy + dz * dz);

            float32_t band = 0.0f;

            for (uint32_t k = SRP_K_MIN; k <= SRP_K_MAX; ++k)
            {
                const float32_t f = (float32_t)k * (float32_t)AUDIO_SAMPLE_RATE_HZ / (float32_t)SPECTRUM_FFT_SIZE;
                const float32_t x = 2.0f * PI * f * d / SRP_SPEED_OF_SOUND;

                band += (x > 1.0e-6f) ? arm_sin_f32(x) / x : 1.0f;
            }

            total += band / (float32_t)SRP_BAND_BINS;
            pairs++;
        }
    }

    _coherence_floor = (pairs > 0) ? total / (float32_t)pairs : 0.0f;
}

/* --------- PHAT --------- */

/* In-band level of mic 0 in dBFS, taken from the spectrum BEFORE whitening --
 * this is the last point at which amplitude still exists. */
static float32_t _band_level_db(const float32_t (*spec)[SPECTRUM_FLOATS])
{
    float32_t power = 0.0f;

    for (uint32_t k = SRP_K_MIN; k <= SRP_K_MAX; ++k)
    {
        power += spec[0][2 * k] * spec[0][2 * k] + spec[0][2 * k + 1] * spec[0][2 * k + 1];
    }

    /* Convert the windowed one-sided spectrum back to a time-domain mean square
     * and reference it to a full-scale sine, so 0 dB really is 0 dBFS:
     *
     *   2 / N^2          one-sided spectrum -> mean square
     *   / (3/8)          undo the periodic Hann power gain, mean(w^2)
     *   * 2              reference to a sine (mean square 1/2), not to 1.0
     *
     * The 3/8 ties this to the window spectrum.c applies; the two move together.
     * Verified: a full-scale sine reads 0.0, a 0.1 amplitude sine reads -20.0. */
    const float32_t scale = 4.0f / ((float32_t)SPECTRUM_FFT_SIZE * (float32_t)SPECTRUM_FFT_SIZE * 0.375f);

    return 10.0f * log10f(power * scale + SRP_EPS);
}

static void _whiten(const float32_t (*spec)[SPECTRUM_FLOATS])
{
    for (uint32_t ch = 0; ch < AUDIO_MIC_COUNT; ++ch)
    {
        for (uint32_t b = 0; b < SRP_BAND_BINS; ++b)
        {
            const uint32_t  k  = SRP_K_MIN + b;
            const float32_t re = spec[ch][2 * k];
            const float32_t im = spec[ch][2 * k + 1];

            /* Divide each bin by its own magnitude: what survives is a unit
             * complex number carrying only the arrival phase. A jet engine and
             * a whisper at the same frequency now count the same, which is the
             * whole point -- the peak is decided by agreement across mics, not
             * by loudness. */
            const float32_t scale = 1.0f / (sqrtf(re * re + im * im) + SRP_EPS);

            _whitened[ch][b][0] = re * scale;
            _whitened[ch][b][1] = im * scale;
        }
    }
}

/* --------- STEERING --------- */

// Steered response power for one direction, given as a unit vector
static float32_t _steer(float32_t ux, float32_t uy, float32_t uz)
{
    /* Per mic: the rotator at the first band bin, and the step that carries it
     * to the next one. Both are unit complex numbers. */
    float32_t rot_re[AUDIO_MIC_COUNT];
    float32_t rot_im[AUDIO_MIC_COUNT];
    float32_t step_re[AUDIO_MIC_COUNT];
    float32_t step_im[AUDIO_MIC_COUNT];

    for (uint32_t ch = 0; ch < AUDIO_MIC_COUNT; ++ch)
    {
        const float32_t* pos = ARRAY_MIC_POSITIONS[ch];

        /* Steering delay in samples. A microphone displaced toward the source
         * hears the wavefront EARLIER, so its delay is negative -- hence the
         * leading minus on the dot product. */
        const float32_t tau =
            -(pos[0] * ux + pos[1] * uy + pos[2] * uz) / SRP_SPEED_OF_SOUND * (float32_t)AUDIO_SAMPLE_RATE_HZ;

        /* Undoing that delay is a phase advance of 2*pi*tau/N per bin index.
         * arm_sin/cos_f32 are table lookups: exact enough at 1e-7, and cheap
         * enough to afford once per (direction, mic). */
        const float32_t per_bin = 2.0f * PI * tau / (float32_t)SPECTRUM_FFT_SIZE;

        step_re[ch] = arm_cos_f32(per_bin);
        step_im[ch] = arm_sin_f32(per_bin);

        const float32_t first_bin = per_bin * (float32_t)SRP_K_MIN;

        rot_re[ch] = arm_cos_f32(first_bin);
        rot_im[ch] = arm_sin_f32(first_bin);
    }

    float32_t power = 0.0f;

    for (uint32_t b = 0; b < SRP_BAND_BINS; ++b)
    {
        float32_t beam_re = 0.0f;
        float32_t beam_im = 0.0f;

        for (uint32_t ch = 0; ch < AUDIO_MIC_COUNT; ++ch)
        {
            const float32_t xr = _whitened[ch][b][0];
            const float32_t xi = _whitened[ch][b][1];

            /* Rotate this mic into alignment with the array origin and add it
             * to the beam. Mics that agree about this direction add up; mics
             * that do not, cancel. */
            beam_re += xr * rot_re[ch] - xi * rot_im[ch];
            beam_im += xr * rot_im[ch] + xi * rot_re[ch];

            // Advance the rotator one bin: rot *= step.
            const float32_t next_re = rot_re[ch] * step_re[ch] - rot_im[ch] * step_im[ch];

            rot_im[ch] = rot_re[ch] * step_im[ch] + rot_im[ch] * step_re[ch];
            rot_re[ch] = next_re;
        }

        power += beam_re * beam_re + beam_im * beam_im;
    }

    return power;
}

/* --------- PUBLIC API --------- */

void srp_phat_init(void)
{
    for (uint32_t a = 0; a < SRP_AZ_STEPS; ++a)
    {
        const float32_t az = (SRP_AZ_START_DEG + (float32_t)a * SRP_AZ_STEP_DEG) * SRP_DEG_TO_RAD;

        _sin_az[a] = arm_sin_f32(az);
        _cos_az[a] = arm_cos_f32(az);
    }

    for (uint32_t e = 0; e < SRP_EL_STEPS; ++e)
    {
        const float32_t el = (SRP_EL_START_DEG + (float32_t)e * SRP_EL_STEP_DEG) * SRP_DEG_TO_RAD;

        _sin_el[e] = arm_sin_f32(el);
        _cos_el[e] = arm_cos_f32(el);
    }

    _averaged_primed = false;

    _coherence_floor_init();
}

void srp_phat_compute(const float32_t (*spec)[SPECTRUM_FLOATS], float32_t* map_out, srp_doa_t* doa)
{
    doa->level_db = _band_level_db(spec);

    _whiten(spec);

    float32_t peak    = -1.0f;
    uint32_t  peak_az = 0;
    uint32_t  peak_el = 0;

    for (uint32_t a = 0; a < SRP_AZ_STEPS; ++a)
    {
        for (uint32_t e = 0; e < SRP_EL_STEPS; ++e)
        {
            /* Unit vector toward (az, el). Elevation is the POLAR angle from
             * boresight, so sin(el) -- not cos -- scales the in-plane part. */
            const float32_t ux = _sin_el[e] * _cos_az[a];
            const float32_t uy = _sin_el[e] * _sin_az[a];
            const float32_t uz = _cos_el[e];

            const uint32_t  d     = a * SRP_EL_STEPS + e;
            const float32_t power = _steer(ux, uy, uz);

            /* Blend this frame into the running map. The first frame has no
             * history to blend with, so it seeds the average outright --
             * otherwise the map would ramp up from zero over SRP_AVERAGE_FRAMES
             * frames and the early bearings would be meaningless. */
            _averaged[d] =
                _averaged_primed ? _averaged[d] + (power - _averaged[d]) / (float32_t)SRP_AVERAGE_FRAMES : power;

            map_out[d] = _averaged[d];

            if (_averaged[d] > peak)
            {
                peak    = _averaged[d];
                peak_az = a;
                peak_el = e;
            }
        }
    }

    /* At el = 0 every azimuth names the same direction (straight ahead), so
     * that row of the map is 72 copies of one value. The strict > above breaks
     * the tie toward azimuth 0, which is as meaningful as any other. */

    _averaged_primed = true;

    doa->azimuth_deg   = SRP_AZ_START_DEG + (float32_t)peak_az * SRP_AZ_STEP_DEG;
    doa->elevation_deg = SRP_EL_START_DEG + (float32_t)peak_el * SRP_EL_STEP_DEG;
    doa->peak_power    = peak;

    /* How far the peak stands above the map's own floor. A real source makes
     * one direction much better than average; noise alone does not. The inner
     * epsilon keeps a fully silent frame at a finite -100 dB. */
    /* Where the peak sits between the diffuse-noise floor and the perfectly
     * coherent ceiling that PHAT normalisation pins the map to. */
    const float32_t incoherent = (float32_t)AUDIO_MIC_COUNT * (float32_t)SRP_BAND_BINS;
    const float32_t coherent   = (float32_t)AUDIO_MIC_COUNT * incoherent;

    /* One microphone has nothing to agree with, so its map carries no
     * direction information and the span below collapses to zero. */
    float32_t coherence = (coherent > incoherent) ? (peak - incoherent) / (coherent - incoherent) : 0.0f;

    if (coherence < 0.0f)
    {
        coherence = 0.0f;
    }
    if (coherence > 1.0f)
    {
        coherence = 1.0f;
    }

    doa->coherence       = coherence;
    doa->coherence_floor = _coherence_floor;

    /* Both gates, answering different questions: coherence says the bearing is
     * trustworthy, level says there is something worth reporting a bearing
     * about. Coherence is judged against what an empty room already produces,
     * not against zero. */
    doa->detected =
        (coherence >= _coherence_floor + SRP_DETECT_MARGIN) && (doa->level_db >= SRP_DETECT_LEVEL_DB);
}
