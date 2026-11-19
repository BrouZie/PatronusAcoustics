#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include <poll.h>
#include <asm/termbits.h>
#include <sys/ioctl.h>

/* TODO(sok): Before full merge:
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
} PacketReader;

typedef struct
{
    int   master_fd;
    int   slave_fd;
    char* slave_name;
} PtyPair;

static PacketReader Reader;
static PtyPair Pty;

int set_baud(int fd, int baud)
{
    struct termios2 t;
    ioctl(fd, TCGETS2, &t);

    // Stolen from https://github.com/lattera/glibc/blob/master/termios/cfmakeraw.c!
    t.c_iflag &= ~(IGNBRK | BRKINT | PARMRK | ISTRIP | INLCR | IGNCR | ICRNL | IXON);
    t.c_oflag &= ~OPOST;
    t.c_lflag &= ~(ECHO | ECHONL | ICANON | ISIG | IEXTEN);
    t.c_cflag &= ~(CSIZE | PARENB);
    t.c_cflag |= CS8;
    t.c_cc[VMIN] = 1;   /* read returns when one char is available. */
    t.c_cc[VTIME] = 0;

    if (baud > 0)
    {
        t.c_cflag &= ~(CBAUD | (CBAUD << IBSHIFT)); // clear input/output fields
        t.c_cflag |= BOTHER | (BOTHER << IBSHIFT);  // make kernel use c_ispeed and c_ospeed
        t.c_ispeed = baud;
        t.c_ospeed = baud;
    }

    return ioctl(fd, TCSETS2, &t);
}

void open_serial_port_rx(const char* port, int baud)
{
    Reader.fd = open(port, O_RDONLY | O_NOCTTY | O_NONBLOCK);
    if (Reader.fd < 0)
    {
        perror("fd");
        exit(EXIT_FAILURE);
    }

    set_baud(Reader.fd, baud);
    ioctl(Reader.fd, TCFLSH, TCIFLUSH);

    snprintf(Reader.name, sizeof(Reader.name), "%s", port);
    printf("opened port: %s\n", port);
}

bool32 read_serial_port(QuantizedPacket* packet)
{
    bool32 packet_found = false;

    while (true)
    {
        ssize_t bytes_read = read(Reader.fd, Reader.buf + Reader.len, sizeof(Reader.buf) - Reader.len);

        if (bytes_read > 0)
        {
            Reader.len += bytes_read;

            uint32_t offset = 0;

            while (Reader.len - offset >= sizeof(uint32_t))
            {
                uint32_t magic_candidate = ((uint32_t)Reader.buf[offset + 3] << 24) |
                                           ((uint32_t)Reader.buf[offset + 2] << 16) |
                                           ((uint32_t)Reader.buf[offset + 1] <<  8) |
                                            (uint32_t)Reader.buf[offset + 0];
                if (magic_candidate == MAGIC)
                {
                    if (Reader.len - offset < sizeof(QuantizedPacket))
                    {
                        break; // wait for more
                    }
                    // consume and update offset
                    memcpy(packet, &Reader.buf[offset], sizeof(QuantizedPacket));
                    offset += sizeof(QuantizedPacket);
                    packet_found = true;
                }
                else
                {
                    // update offset by one byte position
                    ++offset;
                }
            }
            memmove(Reader.buf, Reader.buf + offset, Reader.len - offset);
            Reader.len -= offset;
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
        struct pollfd pfd = { .fd = Reader.fd, .events = POLLIN };
        if (poll(&pfd, 1, -1) == -1 && errno != EINTR)
        {
            perror("poll");
            return -1;
        }
    }
}

void open_serial_port_tx(const char* port, int baud)
{
    Pty.master_fd = posix_openpt(O_RDWR | O_NOCTTY);
    if (Pty.master_fd < 0 || grantpt(Pty.master_fd) < 0 || unlockpt(Pty.master_fd) < 0 || (Pty.slave_name = ptsname(Pty.master_fd)) == NULL)
    {
        perror("posix_openpt");
        exit(EXIT_FAILURE);
    }

    Pty.slave_fd = open(Pty.slave_name, O_RDWR | O_NOCTTY);
    if (Pty.slave_fd < 0 || set_baud(Pty.slave_fd, baud))
    {
        perror("slave_fd configuration");
        exit(EXIT_FAILURE);
    }

    // set to non-blocking
    fcntl(Pty.master_fd, F_SETFL, fcntl(Pty.master_fd, F_GETFL) | O_NONBLOCK);

    // Symlinking to deterministic name (pts are generated undeterministically from ptmx)
    unlink(port);
    if (symlink(Pty.slave_name, port) < 0)
    {
        perror("symlink");
    }

    printf("Simulated UART over %s (%s)\n", port, Pty.slave_name);
}

void write_serial_port(void* data, size_t len)
{
    int n = write(Pty.master_fd, data, len);
    if (n < 0 && errno == EAGAIN)
    {
        ioctl(Pty.slave_fd, TCFLSH, TCIFLUSH); // discard backlog, nobody reading from slave
        n = write(Pty.master_fd, data, len);
    }
}

void close_ports(void)
{
    close(Reader.fd);
    close(Pty.master_fd);
    close(Pty.slave_fd);
}

/*
 * int main()
 * {
 *
 *     caller holds onto the file handle?  -> yes: [ ] no: [x]
 *     caller provides port name only?     -> yes: [ ] no: [x] -> we wanna provide baud rate 0 or something different
 *     separate initialization for rx/tx?  -> yes: [x] no: [ ]
 *     surface some error value to caller? -> yes: [x] no: [ ]
 *          - open_serial_port_rx() ->  yes: [x] no: [ ]
 *          - open_serial_port_tx() ->  yes: [x] no: [ ]
 *          - write_serial_port()   ->  yes: [x] no: [ ]
 *          - read_serial_port()    ->  yes: [x] no: [ ]
 *
 *     if (!open_serial_port_rx(&port, "/dev/ttyACM0", 4194304))
 *     {
 *         try again?
 *         exit(EXIT_FAILURE)?
 *         whatever?
 *     }
 *
 *     return 0;
 * }
 */

int main(void)
{
    QuantizedPacket packet;

    // NOTE: I SHOUDLN'T MANGLE THESE TWO, IT IS DISHONEST BECAUSE THEY ARE
    // QUITE DIFFERENT REALLY! GIVE THEM PROPER NAMES! STOP WITH SUCKY ABSTRACTIONS!
    open_serial_port_rx("/dev/ttyACM0", 4194304); // specific packet reader thing
    open_serial_port_tx("/tmp/ttySIM0", 0);       // more of a pty-pair thingy

    while (true)
    {
        if (!read_serial_port(&packet)) break;
        write_serial_port(&packet, sizeof(packet));
    }

    printf("goodbye, thanks for playing\n");
    close_ports();

    return 0;
}
