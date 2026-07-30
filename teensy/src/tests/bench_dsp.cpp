/// DSP + SRP-PHAT BENCHMARKS AND SYNTHETIC VALIDATION (no mics needed)
///
/// Produces the numbers py-simulation's MCU model wants back
/// (mcu.calibrations): rfft_cycles, steering_cmacs_per_cycle,
/// region_bytes_per_cycle, div/sqrt cycles. Also validates the SRP-PHAT
/// kernels against synthetic plane waves (known DOA) and checks that the
/// recurrence and full-table kernels agree.
#include <Arduino.h>
#include <AudioStream.h> // AUDIO_SAMPLE_RATE_EXACT only; no audio graph here
#include <ArrayGeometry.hpp>
#include <CycleBench.hpp>
#include <Dsp.hpp>
#include <SrpPhat.hpp>
#include <math.h>

// ---------- Config ----------
constexpr float kFs { AUDIO_SAMPLE_RATE_EXACT }; // 44117.647 Hz
constexpr int kFftSize { 1024 };
constexpr float kMinFreq { 100.0f };
constexpr float kMaxFreq { 1000.0f };
constexpr int kReps { 100 };
constexpr int kSteerReps { 20 };
// ----------------------------

static uint32_t samples[kReps];
static volatile float g_sink; // defeat dead-code elimination

// ---------- test buffers per memory region ----------
// DTCM (RAM1, tightly coupled, uncached): plain statics
static float dtcm_buf[12288];                       // 48 KB; also the DTCM
                                                    // steering-table buffer
static float fft_in[4096], fft_out[4096];           // FFT scratch
static float spec[16][kFftSize];                    // synthetic spectra
static const float* spec_ptrs[16];

// OCRAM2 (RAM2, cached, where the heap also lives)
DMAMEM static float ocram_buf[32768]; // 128 KB >> 32 KB dcache

// Flash (XIP through cache): constexpr-generated garbage, stored in flash
struct FlashTable
{
    float v[32768]; // 128 KB
    constexpr FlashTable() : v {}
    {
        uint32_t s { 123456789u };
        for (int i { 0 }; i < 32768; ++i)
        {
            s = s * 1664525u + 1013904223u;
            v[i] = (float)(s >> 8) * (1.0f / 16777216.0f) - 0.5f;
        }
    }
};
PROGMEM static constexpr FlashTable flash_table {};

// ---------- small PRNG helpers ----------
static uint32_t rng_state { 0xC0FFEE42u };
static float rand_uniform() // [0, 1)
{
    rng_state = rng_state * 1664525u + 1013904223u;
    return (float)(rng_state >> 8) * (1.0f / 16777216.0f);
}
static float rand_gauss() // Box-Muller, N(0, 1)
{
    float u1 { rand_uniform() + 1e-12f };
    float u2 { rand_uniform() };
    return sqrtf(-2.0f * logf(u1)) * cosf(2.0f * (float)M_PI * u2);
}

// ---------- section 1: streaming bandwidth per memory region ----------
static float stream_sum(const float* p, int n)
{
    float a0 {}, a1 {}, a2 {}, a3 {};
    for (int i {}; i < n; i += 4)
    {
        a0 += p[i];
        a1 += p[i + 1];
        a2 += p[i + 2];
        a3 += p[i + 3];
    }
    return a0 + a1 + a2 + a3;
}

static void bench_bandwidth()
{
    Serial.println("\n== region_bytes_per_cycle (sequential f32 read) ==");
    struct Region
    {
        const char* name;
        const float* buf;
        int n;
    } regions[] {
        { "dtcm (RAM1)", dtcm_buf, 12288 },
        { "ocram2 (RAM2/DMAMEM)", ocram_buf, 32768 },
        { "flash_xip (PROGMEM)", flash_table.v, 32768 },
    };
    for (auto& r : regions)
    {
        for (int i {}; i < r.n; ++i)
            if (r.buf != flash_table.v)
                const_cast<float*>(r.buf)[i] = rand_uniform();
        auto s = CycleBench::measure([&] { g_sink = stream_sum(r.buf, r.n); },
                                     samples, kReps);
        float bytes { (float)r.n * 4 };
        Serial.printf("%-24s %8.0f B in %8lu cyc -> %.3f B/cycle\n", r.name,
                      bytes, (unsigned long)s.median, bytes / s.median);
    }
}

