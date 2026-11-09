#include <errno.h>
#include <fcntl.h>
#include <string.h>
#include <stdint.h>
#include <unistd.h>
#include <termios.h>
#include <pty.h>


uint8_t tx[7] = "Hello\n";
uint8_t rx[7];

int str_length(const char* str)
{
    int len = 0;
    while (str[len])
    {
        ++len;
    }
    return len;
}

int main()
{
    int fd = open("opening.txt", O_RDWR | O_CREAT, S_IRWXU);
    if (fd < 0)
    {
        int err = errno;
        const char* msg = strerror(err);
        write(STDERR_FILENO, "open failed: ", 13);
        write(STDERR_FILENO, msg, str_length(msg));
        write(STDERR_FILENO, "\n", 1);
    }

    int written = write(fd, tx, sizeof(tx));
    if (lseek(fd, 0, SEEK_SET) < 0)
    {
    }
    if (read(fd, rx, written - 1) < 0)
    {
    }
    if (write(STDOUT_FILENO, rx, sizeof(rx)) < 0)
    {
    }

    return 0;
}
