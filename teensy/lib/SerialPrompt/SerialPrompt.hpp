#pragma once

#include <Arduino.h>

namespace SerialPrompt
{
    // Blocks forever until you choose. Accepts '1'..'0'+max_mics,
    // so max_mics must stay a single digit (<= 9).
    int ask_mic_count(Stream& io, int max_mics);
}
