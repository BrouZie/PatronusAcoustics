#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/complex.h>
#include <cmath>
#include <vector>

namespace py = pybind11;

/* ── SRP-PHAT beamforming (cache-friendly single-threaded) ───────────────
 *
 *  beam[f,d] = sum_m X[m,f] * phase[f,m,d]
 *  SRP[d]    = sum_f weight[f] * |beam[f,d]|^2
 *
 *  Cache-friendly f→m→d order: for a given (f,m), we stride linearly through
 *  all directions (d).  phase[f,m,:] is contiguous in memory.
 *  Two-pass: first accumulate beam_re/im across mics, then add to SRP.
 */

void compute_srp_beam(
    py::array_t<std::complex<double>> X_arr,
    py::array_t<std::complex<double>> phase_arr,
    py::array_t<double> freq_weight_arr,
    py::array_t<double> srp_out_arr
) {
    auto X = X_arr.unchecked<2>();
    auto phase = phase_arr.unchecked<3>();
    auto weight = freq_weight_arr.unchecked<1>();
    auto srp = srp_out_arr.mutable_unchecked<1>();

    int n_mics = X.shape(0);
    int n_freqs = X.shape(1);
    int n_dirs = phase.shape(2);

    for (int d = 0; d < n_dirs; ++d)
        srp(d) = 0.0;

    std::vector<double> beam_re(n_dirs);
    std::vector<double> beam_im(n_dirs);

    for (int f = 0; f < n_freqs; ++f) {
        std::fill(beam_re.begin(), beam_re.end(), 0.0);
        std::fill(beam_im.begin(), beam_im.end(), 0.0);

        for (int m = 0; m < n_mics; ++m) {
            std::complex<double> x = X(m, f);
            double xr = x.real(), xi = x.imag();
            for (int d = 0; d < n_dirs; ++d) {
                std::complex<double> p = phase(f, m, d);
                beam_re[d] += xr * p.real() - xi * p.imag();
                beam_im[d] += xr * p.imag() + xi * p.real();
            }
        }

        double w = weight(f);
        for (int d = 0; d < n_dirs; ++d) {
            srp(d) += w * (beam_re[d] * beam_re[d] + beam_im[d] * beam_im[d]);
        }
    }
}

PYBIND11_MODULE(_srp, m) {
    m.doc() = "C++ accelerated SRP-PHAT beamforming (sequential)";
    m.def("compute_srp_beam", &compute_srp_beam,
          py::arg("X"), py::arg("phase"), py::arg("freq_weight"),
          py::arg("srp_out"),
          "Compute SRP map from PHAT spectra and steering phase tensor.");
}
