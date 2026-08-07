# ============================================================================
# Convenience wrapper around the two CMake projects in this repo:
#
#   .      -> firmware, arm-none-eabi, build/<BUILD>/
#   test/  -> host unit tests, system gcc, build/test/
#
# Usage:
#   make APP=usart_echo           build one app
#   make flash APP=usart_echo     build + flash it
#   make test                    build and run host tests
#   make test TEST=ringbuf       run only matching tests
#   make monitor                 open the serial console
#   make list                    show available apps and tests
#   make help                    this list, in more detail
# ============================================================================

APP     ?= usart_echo
BUILD   ?= Debug
PORT    ?= /dev/ttyACM0
BAUD    ?= 115200
TEST    ?=
JOBS    ?=

BDIR     = build/$(BUILD)
TDIR     = build/test
TOOLCHAIN = cmake/gcc-arm-none-eabi.cmake

JOBFLAG  = $(if $(JOBS),-j $(JOBS),)

.DEFAULT_GOAL := build
.PHONY: build all flash monitor test test-build configure configure-test \
        compiledb list clean distclean debug help

# ---------------------------------------------------------------------------
# Firmware
# ---------------------------------------------------------------------------

# Configure only when the build tree doesn't exist yet.  Ninja re-runs cmake
# by itself when CMakeLists.txt changes, so there's no need to reconfigure
# on every invocation.
$(BDIR)/build.ninja:
	cmake -S . -B $(BDIR) -G Ninja \
		--toolchain $(TOOLCHAIN) \
		-DCMAKE_BUILD_TYPE=$(BUILD)

configure: $(BDIR)/build.ninja

build: $(BDIR)/build.ninja
	cmake --build $(BDIR) --target $(APP) $(JOBFLAG)

all: $(BDIR)/build.ninja
	cmake --build $(BDIR) $(JOBFLAG)

flash: $(BDIR)/build.ninja
	cmake --build $(BDIR) --target flash-$(APP) $(JOBFLAG)

debug: build
	@echo "Starting OpenOCD + GDB for $(APP)..."
	@openocd -f interface/stlink.cfg -f target/stm32h7x.cfg >/dev/null 2>&1 & \
	OOCD_PID=$$!; \
	trap "kill $$OOCD_PID 2>/dev/null" EXIT; \
	sleep 1; \
	arm-none-eabi-gdb \
		-ex "target extended-remote :3333" \
		-ex "monitor reset halt" \
		$(BDIR)/$(APP).elf

monitor:
	picocom -b $(BAUD) $(PORT)

# ---------------------------------------------------------------------------
# Host tests
# ---------------------------------------------------------------------------

$(TDIR)/build.ninja:
	cmake -S test -B $(TDIR) -G Ninja -DCMAKE_BUILD_TYPE=Debug

configure-test: $(TDIR)/build.ninja

test-build: $(TDIR)/build.ninja
	cmake --build $(TDIR) $(JOBFLAG)

test: test-build
	ctest --test-dir $(TDIR) --output-on-failure \
		$(if $(TEST),-R $(TEST),)

# ---------------------------------------------------------------------------
# Tooling
# ---------------------------------------------------------------------------

# clangd looks for compile_commands.json in the project root.  Point it at the
# firmware build -- that's where you want cross-compile flags and HAL headers.
compiledb: $(BDIR)/build.ninja
	ln -sf $(BDIR)/compile_commands.json compile_commands.json
	@echo "compile_commands.json -> $(BDIR)/"

list:
	@echo "Apps (src/apps/*):"
	@ls -1 src/apps 2>/dev/null | sed 's/^/  /' || echo "  (none)"
	@echo "Tests (test/test_*.c):"
	@ls -1 test/test_*.c 2>/dev/null \
		| xargs -n1 basename 2>/dev/null \
		| sed 's/\.c$$//;s/^/  /' || echo "  (none)"

clean:
	@rm -rf $(BDIR) $(TDIR)
	@echo "Removed $(BDIR) and $(TDIR)"

# Use this after changing anything about the toolchain -- CMake caches the
# detected compiler on first configure and never reconsiders it.
distclean:
	@rm -rf build compile_commands.json
	@echo "Removed build/ and compile_commands.json"

help:
	@echo "Targets:"
	@echo "  build       Build one app            (APP=$(APP))"
	@echo "  all         Build every app"
	@echo "  flash       Build + flash via OpenOCD"
	@echo "  debug       OpenOCD + arm-none-eabi-gdb"
	@echo "  monitor     picocom on $(PORT) @ $(BAUD)"
	@echo "  test        Build + run host unit tests (TEST=<regex> to filter)"
	@echo "  compiledb   Symlink compile_commands.json for clangd"
	@echo "  list        Show available apps and tests"
	@echo "  clean       Remove build/$(BUILD) and build/test"
	@echo "  distclean   Remove all of build/ (needed after toolchain changes)"
	@echo ""
	@echo "Variables: APP BUILD PORT BAUD TEST JOBS"
