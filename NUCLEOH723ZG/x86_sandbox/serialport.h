#ifndef SERIALPORT_H
#define SERIALPORT_H

#include "packet.h"
#include "types.h"

#include <sys/types.h>

typedef enum {
    CLOSED, OPEN
} PortState;

typedef struct
{
    int fd;
    PortState state;
} SerialPort;

typedef struct
{
    SerialPort master;
    SerialPort slave;

    char link_name[64];
    char slave_name[64];
} PtySymlink;

typedef struct
{
    uint8_t buf[sizeof(Full_Packet) * 4];
    size_t  len;
} PacketReader;

SerialPort serial_open (const char* path, int baud);
ssize_t    serial_write(SerialPort* port, void* data, size_t len);
void       serial_close(SerialPort* port);

PtySymlink pty_link_open (const char* link_path);
ssize_t    pty_link_write(PtySymlink* pty, void* data, size_t len);
void       pty_link_close(PtySymlink* pty);

/*
   The function polls the passed port until a packet is found. However,
   if the port is disconnected or an interrupt is fired `false` is
   returned.

   PARAMETERS:
    port:   specifies where we read from - what port/file descriptor we poll.
    reader: TODO(sok): coupled with the packet? Or just scratch buf? Or something else?
    packet: out parameter for the newly discovered packet.

   RETURN VALUE:
    true:  new packet is successfully found and read.
    false: port is closed or interrupt fired during polling (errno == EINTR).

   OUT PARAMETER:
    packet: contains the latest packet, given the function returned `true`
*/
// TODO(sok): Add magic from global header elns.
bool32 read_latest_packet(SerialPort* port, PacketReader* reader, Full_Packet* packet);

#endif // SERIALPORT_H
