CLI       := ./bin/arduino-cli
SKETCHES  := $(wildcard src/*/)
CORES     := arduino:avr arduino:samd
BAUD      := 115200
PORT      := /dev/ttyACM0

.PHONY: install-cli install-cores install-libs list-ports \
        compile compile-uno compile-mkr \
        upload upload-uno upload-mkr \
        monitor clean help

help:  ## show this help
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*##"}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install-cli:  ## download arduino-cli binary (latest release)
	@mkdir -p bin
	@curl -fsSL -o /tmp/arduino-cli.tar.gz https://downloads.arduino.cc/arduino-cli/arduino-cli_latest_Linux_64bit.tar.gz
	@tar -xzf /tmp/arduino-cli.tar.gz -C bin/
	@chmod +x bin/arduino-cli
	@rm /tmp/arduino-cli.tar.gz
	@echo "arduino-cli installed to ./bin/arduino-cli"

install-cores:  ## install cores for Uno and MKR WiFi 1010
	$(CLI) core update-index
	$(CLI) core install $(CORES)

install-libs:  ## install common libraries
	$(CLI) lib install WiFiNINA

list-ports:  ## list available serial ports
	$(CLI) board list

compile: compile-uno  ## compile for Uno (default)

compile-uno:  ## compile sketch(es) for Arduino Uno
	@for sketch in $(SKETCHES); do \
		echo "=== Compiling $$(basename $$sketch) for Uno ==="; \
		$(CLI) compile --fqbn arduino:avr:uno --build-path ./build "$$sketch"; \
	done

compile-mkr:  ## compile sketch(es) for Arduino MKR WiFi 1010
	@for sketch in $(SKETCHES); do \
		echo "=== Compiling $$(basename $$sketch) for MKR WiFi 1010 ==="; \
		$(CLI) compile --fqbn arduino:samd:mkrwifi1010 --build-path ./build "$$sketch"; \
	done

upload-uno:  ## upload sketch(es) to Arduino Uno
	@for sketch in $(SKETCHES); do \
		echo "=== Uploading $$(basename $$sketch) to Uno ==="; \
		$(CLI) upload --fqbn arduino:avr:uno --port $(PORT) "$$sketch"; \
	done

upload-mkr:  ## upload sketch(es) to Arduino MKR WiFi 1010
	@for sketch in $(SKETCHES); do \
		echo "=== Uploading $$(basename $$sketch) to MKR WiFi 1010 ==="; \
		$(CLI) upload --fqbn arduino:samd:mkrwifi1010 --port $(PORT) "$$sketch"; \
	done

monitor:  ## open serial monitor (override: make monitor PORT=/dev/ttyUSB0 BAUD=9600)
	$(CLI) monitor --config serial-timeout=1 --raw $(PORT) $(BAUD)

clean:  ## remove build artifacts
	rm -rf build/
