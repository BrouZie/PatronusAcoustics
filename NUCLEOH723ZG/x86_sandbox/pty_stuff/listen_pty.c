#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include <termios.h>
#include <poll.h>
#include <pty.h>

/* TODO(sok): Before full merge:
    0. Replace pty.h and termios with sys/ioctl.h and asm/termbits.h - i.e. use ioctl() to do all the shit + termios2 struct
        - You'll need to use swap out tcflush, cfmakeraw, termios, openpty and all of that with posix_openpty(), ioctl() basically
    1. Move packet def to global header
    2. Decide interface for working with serial ports. Things to consider:
        - Ownership
        - Error-handling & printouts
        - Struct defs
    3. Move full implementation to utils.h
    4. Ideally, rework logmel_viewer, spectrum_viewer ++ (to use same global packet header)
*/

// Replaced by types.h probably
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef float float32_t;
typedef bool bool32;

#define MAGIC 0x314C4D4C
#define NUM_MEL_BANDS 128

typedef struct
{
    uint32_t  magic;
    uint32_t  seq;
    float32_t azimuth;
    float32_t elevation;

} PacketHeader;

typedef struct
{
    PacketHeader header;
    uint8_t      cells[NUM_MEL_BANDS];
} QuantizedPacket;

typedef struct
{
    int     fd;
    char    name[64];
    uint8_t buf[sizeof(QuantizedPacket) * 4];
    size_t  len;
    struct termios tio;
} SerialPortRx;

typedef struct
{
    int     master;
    int     slave;
    char    name[64];
    struct termios tio;
} SerialPortTx;

static SerialPortRx Rx;
static SerialPortTx Tx;

void open_serial_port_rx(const char* port)
{
    Rx.fd = open(port, O_RDONLY | O_NOCTTY | O_NONBLOCK);

    if (Rx.fd < 0)
    {
        perror("fd");
        exit(EXIT_FAILURE);
    }

    tcgetattr(Rx.fd, &Rx.tio);
    cfmakeraw(&Rx.tio);
    // cfsetispeed(&Rx.tio, B1152000);
    // cfsetospeed(&Rx.tio, B1152000);
    // Rx.tio.c_cflag |= CLOCAL | CREAD;
    tcsetattr(Rx.fd, TCSANOW, &Rx.tio);

    tcflush(Rx.fd, TCIFLUSH); // drop any buffered input

    snprintf(Rx.name, sizeof(Rx.name), "%s", port);
    printf("opened port: %s\n", port);
}

bool32 read_serial_port(QuantizedPacket* packet)
{
    bool32 packet_found = false;

    while (true)
    {
        ssize_t bytes_read = read(Rx.fd, Rx.buf + Rx.len, sizeof(Rx.buf) - Rx.len);

        if (bytes_read > 0)
        {
            Rx.len += bytes_read;

            uint32_t offset = 0;

            while (Rx.len - offset >= sizeof(uint32_t))
            {
                uint32_t magic_candidate = ((uint32_t)Rx.buf[offset + 3] << 24) |
                                           ((uint32_t)Rx.buf[offset + 2] << 16) |
                                           ((uint32_t)Rx.buf[offset + 1] <<  8) |
                                            (uint32_t)Rx.buf[offset + 0];
                if (magic_candidate == MAGIC)
                {
                    if (Rx.len - offset < sizeof(QuantizedPacket))
                    {
                        break; // wait for more
                    }
                    // consume and update offset
                    memcpy(packet, &Rx.buf[offset], sizeof(QuantizedPacket));
                    offset += sizeof(QuantizedPacket);
                    packet_found = true;
                }
                else
                {
                    // update offset by one byte position
                    ++offset;
                }
            }
            memmove(Rx.buf, Rx.buf + offset, Rx.len - offset);
            Rx.len -= offset;
            continue;
        }
        if (bytes_read == 0)
        {
            // The port got closed
            return false;
        }

        /// We've cought up to the datastream: read_bytes == -1 ///

        if (errno == EINTR) continue;

        // Kernel buffer is empty and packet found
        if (packet_found)
        {
            // Newest packet is ready and we return to caller+
            return true;
        }

        // no packet, and no data available yet -> poll for more data
        struct pollfd pfd = { .fd = Rx.fd, .events = POLLIN };
        if (poll(&pfd, 1, -1) == -1 && errno != EINTR)
        {
            perror("poll");
            return -1;
        }
    }
}

void open_serial_port_tx(const char* port)
{
    if (openpty(&Tx.master, &Tx.slave, Tx.name, NULL, NULL) < 0)
    {
        perror("openpty failed");
    }

    tcgetattr(Tx.slave, &Tx.tio);
    cfmakeraw(&Tx.tio);
    tcsetattr(Tx.slave, TCSANOW, &Tx.tio);

    // Non-blocking: if nobody is reading, drop data like a real UART would
    fcntl(Tx.master, F_SETFL, fcntl(Tx.master, F_GETFL) | O_NONBLOCK);

    // Symlinking to more meaningful dev name
    unlink(port);
    if (symlink(Tx.name, port) < 0)
    {
        perror("symlink");
    }

    printf("Simulated UART over %s (%s)\n", port, Tx.name);
}

void write_serial_port(const QuantizedPacket* packet)
{
    // Not handling perror - so as to not flood stdout
    // whenever nothing is connected
    int n = write(Tx.master, packet, sizeof(*packet));
    if (n < 0 && errno == EAGAIN)
    {
        tcflush(Tx.slave, TCIFLUSH);   // nobody's reading: discard backlog
        n = write(Tx.master, packet, sizeof(*packet));
    }
}

typedef enum
{
    RX, TX,
} PortType;

typedef struct
{
    char     name[64];
    PortType type;
} SerialPort;

/*
 * int main()
 * {
 *
 *     caller holds onto the file handle? -> yes: [ ] no: [x]
 *     caller provides port name only?    -> yes: [ ] no: [x] -> we wanna provide baud rate
 *     separate initialization for rx/tx? -> yes: [x] no: [ ]
 *
 *     caller owns whatever is not platform specific -> yes: [x] no: [ ]
 *
 *     SerialPort port = {0};
 *     open_serial_port_rx(&port, "/dev/ttyACM0", 4194304)
 *
 *     return 0;
 * }
 */

int main(void)
{
    QuantizedPacket packet;

    open_serial_port_rx("/dev/ttyACM0");
    open_serial_port_tx("/tmp/ttySIM0");

    while (true)
    {
        if (!read_serial_port(&packet)) break;
        write_serial_port(&packet);
    }

    printf("goodbye, thanks for playing\n");

    return 0;
}
