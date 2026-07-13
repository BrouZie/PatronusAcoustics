/// SINGLE ICS-52000 TEST
/// leave WSO out
#include <Audio.h>
#include <cstdint>

AudioInputTDM tdm;  // TDM input (pins 8, 20, 21)
AudioAmplifier amp;
AudioAnalyzePeak peak;
AudioAnalyzeRMS rms;

// One ICS-52000 in slot 0 -> useful 16 bits on EVEN channel 0
AudioConnection p1(tdm, 0, amp, 0);
AudioConnection p2(amp, 0, peak, 0);
AudioConnection p3(amp, 0, rms, 0);

void setup()
{
    Serial.begin(115200);
    AudioMemory(64); // MORE MEMORY WHEN TDM! BUMP EVEN HIGHER FOR ARRAYS!
    amp.gain(10.0); // start here; raise to 20–40 if levels look tiny
    Serial.println("ICS-52000 TDM test - make some noise...");
}

void loop()
{
    if (peak.available() && rms.available())
    {
        float p { peak.read() };
        float r { rms.read() };

        Serial.print("RMS ");
        Serial.print(r, 3);
        Serial.print("  PEAK ");
        Serial.print(p, 3);
        Serial.print("  ");
        int bars = static_cast<int>(p * 100);
        for (int i { 0 }; i < bars; ++i)
            Serial.print("#");
        Serial.println();
    }
    delay(40);
}
