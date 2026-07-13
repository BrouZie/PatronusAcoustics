#include <Arduino.h>

// Placeholder for the main Patronus Acoustics application.
// Hardware test sketches live in src/tests/ (build with `make build TEST=<name>`).

void setup()
{
    Serial.begin(115200);
    pinMode(LED_BUILTIN, OUTPUT);
    Serial.println("PatronusAcoustics main app - nothing here yet");
}

void loop()
{
    digitalWrite(LED_BUILTIN, HIGH);
    delay(500);
    digitalWrite(LED_BUILTIN, LOW);
    delay(500);
}
