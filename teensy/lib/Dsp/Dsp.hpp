#pragma once

#include <arm_math.h>

// Float32 spectral building blocks (CMSIS-DSP wrappers).
//
// Spectrum format: CMSIS rfft packing, fft_size floats total:
//   spec[0] = re(DC), spec[1] = re(Nyquist),
//   spec[2k], spec[2k+1] = re, im of bin k for k = 1 .. fft_size/2 - 1.
// All band-limited operations here take [bin_first, bin_last] with
// 1 <= bin_first <= bin_last < fft_size/2, so the packed DC/Nyquist pair is
// never touched.

namespace Dsp
{
// Periodic Hann window (matches scipy.signal.get_window("hann", n)).
void make_hann(float* w, int n);

// x[i] *= w[i]
void apply_window(const float* w, float* x, int n);

class Rfft
{
  public:
    // fft_size: 32..4096 power of two. Returns false on unsupported size.
    bool init(int fft_size);

    // time_in (fft_size samples) is clobbered; spec_out gets fft_size floats.
    void forward(float* time_in, float* spec_out);

    int size() const { return n_; }

  private:
    arm_rfft_fast_instance_f32 inst_ {};
    int n_ {};
};

// PHAT whitening: X_k /= (|X_k| + eps) for k in [bin_first, bin_last].
void phat_normalize(float* spec, int bin_first, int bin_last, float eps = 1e-12f);
} // namespace Dsp