// ---------- section 2: rfft_cycles ----------
static void bench_rfft()
{
    Serial.println("\n== rfft_cycles (arm_rfft_fast_f32) ==");
    const int sizes[] { 256, 512, 1024, 2048, 4096 };
    for (int n : sizes)
    {
        Dsp::Rfft r;
        if (!r.init(n))
        {
            Serial.printf("  %d: init failed\n", n);
            continue;
        }
        for (int i {}; i < n; ++i)
            fft_in[i] = rand_gauss();
        // forward() clobbers its input; repeated calls then transform garbage,
        // which costs the same (FFT cost is data-independent).
        auto s = CycleBench::measure([&] { r.forward(fft_in, fft_out); },
                                     samples, kReps);
        Serial.printf("  %4d: median %7lu cycles  (min %7lu, max %7lu)\n", n,
                      (unsigned long)s.median, (unsigned long)s.min,
                      (unsigned long)s.max);
    }
}

// ---------- section 3: div / sqrt / phat ----------
static void bench_scalar_ops()
{
    Serial.println("\n== scalar op costs (dependent chain, per op) ==");
    constexpr int kOps { 1000 };
    volatile float seed { 1.234f };

    auto s = CycleBench::measure(
        [&]
        {
            float x { seed };
            for (int i {}; i < kOps; ++i)
                x = sqrtf(x + 1.1f);
            g_sink = x;
        },
        samples, kReps);
    Serial.printf("  sqrtf: %.2f cycles/op\n", (float)s.median / kOps);

    s = CycleBench::measure(
        [&]
        {
            float x { seed };
            for (int i {}; i < kOps; ++i)
                x = 1000000.0f / (x + 1.0f);
            g_sink = x;
        },
        samples, kReps);
    Serial.printf("  fdiv:  %.2f cycles/op\n", (float)s.median / kOps);

    // PHAT whitening cost over the actual band
    float bin_width { kFs / kFftSize };
    int k0 { (int)ceilf(kMinFreq / bin_width) };
    int k1 { (int)floorf(kMaxFreq / bin_width) };
    for (int i {}; i < kFftSize; ++i)
        fft_out[i] = rand_gauss();
    int n_bins { k1 - k0 + 1 };
    s = CycleBench::measure([&] { Dsp::phat_normalize(fft_out, k0, k1); },
                            samples, kReps);
    Serial.printf("  phat_normalize: %lu cycles for %d bins (%.1f/bin)\n",
                  (unsigned long)s.median, n_bins, (float)s.median / n_bins);
}

// ---------- synthetic plane-wave spectra ----------
// X[m][k] = e^{j(phi_k + w_k tau_m)} (mic closer to the source leads in
// phase), optional additive complex gaussian noise, then PHAT-normalized -
// exactly what the live pipeline feeds SrpPhat::Processor.
static void synth_spectra(const float (*pos)[3], int n_mics, float az_deg,
                          float el_deg, int k0, int k1, float noise_sigma)
{
    constexpr float kDeg2Rad { 0.017453292519943295f };
    float se { sinf(el_deg * kDeg2Rad) };
    float dir[3] { se * cosf(az_deg * kDeg2Rad), se * sinf(az_deg * kDeg2Rad),
                   cosf(el_deg * kDeg2Rad) };
    float tau[SrpPhat::kMaxMics];
    for (int m {}; m < n_mics; ++m)
        tau[m] = (pos[m][0] * dir[0] + pos[m][1] * dir[1] + pos[m][2] * dir[2])
                 / 343.0f;

    float dw { 2.0f * (float)M_PI * kFs / kFftSize };
    for (int m {}; m < n_mics; ++m)
        memset(spec[m], 0, kFftSize * sizeof(float));
    for (int k { k0 }; k <= k1; ++k)
    {
        float phi { rand_uniform() * 2.0f * (float)M_PI };
        float w { dw * k };
        for (int m {}; m < n_mics; ++m)
        {
            float ph { phi + w * tau[m] };
            spec[m][2 * k] = cosf(ph) + noise_sigma * rand_gauss();
            spec[m][2 * k + 1] = sinf(ph) + noise_sigma * rand_gauss();
        }
    }
    for (int m {}; m < n_mics; ++m)
        Dsp::phat_normalize(spec[m], k0, k1);
}

