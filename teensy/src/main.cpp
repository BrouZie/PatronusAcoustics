#include <Audio.h>

AudioInputI2S i2sIn; // ICS-43434 (pins 8, 20, 21)
AudioAmplifier amp;  // MEMS signal is quiet after 16-bit truncation
AudioAnalyzePeak peak;
AudioAnalyzeRMS rms;

// L/R tied to GND => mic is on the LEFT channel => AudioInputI2S output 0
AudioConnection p1(i2sIn, 0, amp, 0);
AudioConnection p2(amp, 0, peak, 0);
AudioConnection p3(amp, 0, rms, 0);

void setup()
{
    Serial.begin(115200);
    AudioMemory(20);
    amp.gain(10.0); // start here; raise to 20–40 if levels look tiny
    Serial.println("ICS-43434 test - make some noise...");
}

void loop()
{
    if (peak.available() && rms.available())
    {
        float p = peak.read();
        float r = rms.read();
        Serial.print("RMS ");
        Serial.print(r, 3);
        Serial.print("  PEAK ");
        Serial.print(p, 3);
        Serial.print("  ");
        int bars = (int)(p * 60);
        for (int i = 0; i < bars; i++)
            Serial.print("#");
        Serial.println();
    }
    delay(40);
}
