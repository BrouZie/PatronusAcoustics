# Main app:      make build / upload / monitor
# Test sketch:   make upload TEST=ics43434
TEST ?=
ENV = $(if $(TEST),test-$(TEST),main)
BAUD ?= 115200

.PHONY: build upload monitor compiledb list

build:
	uv run pio run -e $(ENV)

upload:
	uv run pio run -e $(ENV) -t upload

monitor:
	uv run pio device monitor -b $(BAUD)

compiledb:
	uv run pio run -e $(ENV) -t compiledb

list:
	@echo "main"; ls src/tests | sed 's/^/test: /;s/\.cpp$$//'
