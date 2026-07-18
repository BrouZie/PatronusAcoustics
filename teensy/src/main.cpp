#include <Audio.h>

AudioInputTDM tdm;
AudioRecordQueue queue;
AudioAnalyzeFFT256 fft;

AudioConnection p1(tdm, 0, queue, 0);
AudioConnection p2(tdm, 0, fft, 0);

void setup()
{
    Serial.begin(115200);
    while (!Serial)
    { /* wait for the monitor before doing ANYTHING */
    }

	AudioMemory(60);
	delay(100); // let the ICS-52000s finish startup/unmute
	queue.begin();
}

void loop()
{
	if (queue.available() >= 1)
	{
		int16_t* p { queue.readBuffer() };
		static int16_t buf[128];
		memcpy(buf, p, 128 * sizeof(int16_t));
		queue.freeBuffer();

		static uint32_t last { 0 };
		if (millis() - last > 100)
		{
			last = millis();
			for (int i {}; i < 128; ++i)
			{
				Serial.println(buf[i]);
			}
		}
	}

	if (fft.available())
	{
		for (int i {}; i < 20; ++i)
		{
			Serial.printf("%.3f", fft.read(i));
		}
		Serial.println();
	}
}
