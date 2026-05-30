#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/complex.h>
#include <cmath>
#include <random>
#include <algorithm>
#include <cstring>

namespace py = pybind11;

/* ── In-place 16×16 Cholesky (lower-triangular) ───────────────────────────
 *  Returns false if matrix is not positive-definite.
 *  On success, A[lower] is overwritten with L.
 */

static bool cholesky_16x16(double* A) {
    constexpr int n = 16;
    for (int j = 0; j < n; ++j) {
        double s = 0.0;
        for (int k = 0; k < j; ++k)
            s += A[j*n + k] * A[j*n + k];
        double val = A[j*n + j] - s;
        if (val <= 0.0) return false;
        A[j*n + j] = std::sqrt(val);

        for (int i = j + 1; i < n; ++i) {
            s = 0.0;
            for (int k = 0; k < j; ++k)
                s += A[i*n + k] * A[j*n + k];
            A[i*n + j] = (A[i*n + j] - s) / A[j*n + j];
        }
    }
    return true;
}


/* ── Lower-triangular mat-vec: y = L * x (L is 16×16, stored full, lower half used) ── */

static void lt_mul_16x16(const double* L, const double* x, double* y) {
    constexpr int n = 16;
    for (int i = 0; i < n; ++i) {
        double sum = 0.0;
        for (int j = 0; j <= i; ++j)
            sum += L[i*n + j] * x[j];
        y[i] = sum;
    }
}


/* ── Generate wind noise frequency-domain coefficients (Corcos model) ────
 *
 *  Fills positive-frequency bins in X_fft (n_mics, n_pad) with
 *  Corcos-correlated complex wind noise.  DC, Nyquist, and negative
 *  frequencies are left for the caller (which can vectorise them in
 *  numpy more efficiently than strided C++ writes).
 *
 *  Arguments:
 *    dists       – (n_mics, n_mics) pairwise microphone distances
 *    freqs       – (n_pad,)  frequency array
 *    env         – (n_pad,)  spectral envelope (brown noise + LPF)
 *    pos_idx     – (n_pos,)  indices of positive frequencies
 *    alpha       – Corcos constant
 *    U           – wind speed (clamped ≥ 0.1)
 *    n_mics      – number of microphones (expected 16)
 *    seed        – random seed
 *    X_fft       – (n_mics, n_pad) complex128, modified in-place
 */

void generate_wind_frequencies(
    py::array_t<double> dists_arr,
    py::array_t<double> freqs_arr,
    py::array_t<double> env_arr,
    py::array_t<int64_t> pos_idx_arr,
    double alpha,
    double U,
    int n_mics,
    uint64_t seed,
    py::array_t<std::complex<double>> X_fft_arr
) {
    auto dists = dists_arr.unchecked<2>();
    auto freqs = freqs_arr.unchecked<1>();
    auto env = env_arr.unchecked<1>();
    auto pos_idx = pos_idx_arr.unchecked<1>();
    auto X = X_fft_arr.mutable_unchecked<2>();

    int n_pos = pos_idx.shape(0);
    int nm = n_mics;

    // Pre-compute dists as flat 16×16 array for fast access
    constexpr int N = 16;
    double dists_flat[N * N];
    for (int i = 0; i < nm; ++i)
        for (int j = 0; j < nm; ++j)
            dists_flat[i * N + j] = dists(i, j);

    std::mt19937_64 rng(seed);
    std::normal_distribution<double> normal(0.0, 1.0);

    // Temporary arrays (stack-allocated)
    double Gamma[N * N];
    double Z_real[N], Z_imag[N];
    double LZ_real[N], LZ_imag[N];

    double reg = 1e-8;
    double inv_sqrt2 = 1.0 / std::sqrt(2.0);

    for (int p = 0; p < n_pos; ++p) {
        int idx = static_cast<int>(pos_idx(p));
        double f = freqs(idx);
        double coeff = -alpha * f / U;

        // Build Gamma = exp(coeff * dists) + reg * I
        for (int i = 0; i < nm; ++i) {
            for (int j = 0; j < nm; ++j) {
                double val = std::exp(coeff * dists_flat[i * N + j]);
                if (i == j) val += reg;
                Gamma[i * N + j] = val;
            }
        }

        // Cholesky
        bool ok = cholesky_16x16(Gamma);
        if (!ok) {
            // Fallback: identity (L = I)
            std::memset(Gamma, 0, sizeof(double) * N * N);
            for (int i = 0; i < nm; ++i)
                Gamma[i * N + i] = 1.0;
        }

        // Random vector Z = (randn + i*randn) / sqrt(2)
        for (int i = 0; i < nm; ++i) {
            Z_real[i] = normal(rng) * inv_sqrt2;
            Z_imag[i] = normal(rng) * inv_sqrt2;
        }

        // LZ = L @ Z
        lt_mul_16x16(Gamma, Z_real, LZ_real);
        lt_mul_16x16(Gamma, Z_imag, LZ_imag);

        // Store positive frequency
        double e = env(idx);
        for (int m = 0; m < nm; ++m) {
            X(m, idx) = std::complex<double>(LZ_real[m] * e, LZ_imag[m] * e);
        }
    }
}


PYBIND11_MODULE(_noise, m) {
    m.doc() = "C++ accelerated noise generation routines";
    m.def("generate_wind_frequencies", &generate_wind_frequencies,
          py::arg("dists"), py::arg("freqs"), py::arg("env"),
          py::arg("pos_idx"), py::arg("alpha"), py::arg("U"),
          py::arg("n_mics"), py::arg("seed"),
          py::arg("X_fft"),
          "Fill frequency-domain wind noise coefficients via Corcos model.");
}
