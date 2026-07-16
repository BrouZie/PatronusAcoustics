#pragma once

#include <Arduino.h>

namespace LevelMeter
{
float raw_to_dB(float raw_value);

// One meter, NO newline (inline layout). Bar spans -60..0 dBFS.
// Updates peak_hold (0.90 decay per call).
void print_meter(Stream& out, int mic_number, float rms, float peak, float& peak_hold,
                 int bar_width = 30);
} // namespace LevelMeter
