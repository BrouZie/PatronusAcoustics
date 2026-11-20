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
    uint8_t buf[sizeof(QuantizedPacket) * 4];
    size_t  len;
} PacketReader;

typedef struct
{
    int fd;
} SerialPort;

typedef struct
{
    int  master_fd;
    int  slave_fd;
    char link_name[64];
    char slave_name[64];
} PtyPair;

static PacketReader Reader;

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

SerialPort open_serial_port(const char* port, int baud)
{
    int port_fd = open(port, O_RDWR | O_NOCTTY | O_NONBLOCK);
    if (port_fd < 0)
    {
        perror("fd");
        exit(EXIT_FAILURE);
    }

    set_baud(port_fd, baud);
    ioctl(port_fd, TCFLSH, TCIFLUSH);

    printf("opened port: %s\n", port);

    return (SerialPort) { .fd = port_fd };
}

// TODO(sok): Check whether error handling works as anticipated
bool32 read_latest_packet(int fd, QuantizedPacket* packet)
{
    bool32 packet_found = false;

    while (true)
    {
        ssize_t bytes_read = read(fd, Reader.buf + Reader.len, sizeof(Reader.buf) - Reader.len);

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
        struct pollfd pfd = { .fd = fd, .events = POLLIN };
        if (poll(&pfd, 1, -1) == -1 && errno != EINTR)
        {
            perror("poll");
            return false;
        }
    }
}

PtyPair pty_create(const char* link_path)
{
    PtyPair pty = {0};

    pty.master_fd = posix_openpt(O_RDWR | O_NOCTTY);
    if (pty.master_fd < 0 || grantpt(pty.master_fd) < 0
            || unlockpt(pty.master_fd) < 0
            || ptsname_r(pty.master_fd, pty.slave_name, sizeof(pty.slave_name)))
    {
        perror("posix_openpt");
        exit(EXIT_FAILURE);
    }

    pty.master_fd = open(pty.slave_name, O_RDWR | O_NOCTTY);
    if (pty.slave_fd < 0 || set_baud(pty.slave_fd, 0))
    {
        perror("slave_fd configuration");
        exit(EXIT_FAILURE);
    }

    // set to non-blocking
    fcntl(pty.master_fd, F_SETFL, fcntl(pty.master_fd, F_GETFL) | O_NONBLOCK);

    // Symlinking to deterministic name (pts are generated undeterministically from ptmx)
    unlink(link_path);
    if (symlink(pty.slave_name, link_path) < 0)
    {
        perror("symlink");
    }

    printf("Simulated UART over %s (%s)\n", link_path, pty.slave_name);

    return pty;
}

// TODO(sok): Add error handling & consider merging write
void pty_write(PtyPair pty, void* data, size_t len)
{
    ssize_t n = write(pty.master_fd, data, len);
    if (n < 0 && errno == EAGAIN)
    {
        ioctl(pty.slave_fd, TCFLSH, TCIFLUSH); // discard backlog, nobody reading from slave
        n = write(pty.master_fd, data, len);
        if (n < 0) perror("write");
    }
}

// TODO(sok): Add error handling
void write_serial_port(int port_fd, void* data, size_t len)
{
    ssize_t n = write(port_fd, data, len);
    if (n < 0 && errno == EAGAIN)
    {
        perror("write");
        exit(EXIT_FAILURE);
    }
}

int main(void)
{
    // int port_fd = open_serial_port("/dev/ttyACM0", 4194304);
    //
    // char character = 'c';
    // // char out;
    //
    // while (1)
    // {
    //     write_serial_port(port_fd, &character, 1);
    //     usleep(500000);
    // }

    QuantizedPacket packet;

    SerialPort port = open_serial_port("/dev/ttyACM0", 4194304);
    PtyPair pty = pty_create("/tmp/ttySIM0");                   // NOTE: MIGHT FAIL BECAUSE OF "ptsname_r" CHANGE

    while (true)
    {
        if (!read_latest_packet(port.fd, &packet)) break; // specific packet reader thing
        pty_write(pty, &packet, sizeof(packet));
    }

    printf("goodbye, thanks for playing\n");

    return 0;
}
