# ============================================================================
# Convenience wrapper around the two CMake projects in this repo:
#
#   .      -> firmware, arm-none-eabi, build/<BUILD>/
#   test/  -> host unit tests, system gcc, build/test/
#
# Usage:
#   make APP=usart_echo           build one app
#   make flash APP=usart_echo     build + flash it
#   make debug APP=usart_echo     build + flash + GDB session
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

GDB        ?= arm-none-eabi-gdb
OPENOCD    ?= openocd
OOCD_IFACE ?= interface/stlink.cfg
OOCD_TGT   ?= target/stm32h7x.cfg
GDB_PORT   ?= 3333
GDB_EXTRA  ?=
ENTRY      ?= app_main
GDBINIT     = debug/gdbinit
ELF         = $(BDIR)/$(APP).elf

SHELL := /bin/bash

.DEFAULT_GOAL := build
.PHONY: build all flash monitor test test-build configure configure-test \
        compiledb format list clean distclean debug gdbserver attach help

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

# ---------------------------------------------------------------------------
# Debugging
# ---------------------------------------------------------------------------

# Succeeds when something (an OpenOCD, hopefully) is listening on the GDB port.
port_open = (exec 3<>/dev/tcp/127.0.0.1/$(GDB_PORT)) &>/dev/null

# Release is compiled -Os -g0: no debug info, and inlining scrambles what's
# left.  Cheap to warn, expensive to discover halfway through a session.
check_build = if [[ "$(BUILD)" == Release ]]; then \
	echo "!! BUILD=Release is built -g0 -- no symbols.  Use BUILD=Debug."; fi

# OpenOCD in the foreground, so its log lands where you can read it.
gdbserver:
	$(OPENOCD) -f $(OOCD_IFACE) -f $(OOCD_TGT)

# Build, flash and run to $(ENTRY).  Reuses a `make gdbserver` if one is up,
# otherwise starts its own and takes it down again on exit.
debug: build
	@$(check_build)
	@if $(port_open); then \
		echo "==> Reusing the OpenOCD on :$(GDB_PORT)"; \
	else \
		echo "==> Starting OpenOCD (log: $(BDIR)/openocd.log)"; \
		$(OPENOCD) -f $(OOCD_IFACE) -f $(OOCD_TGT) >$(BDIR)/openocd.log 2>&1 & \
		trap "kill $$! 2>/dev/null" EXIT; \
		for _ in {1..50}; do $(port_open) && break; sleep 0.1; done; \
		if ! $(port_open); then \
			echo "==> OpenOCD never opened :$(GDB_PORT).  Its log said:"; \
			cat $(BDIR)/openocd.log; \
			exit 1; \
		fi; \
	fi; \
	$(GDB) -q $(GDB_EXTRA) -x $(GDBINIT) \
		-ex "target extended-remote :$(GDB_PORT)" \
		-ex "monitor reset halt" \
		-ex "load" \
		-ex "monitor reset halt" \
		-ex "tbreak $(ENTRY)" \
		-ex "continue" \
		$(ELF)

# Attach to a running `make gdbserver` WITHOUT resetting or re-flashing --
# this is the one to use on a board that has hung or faulted.
attach:
	@$(check_build)
	@if ! $(port_open); then \
		echo "Nothing listening on :$(GDB_PORT) -- start 'make gdbserver' first."; \
		exit 1; \
	fi
	@if [[ ! -f $(ELF) ]]; then \
		echo "$(ELF) does not exist -- 'make build APP=$(APP)' first."; \
		exit 1; \
	fi
	$(GDB) -q $(GDB_EXTRA) -x $(GDBINIT) \
		-ex "target extended-remote :$(GDB_PORT)" \
		-ex "monitor halt" \
		$(ELF)

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

format:
	find src -regex '.*\.\(c\|h\)' -exec clang-format -i {} \;

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
	@echo "  debug       Build + flash + GDB, stops at app_main"
	@echo "  gdbserver   OpenOCD in the foreground (own terminal)"
	@echo "  attach      GDB onto a running gdbserver -- no reset, no flash"
	@echo "  monitor     picocom on $(PORT) @ $(BAUD)"
	@echo "  test        Build + run host unit tests (TEST=<regex> to filter)"
	@echo "  compiledb   Symlink compile_commands.json for clangd"
	@echo "  list        Show available apps and tests"
	@echo "  clean       Remove build/$(BUILD) and build/test"
	@echo "  distclean   Remove all of build/ (needed after toolchain changes)"
	@echo ""
	@echo "Variables: APP BUILD PORT BAUD TEST JOBS GDB_PORT"
