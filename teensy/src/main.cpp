/// SRP-PHAT LIVE PIPELINE (development driver)
///
/// ICS-52000 TDM capture -> windowed f32 RFFT -> PHAT -> SRP steering ->
/// az/el over serial, with per-stage cycle counts and headroom. Geometry
/// comes from include/ArrayGeometry.hpp; mic count, grid resolution and
/// kernel are chosen at launch.
#include <ArrayGeometry.hpp>
#include <Audio.h>
#include <AudioCapture.hpp>
#include <CycleBench.hpp>
#include <Dsp.hpp>
#include <SerialPrompt.hpp>
#include <SrpPhat.hpp>

// ---------- Config ----------
constexpr int kFftSize { 1024 }; // 43 Hz bins, 23 ms window at 44.1 kHz
constexpr int kHop { 512 };      // 11.6 ms frame budget
constexpr float kMinFreq { 100.0f };
constexpr float kMaxFreq { 1000.0f };
// One TDM bus = 8 x 32-bit slots; mic i arrives on Audio channel 2i.
constexpr int kMaxMics { 8 };
// ----------------------------

// The sketch owns and wires its own audio graph; lib/ only provides
// app-agnostic building blocks.
AudioInputTDM tdm;
AudioCapture capture;
AudioConnection* patch[kMaxMics];

Dsp::Rfft rfft;
SrpPhat::Processor srp;
int numMics { 0 };
uint32_t frameBudget { 0 }; // cycles available per hop

float hann[kFftSize];
float frame[kFftSize];
float spectra[kMaxMics][kFftSize];
const float* spec_ptrs[kMaxMics];

void setup()
{
    Serial.begin(115200);
    while (!Serial)
    { /* wait for the monitor before doing ANYTHING */
    }
    CycleBench::begin();

    // ----- launch-time choices -----
    const char* geom_names[ArrayGeometry::kGeometryCount];
    for (int i {}; i < ArrayGeometry::kGeometryCount; ++i)
        geom_names[i] = ArrayGeometry::kGeometries[i].name;
    const ArrayGeometry::Geometry& geom { ArrayGeometry::kGeometries[SerialPrompt::ask_choice(
        Serial, "Array geometry:", geom_names, ArrayGeometry::kGeometryCount)] };
    numMics = SerialPrompt::ask_mic_count(Serial, geom.n_mics < kMaxMics ? geom.n_mics : kMaxMics);

    const char* res_names[] { "6 deg", "10 deg", "15 deg" };
    const float res_values[] { 6.0f, 10.0f, 15.0f };
    float res { res_values[SerialPrompt::ask_choice(Serial, "Grid resolution:", res_names, 3)] };

    const char* kernel_names[] { "recurrence (compact table)", "full table (streaming)" };
    SrpPhat::Kernel kernel { SerialPrompt::ask_choice(Serial, "Steering kernel:", kernel_names,
                                                      2) == 0
                                 ? SrpPhat::Kernel::Recurrence
                                 : SrpPhat::Kernel::FullTable };

    // ----- DSP init (all allocation happens here) -----
    SrpPhat::Params p;
    p.positions = geom.positions;
    p.n_mics    = numMics;
    p.grid      = SrpPhat::GridSpec { -180.0f, 180.0f, 0.0f, 90.0f, res };
    p.fs        = AUDIO_SAMPLE_RATE_EXACT;
    p.fft_size  = kFftSize;
    p.min_freq  = kMinFreq;
    p.max_freq  = kMaxFreq;
    if (!srp.init(p, kernel))
    {
        Serial.printf("SrpPhat init FAILED (table %lu KB - OOM or bad params). "
                      "Halting.\n",
                      (unsigned long)(SrpPhat::Processor::table_bytes_for(p, kernel) / 1024));
        for (;;)
        {
        }
    }
    Dsp::make_hann(hann, kFftSize);
    rfft.init(kFftSize);
    for (int m {}; m < numMics; ++m)
        spec_ptrs[m] = spectra[m];

    // ----- audio graph -----
    AudioMemory(30 + kMaxMics * 8); // compile-time constant; worst case
    capture.begin(numMics, kFftSize, kHop);
    for (int m {}; m < numMics; ++m)
        patch[m] = new AudioConnection(tdm, m * 2, capture, m);
    delay(300); // let the ICS-52000s finish startup/unmute

    frameBudget = (uint32_t)((float)kHop / AUDIO_SAMPLE_RATE_EXACT * (float)F_CPU_ACTUAL);
    Serial.printf("\nSRP-PHAT: %d mics, %d dirs (res %.0f deg), bins %d-%d "
                  "(%d), table %lu KB, budget %lu cycles/frame @ %lu MHz\n",
                  numMics, srp.n_dirs(), res, srp.bin_first(), srp.bin_last(), srp.n_bins(),
                  (unsigned long)(srp.table_bytes() / 1024), (unsigned long)frameBudget,
                  (unsigned long)(F_CPU_ACTUAL / 1000000));
}

void loop()
{
    if (!capture.frameReady())
        return;

    uint32_t t0 { CycleBench::now() };
    for (int m {}; m < numMics; ++m)
    {
        capture.readFrame(m, frame);
        Dsp::apply_window(hann, frame, kFftSize);
        rfft.forward(frame, spectra[m]);
        Dsp::phat_normalize(spectra[m], srp.bin_first(), srp.bin_last());
    }
    capture.consumeFrame(); // frames are copied out; capture may roll on
    uint32_t fftCycles { CycleBench::now() - t0 };

    SrpPhat::Result r { srp.process(spec_ptrs) };
    uint32_t totalCycles { CycleBench::now() - t0 };

    // running perf aggregates
    static uint32_t frames { 0 }, maxTotal { 0 };
    static uint64_t sumTotal { 0 };
    ++frames;
    sumTotal += totalCycles;
    if (totalCycles > maxTotal)
        maxTotal = totalCycles;

    // DOA at ~5 Hz
    static uint32_t lastDoa { 0 };
    if (millis() - lastDoa >= 200)
    {
        lastDoa = millis();
        Serial.printf("az %6.1f  el %5.1f  p2m %5.2f dB  %s\n", r.az_deg, r.el_deg,
                      r.peak_to_mean_db, r.detected ? "DETECT" : "-");
    }

    // perf report every 2 s
    static uint32_t lastPerf { 0 };
    if (millis() - lastPerf >= 2000)
    {
        lastPerf = millis();
        uint32_t avg { (uint32_t)(sumTotal / frames) };
        Serial.printf("[perf] fft+phat %lu  steer %lu  peak %lu  "
                      "total avg %lu max %lu / budget %lu (%.1f%%)  "
                      "overruns %lu  audioISR %.1f%% mem %d\n",
                      (unsigned long)fftCycles, (unsigned long)srp.last_steering_cycles(),
                      (unsigned long)srp.last_peak_cycles(), (unsigned long)avg,
                      (unsigned long)maxTotal, (unsigned long)frameBudget,
                      100.0f * avg / frameBudget, (unsigned long)capture.overruns(),
                      AudioProcessorUsageMax(), AudioMemoryUsageMax());
        AudioProcessorUsageMaxReset();
        frames   = 0;
        sumTotal = 0;
        maxTotal = 0;
    }
}