static SrpPhat::Params make_params(const float (*pos)[3], int n_mics, float res)
{
    SrpPhat::Params p;
    p.positions = pos;
    p.n_mics = n_mics;
    p.grid = SrpPhat::GridSpec { -180.0f, 180.0f, 0.0f, 90.0f, res };
    p.fs = kFs;
    p.fft_size = kFftSize;
    p.min_freq = kMinFreq;
    p.max_freq = kMaxFreq;
    return p;
}

// ---------- section 4: steering kernels ----------
static void bench_steering_one(const char* name, const SrpPhat::Params& p,
                               SrpPhat::Kernel k, float* buf, size_t buf_bytes)
{
    SrpPhat::Processor srp;
    if (!srp.init(p, k, buf, buf_bytes))
    {
        Serial.printf("  %-34s skipped (table %lu KB doesn't fit)\n", name,
                      (unsigned long)(SrpPhat::Processor::table_bytes_for(p, k)
                                      / 1024));
        return;
    }
    synth_spectra(p.positions, p.n_mics, 40.0f, 30.0f, srp.bin_first(),
                  srp.bin_last(), 0.0f);
    uint32_t steer[kSteerReps];
    for (int i {}; i < kSteerReps; ++i)
    {
        srp.process(spec_ptrs);
        steer[i] = srp.last_steering_cycles();
    }
    auto s = CycleBench::stats_from(steer, kSteerReps);
    float cmacs { (float)srp.cmacs_per_frame() };
    Serial.printf("  %-34s %4d dirs %2d bins  table %6lu KB  "
                  "%8lu cyc  %.4f cmacs/cycle\n",
                  name, srp.n_dirs(), srp.n_bins(),
                  (unsigned long)(srp.table_bytes() / 1024),
                  (unsigned long)s.median, cmacs / s.median);
}

static void bench_steering()
{
    Serial.println("\n== steering kernels (front hemisphere, 100-1000 Hz) ==");
    Serial.println("  cmacs = n_bins*n_mics*n_dirs (py-simulation MCU model)");
    using ArrayGeometry::kGeometries;
    const float(*ring8)[3] { kGeometries[0].positions };
    const float(*dual16)[3] { kGeometries[1].positions };
    constexpr size_t kDtcmBytes { sizeof(dtcm_buf) };

    bench_steering_one("recurrence 5mic 10deg heap",
                       make_params(ring8, 5, 10.0f),
                       SrpPhat::Kernel::Recurrence, nullptr, 0);
    bench_steering_one("recurrence 5mic 10deg DTCM",
                       make_params(ring8, 5, 10.0f),
                       SrpPhat::Kernel::Recurrence, dtcm_buf, kDtcmBytes);
    bench_steering_one("recurrence 8mic 10deg heap",
                       make_params(ring8, 8, 10.0f),
                       SrpPhat::Kernel::Recurrence, nullptr, 0);
    bench_steering_one("recurrence 8mic 10deg DTCM",
                       make_params(ring8, 8, 10.0f),
                       SrpPhat::Kernel::Recurrence, dtcm_buf, kDtcmBytes);
    bench_steering_one("recurrence 8mic 6deg heap",
                       make_params(ring8, 8, 6.0f),
                       SrpPhat::Kernel::Recurrence, nullptr, 0);
    bench_steering_one("recurrence 16mic 6deg heap",
                       make_params(dual16, 16, 6.0f),
                       SrpPhat::Kernel::Recurrence, nullptr, 0);
    bench_steering_one("full-table 5mic 10deg heap",
                       make_params(ring8, 5, 10.0f),
                       SrpPhat::Kernel::FullTable, nullptr, 0);
    bench_steering_one("full-table 8mic 14deg heap",
                       make_params(ring8, 8, 14.0f),
                       SrpPhat::Kernel::FullTable, nullptr, 0);
}

