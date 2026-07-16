#include <Audio.h>
#include <LevelMeter.hpp>
#include <SerialPrompt.hpp>

// ---------- Config ----------
// Stock AudioInputTDM = one 256-bit frame = 8 x 32-bit slots => 8 mics max.
constexpr int MAX_MICS = 8;
// ----------------------------

// The sketch owns and wires its own audio graph; lib/ only provides
// app-agnostic building blocks.
AudioInputTDM tdm;
AudioFilterBiquad hp[MAX_MICS];
AudioAnalyzePeak peak[MAX_MICS];
AudioAnalyzeRMS rms[MAX_MICS];
AudioConnection* patch[MAX_MICS * 3];

float hold[MAX_MICS] = { 0 };
int numMics          = 0;

void setup()
{
    Serial.begin(115200);
    while (!Serial)
    { /* wait for the monitor before doing ANYTHING */
    }

    numMics = SerialPrompt::ask_mic_count(Serial, MAX_MICS);
    AudioMemory(30 + MAX_MICS * 8); // compile-time constant; sized for worst case

    for (int i { 0 }; i < numMics; i++)
    {
        hp[i].setHighpass(0, 40, 0.707f);
        patch[i * 3 + 0] = new AudioConnection(tdm, i * 2, hp[i], 0);
        patch[i * 3 + 1] = new AudioConnection(hp[i], 0, peak[i], 0);
        patch[i * 3 + 2] = new AudioConnection(hp[i], 0, rms[i], 0);
    }

    delay(300); // let the ICS-52000s finish startup/unmute
    Serial.print("Running ");
    Serial.print(numMics);
    Serial.println(" mic(s). 0 dB = full scale. Tap each mic in turn.");
}

void loop()
{
    static uint32_t last { 0 };
    if (millis() - last < 100)
        return;

    for (int i { 0 }; i < numMics; i++)
        if (!peak[i].available() || !rms[i].available())
            return;
    last = millis();

    for (int i { 0 }; i < numMics; i++)
    {
        LevelMeter::print_meter(Serial, i, rms[i].read(), peak[i].read(), hold[i]);
        if (i < numMics - 1)
            Serial.print("  |  ");
    }
    Serial.println();
}
