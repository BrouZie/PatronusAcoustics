#include "LevelMeter.hpp"

float LevelMeter::raw_to_dB(float raw_value)
{
    return (raw_value <= 1e-7f) ? -90.0f : 20.0f * log10f(raw_value);
}

void LevelMeter::print_meter(Stream& out, int mic_number, float rms, float peak, float& peak_hold,
                             int bar_width)
{
    if (peak > peak_hold)
        peak_hold = peak;
    else
        peak_hold *= 0.90f;

    float rdb = raw_to_dB(rms);
    int bars  = constrain(static_cast<int>((rdb + 60.0f) / 60.0f * bar_width), 0, bar_width);

    out.print("M");
    out.print(mic_number + 1);
    out.print(' ');
    out.print(rdb, 1);
    out.print(" dB [");
    for (int b = 0; b < bar_width; b++)
        out.print(b < bars ? '#' : ' ');
    out.print("] pkhold ");
    out.print(raw_to_dB(peak_hold), 1);
    out.print(peak >= 0.999f ? " CLIP!" : "      ");
}
