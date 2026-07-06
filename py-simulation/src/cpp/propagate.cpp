#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <cmath>
#include <algorithm>
#include <cstring>
#include <fftw3.h>

namespace py = pybind11;

/* ── Windowed-sinc fractional delay ──────────────────────────────────────
 *
 * 16-tap Kaiser (β = 8.6) sinc interpolator, mirroring drone_signal.py
 * exactly (same I0 power series, same tap layout) so the Python fallback
 * and this extension agree to ~1e-15. Keep both in sync.
 */

static const int SINC_TAPS = 16;
static const double KAISER_BETA = 8.6;

static double bessel_i0(double x) {
    /* Same power series as drone_signal._i0 — NOT std::cyl_bessel_i,
     * whose rounding differs from the Python-side series. */
    double half2 = (x / 2.0) * (x / 2.0);
    double term = 1.0, total = 1.0;
    for (int k = 1; k < 60; ++k) {
        term *= half2 / ((double)k * (double)k);
        total += term;
        if (term < 1e-18 * total) break;
    }
    return total;
}

static const double I0_BETA = bessel_i0(KAISER_BETA);

static inline double sinc_kernel(double x) {
    const double half = SINC_TAPS / 2.0;
    if (std::abs(x) > half) return 0.0;
    double arg = 1.0 - (x / half) * (x / half);
    if (arg < 0.0) arg = 0.0;
    double window = bessel_i0(KAISER_BETA * std::sqrt(arg)) / I0_BETA;
    double s = (x == 0.0) ? 1.0 : std::sin(M_PI * x) / (M_PI * x);
    return s * window;
}

/* Retarded emission time: fixed-point iterations of t_e = t − d(t_e)/c,
 * mirroring drone_signal._retarded_distances (three passes; position is
 * linearly interpolated and edge-clamped exactly like np.interp). */
static const int RETARDED_TIME_ITERS = 3;

template <typename Acc>
static double retarded_distance(
    const Acc& pos, int n_work,
    double mx, double my, double mz,
    int i, double fs, double speed_sound
) {
    double dx = mx - pos(i, 0);
    double dy = my - pos(i, 1);
    double dz = mz - pos(i, 2);
    double d = std::sqrt(dx*dx + dy*dy + dz*dz);

    for (int it = 0; it < RETARDED_TIME_ITERS; ++it) {
        double t_e = (double)i - d / speed_sound * fs;
        double px, py_, pz;
        if (t_e <= 0.0) {
            px = pos(0, 0); py_ = pos(0, 1); pz = pos(0, 2);
        } else if (t_e >= (double)(n_work - 1)) {
            px = pos(n_work - 1, 0); py_ = pos(n_work - 1, 1);
            pz = pos(n_work - 1, 2);
        } else {
            int j = (int)std::floor(t_e);
            double frac = t_e - (double)j;
            px  = (1.0 - frac) * pos(j, 0) + frac * pos(j + 1, 0);
            py_ = (1.0 - frac) * pos(j, 1) + frac * pos(j + 1, 1);
            pz  = (1.0 - frac) * pos(j, 2) + frac * pos(j + 1, 2);
        }
        dx = mx - px; dy = my - py_; dz = mz - pz;
        d = std::sqrt(dx*dx + dy*dy + dz*dz);
    }
    return d;
}

template <typename Acc>
static double sinc_read(const Acc& src, int n, double read_pos) {
    int idx_int = (int)std::floor(read_pos);
    double frac = read_pos - (double)idx_int;
    double acc = 0.0;
    for (int o = -SINC_TAPS / 2 + 1; o <= SINC_TAPS / 2; ++o) {
        int s = idx_int + o;
        if (s < 0 || s >= n) continue;
        acc += sinc_kernel(frac - (double)o) * src(s);
    }
    return acc;
}

/* ── Direct-path propagation (moving source, per-sample) ─────────────── */

py::array_t<double> propagate_moving(
    py::array_t<double> source,
    py::array_t<double> mic_positions,
    py::array_t<double> positions,
    double fs,
    double speed_sound,
    py::array_t<double> turbulence
) {
    auto src = source.unchecked<1>();
    auto mic = mic_positions.unchecked<2>();
    auto pos = positions.unchecked<2>();
    auto turb = turbulence.unchecked<2>();

    int n = src.shape(0);
    int n_mics = mic.shape(0);
    int n_pos = pos.shape(0);
    int n_work = std::min(n, n_pos);

    auto result = py::array_t<double>({n_mics, n});
    auto res = result.mutable_unchecked<2>();

    for (int m = 0; m < n_mics; ++m)
        for (int j = 0; j < n; ++j)
            res(m, j) = 0.0;

    for (int i = 0; i < n_work; ++i) {
        for (int m = 0; m < n_mics; ++m) {
            double dist = retarded_distance(
                pos, n_work, mic(m, 0), mic(m, 1), mic(m, 2),
                i, fs, speed_sound);
            double atten = 1.0 / (dist + 1e-6);

            double delay = dist / speed_sound + turb(m, i);
            double read_pos = (double)i - delay * fs;
            res(m, i) = atten * sinc_read(src, n, read_pos);
        }
    }

    return result;
}


/* ── Reflected-path propagation (moving source, per-sample) ──────────── */

