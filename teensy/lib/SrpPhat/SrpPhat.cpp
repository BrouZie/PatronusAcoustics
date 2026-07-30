#include "SrpPhat.hpp"

#include <Arduino.h> // ARM_DWT_CYCCNT
#include <math.h>
#include <new>

// Table layouts (built in init, streamed in process):
//   Recurrence: [n_dirs][n_mics][4] = base_re, base_im, inc_re, inc_im
//     where base = exp(-j w_first tau), inc = exp(-j dw tau)
//   FullTable:  [n_dirs][n_bins][n_mics][2] = re, im of exp(-j w_k tau)
// Both are direction-major so each direction is one contiguous stream.

namespace SrpPhat
{
namespace
{
constexpr float kDegToRad { 0.017453292519943295f };

// Inclusive-endpoint step count, matching py-simulation's
// arange(min, max + res/2, res) convention.
int count_inclusive(float min, float max, float res)
{
    return (int)floorf((max - min) / res + 0.5f) + 1;
}
} // namespace

int Processor::grid_counts(const GridSpec& g, int* n_az, int* n_el)
{
    *n_az = count_inclusive(g.az_min_deg, g.az_max_deg, g.resolution_deg);
    // full-circle azimuth: drop the duplicate +180 == -180 seam point
    if (g.az_max_deg - g.az_min_deg >= 360.0f - 0.5f * g.resolution_deg)
        *n_az -= 1;
    *n_el = count_inclusive(g.el_min_deg, g.el_max_deg, g.resolution_deg);
    return *n_az * *n_el;
}

size_t Processor::table_bytes_for(const Params& p, Kernel k)
{
    int n_az {}, n_el {};
    int n_dirs { grid_counts(p.grid, &n_az, &n_el) };
    float bin_width { p.fs / p.fft_size };
    int bin_first { (int)ceilf(p.min_freq / bin_width) };
    if (bin_first < 1)
        bin_first = 1;
    int bin_last { (int)floorf(p.max_freq / bin_width) };
    if (bin_last > p.fft_size / 2 - 1)
        bin_last = p.fft_size / 2 - 1;
    int n_bins { bin_last - bin_first + 1 };
    if (k == Kernel::Recurrence)
        return (size_t)n_dirs * p.n_mics * 4 * sizeof(float);
    return (size_t)n_dirs * n_bins * p.n_mics * 2 * sizeof(float);
}

bool Processor::init(const Params& p, Kernel k, float* table_buf, size_t table_buf_bytes)
{
    deinit();
    if (!p.positions || p.n_mics < 2 || p.n_mics > kMaxMics)
        return false;

    kernel_    = k;
    n_mics_    = p.n_mics;
    thresh_db_ = p.peak_to_mean_threshold_db;

    float bin_width { p.fs / p.fft_size };
    bin_first_ = (int)ceilf(p.min_freq / bin_width);
    if (bin_first_ < 1)
        bin_first_ = 1;
    int bin_last { (int)floorf(p.max_freq / bin_width) };
    if (bin_last > p.fft_size / 2 - 1)
        bin_last = p.fft_size / 2 - 1;
    n_bins_ = bin_last - bin_first_ + 1;
    if (n_bins_ < 1)
        return false;

    int n_az {}, n_el {};
    n_dirs_ = grid_counts(p.grid, &n_az, &n_el);
    if (n_dirs_ < 1)
        return false;

    table_bytes_ = table_bytes_for(p, k);
    if (table_buf)
    {
        if (table_buf_bytes < table_bytes_)
            return false;
        table_       = table_buf;
        table_owned_ = false;
    }
    else
    {
        table_       = new (std::nothrow) float[table_bytes_ / sizeof(float)];
        table_owned_ = true;
    }
    xband_  = new (std::nothrow) float[(size_t)n_bins_ * n_mics_ * 2];
    srp_    = new (std::nothrow) float[n_dirs_];
    az_deg_ = new (std::nothrow) float[n_dirs_];
    el_deg_ = new (std::nothrow) float[n_dirs_];
    if (!table_ || !xband_ || !srp_ || !az_deg_ || !el_deg_)
    {
        deinit();
        return false;
    }

    // w_k = 2 pi (bin_first + k) fs / fft_size; dw = 2 pi fs / fft_size
    float dw { 2.0f * (float)M_PI * bin_width };
    float w_first { dw * bin_first_ };
    float inv_c { 1.0f / p.speed_of_sound };
    float res { p.grid.resolution_deg };

    for (int ia {}; ia < n_az; ++ia)
    {
        float az { p.grid.az_min_deg + ia * res };
        for (int ie {}; ie < n_el; ++ie)
        {
            float el { p.grid.el_min_deg + ie * res };
            int d { ia * n_el + ie };
            az_deg_[d] = az;
            el_deg_[d] = el;

            float sin_el { sinf(el * kDegToRad) };
            float dir[3] { sin_el * cosf(az * kDegToRad), sin_el * sinf(az * kDegToRad),
                           cosf(el * kDegToRad) };

            for (int m {}; m < n_mics_; ++m)
            {
                const float* pos { p.positions[m] };
                float tau { (pos[0] * dir[0] + pos[1] * dir[1] + pos[2] * dir[2]) * inv_c };
                if (k == Kernel::Recurrence)
                {
                    float* t { table_ + ((size_t)d * n_mics_ + m) * 4 };
                    t[0] = cosf(-w_first * tau);
                    t[1] = sinf(-w_first * tau);
                    t[2] = cosf(-dw * tau);
                    t[3] = sinf(-dw * tau);
                }
                else
                {
                    for (int kb {}; kb < n_bins_; ++kb)
                    {
                        float w { w_first + kb * dw };
                        float* t { table_ + (((size_t)d * n_bins_ + kb) * n_mics_ + m) * 2 };
                        t[0] = cosf(-w * tau);
                        t[1] = sinf(-w * tau);
                    }
                }
            }
        }
    }
    return true;
}

void Processor::deinit()
{
    if (table_owned_)
        delete[] table_;
    table_       = nullptr;
    table_owned_ = false;
    delete[] xband_;
    delete[] srp_;
    delete[] az_deg_;
    delete[] el_deg_;
    xband_  = nullptr;
    srp_    = nullptr;
    az_deg_ = nullptr;
    el_deg_ = nullptr;
    n_dirs_ = 0;
}

Result Processor::process(const float* const* spectra)
{
    // Repack the band bin-major so the inner mic loop reads contiguously:
    // xband[k][m] = spectra[m][bin_first + k]
    for (int m {}; m < n_mics_; ++m)
    {
        const float* s { spectra[m] + 2 * bin_first_ };
        float* x { xband_ + 2 * m };
        for (int kb {}; kb < n_bins_; ++kb)
        {
            x[0]  = s[0];
            x[1]  = s[1];
            s    += 2;
            x    += 2 * n_mics_;
        }
    }

    uint32_t t0 { ARM_DWT_CYCCNT };
    if (kernel_ == Kernel::Recurrence)
        steer_recurrence();
    else
        steer_full_table();
    uint32_t t1 { ARM_DWT_CYCCNT };
    steering_cycles_ = t1 - t0;

    // Peak + peak-to-mean detection gate
    float peak { srp_[0] };
    int peak_d {};
    float sum {};
    for (int d {}; d < n_dirs_; ++d)
    {
        float v { srp_[d] };
        sum += v;
        if (v > peak)
        {
            peak   = v;
            peak_d = d;
        }
    }
    float mean { sum / n_dirs_ };
    float p2m_db { 10.0f * log10f(peak / (mean + 1e-20f) + 1e-20f) };
    peak_cycles_ = ARM_DWT_CYCCNT - t1;

    Result r;
    r.az_deg          = az_deg_[peak_d];
    r.el_deg          = el_deg_[peak_d];
    r.power           = peak;
    r.peak_to_mean_db = p2m_db;
    r.detected        = p2m_db >= thresh_db_;
    return r;
}

void Processor::steer_recurrence()
{
    for (int d {}; d < n_dirs_; ++d)
    {
        const float* t { table_ + (size_t)d * n_mics_ * 4 };
        float phr[kMaxMics], phi[kMaxMics], incr[kMaxMics], inci[kMaxMics];
        for (int m {}; m < n_mics_; ++m)
        {
            phr[m]  = t[4 * m + 0];
            phi[m]  = t[4 * m + 1];
            incr[m] = t[4 * m + 2];
            inci[m] = t[4 * m + 3];
        }

        const float* xb { xband_ };
        float acc {};
        for (int kb {}; kb < n_bins_; ++kb)
        {
            float br {}, bi {};
            for (int m {}; m < n_mics_; ++m)
            {
                float xr { xb[2 * m] };
                float xi { xb[2 * m + 1] };
                br += xr * phr[m] - xi * phi[m];
                bi += xr * phi[m] + xi * phr[m];
                float nr { phr[m] * incr[m] - phi[m] * inci[m] };
                float ni { phr[m] * inci[m] + phi[m] * incr[m] };
                phr[m] = nr;
                phi[m] = ni;
            }
            acc += br * br + bi * bi;
            xb  += 2 * n_mics_;
        }
        srp_[d] = acc;
    }
}

void Processor::steer_full_table()
{
    const float* t { table_ };
    for (int d {}; d < n_dirs_; ++d)
    {
        const float* xb { xband_ };
        float acc {};
        for (int kb {}; kb < n_bins_; ++kb)
        {
            float br {}, bi {};
            for (int m {}; m < n_mics_; ++m)
            {
                float xr { xb[2 * m] };
                float xi { xb[2 * m + 1] };
                float pr { t[0] };
                float pi { t[1] };
                t  += 2;
                br += xr * pr - xi * pi;
                bi += xr * pi + xi * pr;
            }
            acc += br * br + bi * bi;
            xb  += 2 * n_mics_;
        }
        srp_[d] = acc;
    }
}
} // namespace SrpPhat
