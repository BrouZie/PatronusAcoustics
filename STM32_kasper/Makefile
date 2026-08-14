# stm32/Makefile - mirrors teensy/'s workflow:
#   make build                 # SRP-PHAT main app (patronus-main)
#   make build TEST=ics52000   # bring-up test
#   make upload TEST=bench-dsp # flash via ST-LINK (requires flashing software!)
#   make monitor               # serial monitor on the ST-LINK VCP
#   make boost                 # one-time: set CPUFREQ_BOOST option byte (550 MHz)

TEST ?=
TARGET = $(if $(TEST), test-$(TEST),STM32_kasper)
BUILD ?= Debug
PORT ?= /dev/ttyACM0
BAUD ?= 115200
BDIR = build/$(BUILD)

.PHONY: build upload monitor compiledb list boost clean

build:
	cmake -S . -B $(BDIR) -G Ninja \
		--toolchain cmake/gcc-arm-none-eabi.cmake \
		-DCMAKE_BUILD_TYPE=$(BUILD)
	cmake --build $(BDIR) --target $(TARGET)

upload: build
	@command -v openocd >/dev/null 2>&1 && \
		sudo openocd -f interface/stlink.cfg -f target/stm32h7x.cfg \
		-c "program $(BDIR)/$(TARGET).elf verify reset exit"

monitor:
	@command -v tio >/dev/null 2>&1 && tio -b $(BAUD) $(PORT) || picocom -b $(BAUD) $(PORT) || \
		echo "picocom/tio or the stm32 isn't connected properly!"

compiledb: build
	ln -sf $(BDIR)/compile_commands.json compile_commands.json

list:
	@echo "main: patronus-main (default)"
	@ls src/app | sed 's/^/test: /;s/\.c$$//;s/_/-/g'

openocd-server:
	@command -v openocd >/dev/null 2>&1 && \
		sudo openocd -f interface/stlink.cfg -f target/stm32h7x.cfg || \
		echo "openocd not found or the stm32 isn't connected properly!"
debug:
	gdb-multiarch $(BDIR)/$(TARGET).elf \
		-ex "target extended-remote localhost:3333" \
		-ex "monitor reset halt"
clean:
	rm -rf build