py::array_t<double> propagate_reflected_moving(
    py::array_t<double> source,
    py::array_t<double> mic_positions,
    py::array_t<double> positions,
    py::array_t<double> image_positions,
    double fs,
    double speed_sound,
    py::array_t<double> turbulence,
    double reflection_coefficient
) {
    auto src = source.unchecked<1>();
    auto mic = mic_positions.unchecked<2>();
    auto pos = positions.unchecked<2>();
    auto img = image_positions.unchecked<2>();
    auto turb = turbulence.unchecked<2>();

    int n = src.shape(0);
    int n_mics = mic.shape(0);
    int n_pos = pos.shape(0);
    int n_work = std::min(n, n_pos);

    auto result = py::array_t<double>({n_mics, n});
    auto res = result.mutable_unchecked<2>();

    for (int m = 0; m < n_mics; ++m)
        for (int j = 0; j < n; ++j)
            res(m, j) = 0.0;

    double R = reflection_coefficient;

    for (int i = 0; i < n_work; ++i) {
        for (int m = 0; m < n_mics; ++m) {
            double dist_image = retarded_distance(
                img, n_work, mic(m, 0), mic(m, 1), mic(m, 2),
                i, fs, speed_sound);

            /* Image-source amplitude R/d_image (see drone_signal.py). */
            double atten = R / (dist_image + 1e-6);

            double delay = dist_image / speed_sound + turb(m, i) * 0.5;
            double read_pos = (double)i - delay * fs;
            res(m, i) = -atten * sinc_read(src, n, read_pos);
        }
    }

    return result;
}


/* ── Absorption OLA post-process (FFTW accelerated) ───────────────────── */

py::array_t<double> apply_absorption_ola(
    py::array_t<double> mic_signals,
    py::array_t<double> distances,
    double fs,
    py::array_t<double> alpha_coeffs,
    int block_size,
    int hop,
    py::array_t<double> window_arr
) {
    auto sig = mic_signals.unchecked<2>();
    auto dist = distances.unchecked<2>();
    auto alpha = alpha_coeffs.unchecked<1>();
    auto win = window_arr.unchecked<1>();

    int n_mics = sig.shape(0);
    int n = sig.shape(1);
    int n_freq = block_size / 2 + 1;

    auto result = py::array_t<double>({n_mics, n});
    auto out = result.mutable_unchecked<2>();
    std::memset(result.mutable_data(), 0, sizeof(double) * n_mics * n);

    auto overlap = py::array_t<double>(n);
    auto ov = overlap.mutable_unchecked<1>();
    std::memset(overlap.mutable_data(), 0, sizeof(double) * n);

    if (n < block_size)
        return mic_signals;

    double* in = (double*)fftw_malloc(sizeof(double) * block_size);
    fftw_complex* fft_out = (fftw_complex*)fftw_malloc(sizeof(fftw_complex) * n_freq);
    fftw_plan fwd = fftw_plan_dft_r2c_1d(block_size, in, fft_out, FFTW_ESTIMATE);
    fftw_plan inv = fftw_plan_dft_c2r_1d(block_size, fft_out, in, FFTW_ESTIMATE);

    for (int start = 0; start <= n - block_size; start += hop) {
        int center = start + block_size / 2;

        for (int m = 0; m < n_mics; ++m) {
            double d_m = dist(m, center);

            for (int j = 0; j < block_size; ++j)
                in[j] = sig(m, start + j) * win(j);

            fftw_execute(fwd);

            for (int f = 0; f < n_freq; ++f) {
                double H = std::exp(-alpha(f) * d_m / 8.686);
                fft_out[f][0] *= H;
                fft_out[f][1] *= H;
            }

            fftw_execute(inv);

            double inv_n = 1.0 / (double)block_size;
            for (int j = 0; j < block_size; ++j)
                out(m, start + j) += in[j] * inv_n;
        }

        for (int j = 0; j < block_size; ++j)
            ov(start + j) += 1.0;
    }

    fftw_destroy_plan(fwd);
    fftw_destroy_plan(inv);
    fftw_free(in);
    fftw_free(fft_out);

    for (int m = 0; m < n_mics; ++m)
        for (int j = 0; j < n; ++j)
            out(m, j) /= (ov(j) + 1e-10);

    return result;
}


PYBIND11_MODULE(_propagate, m) {
    m.doc() = "C++ accelerated drone signal propagation routines";
    m.attr("SINC_TAPS") = SINC_TAPS;  // feature flag checked by drone_signal
    m.def("propagate_moving", &propagate_moving,
          py::arg("source"), py::arg("mic_positions"), py::arg("positions"),
          py::arg("fs"), py::arg("speed_sound"), py::arg("turbulence"),
          "Per-sample direct-path propagation, windowed-sinc interpolation.");
    m.def("propagate_reflected_moving", &propagate_reflected_moving,
          py::arg("source"), py::arg("mic_positions"),
          py::arg("positions"), py::arg("image_positions"),
          py::arg("fs"), py::arg("speed_sound"),
          py::arg("turbulence"), py::arg("reflection_coefficient"),
          "Per-sample reflected-path propagation, windowed-sinc interpolation.");
    m.def("apply_absorption_ola", &apply_absorption_ola,
          py::arg("mic_signals"), py::arg("distances"),
          py::arg("fs"), py::arg("alpha_coeffs"),
          py::arg("block_size"), py::arg("hop"),
          py::arg("window_arr"),
          "FFTW-accelerated absorption overlap-add post-process.");
}
