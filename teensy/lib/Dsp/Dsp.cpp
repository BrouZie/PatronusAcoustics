#include "Dsp.hpp"

#include <math.h>

namespace Dsp
{
void make_hann(float* w, int n)
{
    for (int i {}; i < n; ++i)
        w[i] = 0.5f - 0.5f * cosf(2.0f * (float)M_PI * i / n);
}

void apply_window(const float* w, float* x, int n)
{
    arm_mult_f32(const_cast<float*>(w), x, x, n);
}

bool Rfft::init(int fft_size)
{
    if (arm_rfft_fast_init_f32(&inst_, fft_size) != ARM_MATH_SUCCESS)
        return false;
    n_ = fft_size;
    return true;
}

void Rfft::forward(float* time_in, float* spec_out)
{
    arm_rfft_fast_f32(&inst_, time_in, spec_out, 0);
}

void phat_normalize(float* spec, int bin_first, int bin_last, float eps)
{
    for (int k { bin_first }; k <= bin_last; ++k)
    {
        float re { spec[2 * k] };
        float im { spec[2 * k + 1] };
        float scale { 1.0f / (sqrtf(re * re + im * im) + eps) };
        spec[2 * k]     = re * scale;
        spec[2 * k + 1] = im * scale;
    }
}
} // namespace Dsp
