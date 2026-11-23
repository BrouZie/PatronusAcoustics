#include "serialport.h"
#include "packet.h"
#include "dsp.h"

#include <stdio.h>

#define STM32_PATH   "/dev/ttyACM0"
#define SYMLINK_PATH "/tmp/ttySIM0"

#define BAUD_RATE    4194304

/* TODO(sok): Further thoughts on what should be done:
    - [x] Revive `spectrum_viewer.py`
    - [x] Finalize `serialport` API - comments and decide what to do about `PacketReader`
    - [ ] Have `pcm` be transported always for x86 build (not just debug) - ties into the next point
    - [ ] Make Full_Packet shared across more shit and research different options/approaches:
        - cffi, parse headers at python-runtime which gives us packet def
        - just go for the easy approach, send magic and specific data
        - better yet, find some other IPC method as the x86 app is the central program
            - main process (x86) gets one massive packet and distributes the data
            - tools are given what they want - just the domain specific data (from x86 process)
    - [ ] Think about restructuring of project layout (and build system/setup?)
        - use platform vs. non-platform layout? What will our python look like then?
        - arm, python and x86 apps should behave nicely together
    - [ ] Figure out how to handle globals/config for python applications (structs etc.)
    - [ ] Find way to orchastrate all python scripts/tools from main C application
        - [x] spectrum_viewer
        - [ ] logmel_viewer
        - [ ] drone_detection_cnn
*/

int main()
{
    FFT_Spectrum   spec = {};
    PrevAudioFrame prev = {};

    dsp_init_spectrum();

    SerialPort port = serial_open(STM32_PATH, BAUD_RATE);
    PtySymlink pty  = pty_link_open(SYMLINK_PATH);

    Full_Packet packet = {};

    for (;;)
    {
        if (port.state == OPEN)
        {
            if (!read_latest_packet(&port, &packet)) continue;
            // printf("magic: %x, seq: %d\n", packet.magic, packet.seq);
        }
        else
        {
            // try to open again!
            port = serial_open(STM32_PATH, BAUD_RATE);
        }

        dsp_compute_spectrum(&packet.frame, &prev, &spec);
        pty_link_write(&pty, &spec.bins[0], sizeof(spec.bins[0]));
    }

    serial_close(&port);
    pty_link_close(&pty);

    return 0;
}
