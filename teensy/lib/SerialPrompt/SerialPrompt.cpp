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

int SerialPrompt::ask_choice(Stream& io, const char* title, const char* const* options,
                             int n_options)
{
    io.println(title);
    for (int i { 0 }; i < n_options; i++)
    {
        io.print("  ");
        io.print(i + 1);
        io.print(") ");
        io.println(options[i]);
    }
    io.print("Press 1-");
    io.print(n_options);
    io.print(": ");
    for (;;)
    {
        while (!io.available())
        { /* wait for a keypress */
        }
        char c = io.read();
        if (c >= '1' && c <= char('0' + n_options))
        {
            int i { c - '1' };
            io.print("-> ");
            io.println(options[i]);
            return i;
        }
    }
}
