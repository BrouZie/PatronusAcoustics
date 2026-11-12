#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <termios.h>
#include <pty.h>

// TODO: Make packet structs shareable across stm and x86
// TODO: Refactor stuff into x86 code and utils.h

typedef float float32_t;

typedef struct {
    uint32_t magic;       // LOGMEL_MAGIC
    uint32_t seq;         // increments every frame; used to detect drops
    float32_t azimuth;
    float32_t elevation;
} logmel_header_t;

typedef struct {
    logmel_header_t header;
    uint8_t         cells[128];
} logmel_packet_t;

#define PACKET_SIZE sizeof(logmel_packet_t)
#define RX_SIZE (PACKET_SIZE * 4)
#define MAGIC 0x314C4D4C

typedef struct
{
    uint8_t buf[RX_SIZE];
    size_t  len;
} rx_t;

static rx_t Rx;
static logmel_packet_t Packet;

// TODO: Make sure we handle errors we care about
int read_pty_packet(int fd, rx_t* rx, logmel_packet_t* packet)
{
    ssize_t bytes_read = read(fd, rx->buf + rx->len, sizeof(rx->buf) - rx->len);
    if (bytes_read == 0) return -1;
    if (bytes_read < 0)
    {
        perror("read");
        return -1;
    }
    rx->len += bytes_read;

    int offset = 0;
    while (rx->len - offset >= sizeof(uint32_t))
    {
        uint32_t four_byte_value = ((uint32_t)rx->buf[offset + 3] << 24) |
                                   ((uint32_t)rx->buf[offset + 2] << 16) |
                                   ((uint32_t)rx->buf[offset + 1] <<  8) |
                                    (uint32_t)rx->buf[offset + 0];
        if (four_byte_value == MAGIC)
        {
            if (rx->len - offset < PACKET_SIZE)
            {
                break; // wait for more
            }
            // consume and update offset
            memcpy(packet, &rx->buf[offset], PACKET_SIZE);
            offset += PACKET_SIZE;
        }
        else
        {
            // update by one byte
            ++offset;
        }
    }

    memmove(rx->buf, rx->buf + offset, rx->len - offset);
    printf("Raw.len: %zu, read: %zu, offset: %d\n", rx->len, bytes_read, offset);
    rx->len -= offset;

    return 1;
}

int main()
{
    int fd = open("/tmp/ttySIM0", O_RDONLY | O_NOCTTY);

    while (1)
    {
        // TODO: Rx hidden or caller owned? Figure out startup (before reader is up to par with the writer)
        // Check whether the /dev/ttyACM0 behaves identically to /tmp/ttySIM0 (or naht)
        if (!read_pty_packet(fd, &Rx, &Packet)) break;
        printf("Packet.seq: %d\n", Packet.header.seq);
    }

    return 0;
}
