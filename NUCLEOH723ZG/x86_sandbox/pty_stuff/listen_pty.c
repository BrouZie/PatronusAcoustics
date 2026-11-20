#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include <poll.h>
#include <asm/termbits.h>
#include <sys/ioctl.h>


// FIX: WERID BUG WITH SIGNAL HANDLER, BAUD RATE (0 VS. 4194304)
// AND WRITERS RETURN VALUE OR SOMETHING (bool vs. int)
// - CHECK DEBUGGER BITCH!

/* TODO(sok): Before full merge:
    1. Move packet def to global header
    2. Decide interface for working with serial ports. Things to consider:
        - Ownership
        - Error-handling & printouts
        - Struct defs
    3. Move full implementation to utils.h
    4. Ideally, rework logmel_viewer, spectrum_viewer ++ (to use same global packet header)
*/

#include <signal.h>

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

SerialPort serial_open(const char* port, int baud)
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
bool32 read_latest_packet(int fd, PacketReader* reader, QuantizedPacket* packet)
{
    bool32 packet_found = false;

    while (true)
    {
        ssize_t bytes_read = read(fd, reader->buf + reader->len, sizeof(reader->buf) - reader->len);

        if (bytes_read > 0)
        {
            reader->len += bytes_read;

            uint32_t offset = 0;

            while (reader->len - offset >= sizeof(uint32_t))
            {
                uint32_t magic_candidate = ((uint32_t)reader->buf[offset + 3] << 24) |
                                           ((uint32_t)reader->buf[offset + 2] << 16) |
                                           ((uint32_t)reader->buf[offset + 1] <<  8) |
                                            (uint32_t)reader->buf[offset + 0];
                if (magic_candidate == MAGIC)
                {
                    if (reader->len - offset < sizeof(QuantizedPacket))
                    {
                        break; // wait for more
                    }
                    // consume and update offset
                    memcpy(packet, &reader->buf[offset], sizeof(QuantizedPacket));
                    offset += sizeof(QuantizedPacket);
                    packet_found = true;
                }
                else
                {
                    // update offset by one byte position
                    ++offset;
                }
            }
            memmove(reader->buf, reader->buf + offset, reader->len - offset);
            reader->len -= offset;
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

    pty.slave_fd = open(pty.slave_name, O_RDWR | O_NOCTTY);
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
    snprintf(pty.link_name, sizeof(pty.link_name), "%s", link_path);

    printf("Simulated UART over %s (%s)\n", link_path, pty.slave_name);

    return pty;
}

int pty_write(PtyPair* pty, void* data, size_t len)
{
    ssize_t n = write(pty->master_fd, data, len);
    if (n < (ssize_t)len) return false;
    if (n < 0 && errno == EAGAIN)
    {
        ioctl(pty->slave_fd, TCFLSH, TCIFLUSH); // discard backlog, nobody reading from slave
        n = write(pty->master_fd, data, len);
        return (int)n;
    }
    return (int)n;
}

int serial_write(SerialPort port, void* data, size_t len)
{
    return write(port.fd, data, len);
}

void pty_close(PtyPair* pty)
{
    close(pty->master_fd);
    close(pty->slave_fd);
    unlink(pty->link_name);
}

static bool quit = false;

void signal_handler(int sigint)
{
    (void)sigint;
    quit = true;
}

int main(void)
{
    // SerialPort port = serial_open("/dev/ttyACM0", 4194304);
    //
    // char character = 'c';
    // // char out;
    //
    // while (1)
    // {
    //     serial_write(port, &character, 1);
    //     usleep(500000);
    // }

    signal(SIGINT, signal_handler);

    PacketReader reader = {};
    QuantizedPacket packet;

    SerialPort port = serial_open("/dev/ttyACM0", 4194304);
    PtyPair pty = pty_create("/tmp/ttySIM0");

    while (!quit)
    {
        if (!read_latest_packet(port.fd, &reader, &packet)) break; // specific packet reader thing
        pty_write(&pty, &packet, sizeof(packet));

        // printf("seq: %d, slave_fd: %d, slave_name: %s, link_name: %s\n", packet.header.seq, pty.slave_fd, pty.slave_name, pty.link_name);
        // usleep(500000);
    }

    pty_close(&pty);
    close(port.fd);

    printf("\nGoodbye, thanks for playing\n");

    return 0;
}
