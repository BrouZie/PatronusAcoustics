# Build C++ pybind11 extensions for acoustic simulation
#
# Dependencies (system packages):
#   Debian/Ubuntu: sudo apt install libfftw3-dev
#   Arch:          sudo pacman -S fftw
#   Fedora:        sudo dnf install fftw-devel
#   macOS:         brew install fftw
#
# Python: pybind11 (installed via pip/uv, listed in pyproject.toml)

VENV_PYTHON = uv run python
CXX          = g++
CXXFLAGS     = -O3 -Wall -shared -std=c++17 -fPIC -march=native

# pybind11 includes + numpy includes from venv
PY_INCLUDES = $(shell $(VENV_PYTHON) -m pybind11 --includes)

# Detect extension suffix for the venv Python
PY_SUFFIX   = $(shell $(VENV_PYTHON) -c \
  "import importlib.machinery; \
   print([s for s in importlib.machinery.EXTENSION_SUFFIXES if s.startswith('.cpython')][0])")

all: build

build: src/_propagate$(PY_SUFFIX) src/_noise$(PY_SUFFIX) src/_srp$(PY_SUFFIX)

# Compile the propagation extension (uses FFTW)
src/_propagate$(PY_SUFFIX): src/cpp/propagate.cpp
	$(CXX) $(CXXFLAGS) $(PY_INCLUDES) $< -lfftw3 -o $@

# Compile the noise generation extension
src/_noise$(PY_SUFFIX): src/cpp/noise.cpp
	$(CXX) $(CXXFLAGS) $(PY_INCLUDES) $< -o $@

# Compile the SRP beamforming extension
src/_srp$(PY_SUFFIX): src/cpp/srp.cpp
	$(CXX) $(CXXFLAGS) $(PY_INCLUDES) $< -o $@

clean:
	rm -f src/_propagate*.so src/_noise*.so src/_srp*.so

# The fabrication trade: dual ring at 3 spacings vs a 16-mic planar ring at
# equal mic budget. Tens of minutes cold; cached runs make re-runs cheap.
compare-baseline:
	uv run python -m src.compare \
	  config/compare/dual_ring_s05.yaml \
	  config/compare/dual_ring_s20.yaml \
	  config/compare/dual_ring_s30.yaml \
	  config/compare/single_ring_16.yaml \
	  --distances 10 20 30 50 70

compare-baseline-quick:
	uv run python -m src.compare \
	  config/compare/dual_ring_s05.yaml \
	  config/compare/dual_ring_s20.yaml \
	  config/compare/dual_ring_s30.yaml \
	  config/compare/single_ring_16.yaml \
	  --distances 10 30 50 --seeds 1 --quick

test:
	uv run python -m pytest tests/ -q

.PHONY: all build clean compare-baseline compare-baseline-quick test
