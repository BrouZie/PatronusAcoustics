#include "SerialPrompt.hpp"

int SerialPrompt::ask_mic_count(Stream& io, int max_mics)
{
    io.print("How many ICS-52000 mics? Press 1-");
    io.print(max_mics);
    io.print(": ");
    for (;;)
    {
        while (!io.available())
        { /* wait for a keypress */
        }
        char c = io.read();
        if (c >= '1' && c <= char('0' + max_mics))
        {
            int n { c - '0' };
            io.print("-> ");
            io.print(n);
            io.println(" mic(s)");
            return n;
        }
        // ignore stray newlines / bad keys and keep waiting
    }
}
