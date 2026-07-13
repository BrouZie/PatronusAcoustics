#include <Audio.h>

// ---------- Config ----------
// Stock AudioInputTDM = one 256-bit frame = 8 x 32-bit slots => 8 mics max.
// (1-8 is a single digit, which the launch prompt relies on.)
constexpr int MAX_MICS = 8;
constexpr int BAR_W    = 30; // meter width, spans -60..0 dBFS
// ----------------------------

AudioInputTDM tdm;
AudioFilterBiquad hp[MAX_MICS];
AudioAnalyzePeak peak[MAX_MICS];
AudioAnalyzeRMS rms[MAX_MICS];
AudioConnection* patch[MAX_MICS * 3];

float hold[MAX_MICS] = { 0 };
int numMics          = 0;

float toDb(float v)
{
    return (v <= 1e-7f) ? -90.0f : 20.0f * log10f(v);
}

// Blocks forever until you choose.
int askMicCount()
{
    Serial.print("How many ICS-52000 mics? Press 1-");
    Serial.print(MAX_MICS);
    Serial.print(": ");
    for (;;)
    {
        while (!Serial.available())
        { /* wait for a keypress */
        }
        char c = Serial.read();
        if (c >= '1' && c <= char('0' + MAX_MICS))
        {
            int n { c - '0' };
            Serial.print("-> ");
            Serial.print(n);
            Serial.println(" mic(s)");
            return n;
        }
        // ignore stray newlines / bad keys and keep waiting
    }
}

void printMeter(int i)
{ // one meter, NO newline (inline layout)
    float pk = peak[i].read();
    float r  = rms[i].read();
    if (pk > hold[i])
        hold[i] = pk;
    else
        hold[i] *= 0.90f;

    float rdb = toDb(r);
    int bars  = constrain(static_cast<int>((rdb + 60.0f) / 60.0f * BAR_W), 0, BAR_W);

    char label[6];
    snprintf(label, sizeof(label), "M%d", i + 1);
    Serial.print(label);
    Serial.print(' ');
    Serial.print(rdb, 1);
    Serial.print(" dB [");
    for (int b = 0; b < BAR_W; b++)
        Serial.print(b < bars ? '#' : ' ');
    Serial.print("] pkhold ");
    Serial.print(toDb(hold[i]), 1);
    Serial.print(pk >= 0.999f ? " CLIP!" : "      ");
}

void setup()
{
    Serial.begin(115200);
    while (!Serial)
    { /* wait for the monitor before doing ANYTHING */
    }

    numMics = askMicCount();
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
        printMeter(i);
        if (i < numMics - 1)
            Serial.print("  |  ");
    }
    Serial.println();
}