// ---------- section 5: kernel parity ----------
static void check_parity()
{
    Serial.println("\n== kernel parity (recurrence vs full table) ==");
    auto p = make_params(ArrayGeometry::kGeometries[0].positions, 5, 10.0f);
    SrpPhat::Processor a, b;
    if (!a.init(p, SrpPhat::Kernel::Recurrence)
        || !b.init(p, SrpPhat::Kernel::FullTable))
    {
        Serial.println("  init failed");
        return;
    }
    synth_spectra(p.positions, p.n_mics, -70.0f, 55.0f, a.bin_first(),
                  a.bin_last(), 0.1f);
    auto ra = a.process(spec_ptrs);
    auto rb = b.process(spec_ptrs);
    float max_rel {};
    for (int d {}; d < a.n_dirs(); ++d)
    {
        float rel { fabsf(a.power_map()[d] - b.power_map()[d])
                    / (fabsf(b.power_map()[d]) + 1e-12f) };
        if (rel > max_rel)
            max_rel = rel;
    }
    Serial.printf("  max relative power-map diff: %.3e (expect ~1e-5)\n",
                  max_rel);
    Serial.printf("  peaks: recurrence az %.0f el %.0f | full az %.0f el %.0f\n",
                  ra.az_deg, ra.el_deg, rb.az_deg, rb.el_deg);
}

// ---------- section 6: synthetic DOA accuracy sweep ----------
static float angular_error_deg(float az1, float el1, float az2, float el2)
{
    constexpr float kDeg2Rad { 0.017453292519943295f };
    float v1[3] { sinf(el1 * kDeg2Rad) * cosf(az1 * kDeg2Rad),
                  sinf(el1 * kDeg2Rad) * sinf(az1 * kDeg2Rad),
                  cosf(el1 * kDeg2Rad) };
    float v2[3] { sinf(el2 * kDeg2Rad) * cosf(az2 * kDeg2Rad),
                  sinf(el2 * kDeg2Rad) * sinf(az2 * kDeg2Rad),
                  cosf(el2 * kDeg2Rad) };
    float dot { v1[0] * v2[0] + v1[1] * v2[1] + v1[2] * v2[2] };
    if (dot > 1.0f)
        dot = 1.0f;
    if (dot < -1.0f)
        dot = -1.0f;
    return acosf(dot) / kDeg2Rad;
}

static void accuracy_sweep(float noise_sigma, const char* label)
{
    auto p = make_params(ArrayGeometry::kGeometries[0].positions, 8, 10.0f);
    SrpPhat::Processor srp;
    if (!srp.init(p, SrpPhat::Kernel::Recurrence))
    {
        Serial.println("  init failed");
        return;
    }
    float max_err {}, sum_err {}, sum_p2m {};
    int n {}, detected {};
    for (int ia {}; ia < 8; ++ia)
    {
        for (float el : { 10.0f, 30.0f, 50.0f, 70.0f })
        {
            float az { -180.0f + ia * 45.0f };
            synth_spectra(p.positions, p.n_mics, az, el, srp.bin_first(),
                          srp.bin_last(), noise_sigma);
            auto r = srp.process(spec_ptrs);
            float err { angular_error_deg(az, el, r.az_deg, r.el_deg) };
            if (err > max_err)
                max_err = err;
            sum_err += err;
            sum_p2m += r.peak_to_mean_db;
            ++n;
            if (r.detected)
                ++detected;
        }
    }
    Serial.printf("  %-22s mean err %5.2f deg  max err %5.2f deg  "
                  "mean p2m %4.2f dB  detected %d/%d  (grid 10 deg)\n",
                  label, sum_err / n, max_err, sum_p2m / n, detected, n);
}

static void accuracy()
{
    Serial.println("\n== synthetic DOA accuracy (ring8, 8 mics, 10 deg grid) ==");
    accuracy_sweep(0.0f, "clean");
    accuracy_sweep(0.71f, "noisy (0 dB per bin)");
}

void setup()
{
    Serial.begin(115200);
    while (!Serial)
    { /* wait for the monitor before doing ANYTHING */
    }
    CycleBench::begin();
    for (int m {}; m < 16; ++m)
        spec_ptrs[m] = spec[m];

    Serial.printf("\n=== bench_dsp @ %lu MHz, fs %.1f Hz, fft %d ===\n",
                  (unsigned long)(F_CPU_ACTUAL / 1000000), kFs, kFftSize);
    bench_bandwidth();
    bench_rfft();
    bench_scalar_ops();
    bench_steering();
    check_parity();
    accuracy();
    Serial.println("\n=== done ===");
}

void loop()
{
}
