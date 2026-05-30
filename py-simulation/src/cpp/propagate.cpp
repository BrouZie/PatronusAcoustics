#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <cmath>
#include <algorithm>
#include <cstring>
#include <fftw3.h>

namespace py = pybind11;

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
        double px = pos(i, 0), py = pos(i, 1), pz = pos(i, 2);

        for (int m = 0; m < n_mics; ++m) {
            double dx = mic(m, 0) - px;
            double dy = mic(m, 1) - py;
            double dz = mic(m, 2) - pz;
            double dist = std::sqrt(dx*dx + dy*dy + dz*dz);
            double atten = 1.0 / (dist + 1e-6);

            double delay = dist / speed_sound + turb(m, i);
            double delay_samp = delay * fs;
            double idx_float = (double)i - delay_samp;
            int idx_int = (int)std::floor(idx_float);
            double frac = idx_float - (double)idx_int;

            if (idx_int >= 0 && idx_int < n - 1) {
                double val = (1.0 - frac) * src(idx_int) + frac * src(idx_int + 1);
                res(m, i) = atten * val;
            }
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
        double px = pos(i, 0), py = pos(i, 1), pz = pos(i, 2);
        double ix = img(i, 0), iy = img(i, 1), iz = img(i, 2);

        for (int m = 0; m < n_mics; ++m) {
            double dx_d = mic(m, 0) - px;
            double dy_d = mic(m, 1) - py;
            double dz_d = mic(m, 2) - pz;
            double dist_direct = std::sqrt(dx_d*dx_d + dy_d*dy_d + dz_d*dz_d);

            double dx_i = mic(m, 0) - ix;
            double dy_i = mic(m, 1) - iy;
            double dz_i = mic(m, 2) - iz;
            double dist_image = std::sqrt(dx_i*dx_i + dy_i*dy_i + dz_i*dz_i);

            double atten = R * dist_direct / (dist_image + 1e-6);

            double delay = dist_image / speed_sound + turb(m, i) * 0.5;
            double delay_samp = delay * fs;
            double idx_float = (double)i - delay_samp;
            int idx_int = (int)std::floor(idx_float);
            double frac = idx_float - (double)idx_int;

            if (idx_int >= 0 && idx_int < n - 1) {
                double val = (1.0 - frac) * src(idx_int) + frac * src(idx_int + 1);
                res(m, i) = -atten * val;
            }
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
    m.def("propagate_moving", &propagate_moving,
          py::arg("source"), py::arg("mic_positions"), py::arg("positions"),
          py::arg("fs"), py::arg("speed_sound"), py::arg("turbulence"),
          "Per-sample direct-path propagation with linear interpolation.");
    m.def("propagate_reflected_moving", &propagate_reflected_moving,
          py::arg("source"), py::arg("mic_positions"),
          py::arg("positions"), py::arg("image_positions"),
          py::arg("fs"), py::arg("speed_sound"),
          py::arg("turbulence"), py::arg("reflection_coefficient"),
          "Per-sample reflected-path propagation with linear interpolation.");
    m.def("apply_absorption_ola", &apply_absorption_ola,
          py::arg("mic_signals"), py::arg("distances"),
          py::arg("fs"), py::arg("alpha_coeffs"),
          py::arg("block_size"), py::arg("hop"),
          py::arg("window_arr"),
          "FFTW-accelerated absorption overlap-add post-process.");
}
