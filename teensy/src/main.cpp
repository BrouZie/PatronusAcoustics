#include <Arduino.h>

void setup()
{
    pinMode(LED_BUILTIN, OUTPUT);
    Serial.begin(115200);
}

void loop()
{
    digitalWrite(LED_BUILTIN, HIGH);
    delay(1200);
    digitalWrite(LED_BUILTIN, LOW);
    delay(200);
    // Serial.println(millis());
	Serial.println("Hello bitch boy!");
}
