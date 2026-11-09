#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <termios.h>
#include <pty.h>

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

static logmel_packet_t Packet;

typedef struct
{
    uint8_t buf[RX_SIZE];
    size_t  len;
} rx_t;

static rx_t rx;
static int num_packets = 0;

int main()
{
    int fd = open("/tmp/ttySIM0", O_RDONLY | O_NOCTTY);

    int consumed = 0;

    while (1)
    {
        ssize_t bytes_read = read(fd, rx.buf + rx.len, sizeof(rx.buf) - rx.len);
        if (bytes_read == 0) continue;
        if (bytes_read < 0)
        {
            perror("read");
            return 1;
        }
        rx.len += bytes_read;

        int offset = 0;
        while (rx.len - offset >= sizeof(uint32_t))
        {
            uint32_t four_byte_value = ((uint32_t)rx.buf[offset + 3] << 24) |
                                       ((uint32_t)rx.buf[offset + 2] << 16) |
                                       ((uint32_t)rx.buf[offset + 1] <<  8) |
                                        (uint32_t)rx.buf[offset + 0];

            if (four_byte_value == MAGIC)
            {
                if (rx.len - offset < PACKET_SIZE)
                {
                    break; // wait for more
                }
 
                // consume and update offset
                memcpy(&Packet, &rx.buf[offset], PACKET_SIZE);

                // NOTE: Application code here / figure out how to "read_from_stream()"

                printf("MAGIC: %08x, seq: %d\n", Packet.header.magic, Packet.header.seq);
                ++consumed;
                offset += PACKET_SIZE;
            }
            else
            {
                // update by one byte
                ++offset;
            }
        }

        memmove(rx.buf, rx.buf + offset, rx.len - offset);
        printf("Raw.len: %zu, read: %zu, offset: %d, consumed: %d\n", rx.len, bytes_read, offset, consumed);
        rx.len -= offset;
        consumed = 0;
    }

    return 0;
}
