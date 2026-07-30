#pragma once

#include <Arduino.h>

namespace SerialPrompt
{
// Blocks forever until you choose. Accepts '1'..'0'+max_mics,
// so max_mics must stay a single digit (<= 9).
int ask_mic_count(Stream& io, int max_mics);

// Numbered single-key menu; blocks until a valid choice. Returns the
// 0-based index. n_options must stay a single digit (<= 9).
int ask_choice(Stream& io, const char* title, const char* const* options, int n_options);
} // namespace SerialPrompt
