#define _GNU_SOURCE

#include "serialport.h"

#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include <poll.h>
#include <asm/termbits.h>
#include <sys/ioctl.h>

#include <stdlib.h>
#include <stdio.h>

void serial_close(SerialPort* port)
{
    close(port->fd);
    port->state = CLOSED;
}

void pty_link_close(PtySymlink* pty)
{
    serial_close(&pty->master);
    serial_close(&pty->slave);
    unlink(pty->link_name);
}

internal inline int set_baud(int fd, int baud)
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

SerialPort serial_open(const char* path, int baud)
{
    SerialPort port = {0};
    port.fd = open(path, O_RDWR | O_NOCTTY | O_NONBLOCK);
    if (port.fd < 0)
    {
        fprintf(stderr, "[ERROR]: %s not found\n", path);
        serial_close(&port);
    }
    else
    {
        set_baud(port.fd, baud);
        ioctl(port.fd, TCFLSH, TCIFLUSH);
        port.state = OPEN;
    }

    return port;
}

bool32 read_latest_packet(SerialPort* port, PacketReader* reader, Full_Packet* packet)
{
    if (port->state == CLOSED)
    {
        return false;
    }

    bool32 packet_found = false;

    while (true)
    {
        ssize_t bytes_read = read(port->fd, reader->buf + reader->len, sizeof(reader->buf) - reader->len);
        if (bytes_read > 0)
        {
            reader->len += (size_t)bytes_read;

            uint32_t offset = 0;

            while (reader->len - offset >= sizeof(uint32_t))
            {
                uint32_t magic_candidate = ((uint32_t)reader->buf[offset + 3] << 24) |
                                           ((uint32_t)reader->buf[offset + 2] << 16) |
                                           ((uint32_t)reader->buf[offset + 1] <<  8) |
                                            (uint32_t)reader->buf[offset + 0];
                if (magic_candidate == MAGIC)
                {
                    if (reader->len - offset < sizeof(Full_Packet))
                    {
                        break; // wait for more
                    }
                    // consume and update offset
                    memcpy(packet, &reader->buf[offset], sizeof(Full_Packet));
                    offset += sizeof(Full_Packet);
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
            serial_close(port);
            return false;
        }

        /// We've cought up to the datastream: read_bytes == -1 ///

        if (errno == EINTR) continue;

        // Kernel buffer is empty and packet found
        if (packet_found)
        {
            // Newest packet is ready and we returned to caller
            return true;
        }

        // no packet, and no data available yet -> poll for more data
        struct pollfd pfd = { .fd = port->fd, .events = POLLIN };
        if (poll(&pfd, 1, -1) == -1 && errno == EINTR)
        {
            // Return false on interrupts when stuck polling
            return false;
        }
    }
}

PtySymlink pty_link_open(const char* link_path)
{
    PtySymlink pty = {0};

    pty.master.fd = posix_openpt(O_RDWR | O_NOCTTY);
    if (pty.master.fd < 0 || grantpt(pty.master.fd) < 0
            || unlockpt(pty.master.fd) < 0
            || ptsname_r(pty.master.fd, pty.slave_name, sizeof(pty.slave_name)))
    {
        fprintf(stderr, "[ERROR]: pty-pair creation failed\n");
        pty.master.state = CLOSED;
        close(pty.master.fd);
    }

    pty.slave.fd = open(pty.slave_name, O_RDWR | O_NOCTTY);
    if (pty.slave.fd < 0 || set_baud(pty.slave.fd, 0))
    {
        fprintf(stderr, "[ERROR]: slave configuration failed\n");
        pty.slave.state = CLOSED;
        close(pty.slave.fd);
    }

    // set to non-blocking
    fcntl(pty.master.fd, F_SETFL, fcntl(pty.master.fd, F_GETFL) | O_NONBLOCK);

    // Symlinking to deterministic name (pts are generated undeterministically from ptmx)
    unlink(link_path);
    if (symlink(pty.slave_name, link_path) < 0)
    {
        fprintf(stderr, "[ERROR]: Symlinking failed\n");
    }
    snprintf(pty.link_name, sizeof(pty.link_name), "%s", link_path);

    return pty;
}

ssize_t pty_link_write(PtySymlink* pty, void* data, size_t len)
{
    if (pty->master.state == CLOSED)
    {
        return 0;
    } 
    ssize_t n = write(pty->master.fd, data, len);
    if (n < 0 && errno == EAGAIN)
    {
        ioctl(pty->slave.fd, TCFLSH, TCIFLUSH); // discard backlog, nobody reading from slave
        n = write(pty->master.fd, data, len);
        return n;
    }
    return n;
}

ssize_t serial_write(SerialPort* port, void* data, size_t len)
{
    if (port->state == CLOSED)
    {
        return 0;
    } 
    ssize_t n = write(port->fd, data, len);
    if (n < 0)
    {
        serial_close(port);
        return 0;
    }
    return n;
}
