#pragma once

#include <stddef.h>
#include <stdint.h>

// SRP-PHAT steered-response-power DOA over a precomputed az/el grid.
//
// Conventions (match py-simulation/src/srpphat.py + geometry.py):
//   +z = boresight; elevation = polar angle from +z (0 = boresight,
//   90 = array plane); direction d = [sin e cos a, sin e sin a, cos e];
//   steering delay tau[m][d] = (pos_m . dir_d) / c;
//   steering phase = exp(-j w tau); srp[d] = sum_k |sum_m X[m][k] ph[k][m][d]|^2.
//
// Two kernels:
//   Recurrence - stores exp(-j w_first tau) and exp(-j dw tau) per (dir, mic)
//     (16 B each pair) and rotates across bins in registers. ~10-25x smaller
//     than the full table and compute-bound. The default.
//   FullTable - the full phase table exp(-j w_k tau), 8 B per (dir, bin, mic),
//     streamed once per frame. Correctness reference + the bandwidth-bound
//     calibration workload for py-simulation's MCU model.
//
// init() is the only place that allocates; process() is allocation-free.

namespace SrpPhat
{
constexpr int kMaxMics { 16 };

struct GridSpec
{
    float az_min_deg { -180.0f };
    float az_max_deg { 180.0f }; // full-circle spans drop the duplicate seam
    float el_min_deg { 0.0f };
    float el_max_deg { 90.0f };
    float resolution_deg { 10.0f };
};

struct Params
{
    const float (*positions)[3] {}; // [n_mics][3] xyz meters, array frame
    int n_mics {};
    GridSpec grid {};
    float fs { 44100.0f };
    int fft_size { 1024 };
    float min_freq { 100.0f };
    float max_freq { 1000.0f };
    float speed_of_sound { 343.0f };
    // Peak-to-mean gate. Strongly aperture/band/grid dependent: a small
    // array with a broad beam tops out ~2 dB even on clean signal (measured:
    // ring8 r=8.5cm, 100-1000 Hz -> signal ~1.6 dB vs noise-only up to
    // ~1.9 dB). Calibrate against the live noise floor; py-simulation's 5 dB
    // default assumes its much larger default geometry.
    float peak_to_mean_threshold_db { 3.0f };
};

struct Result
{
    float az_deg;
    float el_deg;
    float power;
    float peak_to_mean_db;
    bool detected;
};

enum class Kernel
{
    Recurrence,
    FullTable
};

class Processor
{
  public:
    ~Processor()
    {
        deinit();
    }

    // Builds delay/phase tables for the given geometry + search parameters.
    // Optional table_buf places the steering table in caller-owned memory
    // (e.g. a static DTCM array for benchmarks) instead of the heap; it must
    // hold table_bytes_for(p, k) bytes. Returns false on bad params or OOM.
    bool init(const Params& p, Kernel k, float* table_buf = nullptr, size_t table_buf_bytes = 0);
    void deinit();

    // spectra[m] = CMSIS-packed rfft output (fft_size floats) of mic m,
    // already PHAT-normalized over [bin_first, bin_last].
    Result process(const float* const* spectra);

    static size_t table_bytes_for(const Params& p, Kernel k);

    int n_dirs() const { return n_dirs_; }
    int n_bins() const { return n_bins_; }
    int bin_first() const { return bin_first_; }
    int bin_last() const { return bin_first_ + n_bins_ - 1; }
    size_t table_bytes() const { return table_bytes_; }
    const float* power_map() const { return srp_; } // [n_dirs]
    float az_of(int d) const { return az_deg_[d]; }
    float el_of(int d) const { return el_deg_[d]; }

    // Complex MACs per frame as defined by py-simulation's MCU model
    // (n_bins * n_mics * n_dirs), for cmacs-per-cycle reporting.
    uint64_t cmacs_per_frame() const { return (uint64_t)n_bins_ * n_mics_ * n_dirs_; }

    // Per-stage DWT cycle counts from the last process() call
    // (0 unless the cycle counter is enabled, e.g. via CycleBench::begin()).
    uint32_t last_steering_cycles() const { return steering_cycles_; }
    uint32_t last_peak_cycles() const { return peak_cycles_; }

  private:
    static int grid_counts(const GridSpec& g, int* n_az, int* n_el);
    void steer_recurrence();
    void steer_full_table();

    Kernel kernel_ { Kernel::Recurrence };
    int n_mics_ {};
    int n_dirs_ {};
    int n_bins_ {};
    int bin_first_ {};
    float thresh_db_ {};

    float* table_ {}; // steering table, layout per kernel (see .cpp)
    bool table_owned_ {};
    size_t table_bytes_ {};
    float* xband_ {};  // [n_bins][n_mics][2] bin-major repack of spectra
    float* srp_ {};    // [n_dirs] power map
    float* az_deg_ {}; // [n_dirs]
    float* el_deg_ {}; // [n_dirs]

    uint32_t steering_cycles_ {};
    uint32_t peak_cycles_ {};
};
} // namespace SrpPhat
