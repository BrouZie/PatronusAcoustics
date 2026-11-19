#define _GNU_SOURCE
#include <stdio.h>
#include <unistd.h>

#include <asm/termbits.h>
#include <sys/ioctl.h>
#include <fcntl.h>
#include <stdlib.h>

#define SYSCALL_LT0(func) do { \
    if ((func) < 0) {          \
        perror(#func);         \
        exit(EXIT_FAILURE);    \
    }; } while(0)

// Copied from source https://github.com/lattera/glibc/blob/master/termios/cfmakeraw.c
// - swapped out termios for termios2
void make_raw(struct termios2* t)
{
    t->c_iflag &= ~(IGNBRK | BRKINT | PARMRK | ISTRIP | INLCR | IGNCR | ICRNL | IXON);
    t->c_oflag &= ~OPOST;
    t->c_lflag &= ~(ECHO | ECHONL | ICANON | ISIG | IEXTEN);
    t->c_cflag &= ~(CSIZE | PARENB);
    t->c_cflag |= CS8;
    t->c_cc[VMIN] = 1;   /* read returns when one char is available. */
    t->c_cc[VTIME] = 0;
}

int main()
{
    pid_t pid = getpid();
    printf("PID: %d\n", pid);

    int slavefd;
    char* slave_name;

    // tcgetattr(fd, tio);
    // why not do the tio setup shit and then call openpty?
    int masterfd = posix_openpt(O_RDWR | O_NOCTTY);

    if (masterfd < 0 || grantpt(masterfd) < 0 || unlockpt(masterfd) < 0
            || (slave_name = ptsname(masterfd)) == NULL)
    {
        perror("master pty");
        exit(EXIT_FAILURE);
    }

    slavefd = open(slave_name, O_RDWR | O_NOCTTY);
    if (slavefd < 0) exit(EXIT_FAILURE);

    struct termios2 t;
    SYSCALL_LT0(ioctl(slavefd, TCGETS2, &t));
    make_raw(&t);

    int baud = 4194304;
    if (baud > 0)
    {
        t.c_cflag &= ~(CBAUD | (CBAUD << IBSHIFT)); // clear input/output fields
        t.c_cflag |= BOTHER | (BOTHER << IBSHIFT);  // make kernel use c_ispeed and c_ospeed
        t.c_ispeed = baud;
        t.c_ospeed = baud;
    }

    fcntl(masterfd, F_SETFL, fcntl(masterfd, F_GETFL) | O_NONBLOCK);

    SYSCALL_LT0(ioctl(slavefd, TCSETS2, &t));
    SYSCALL_LT0(ioctl(slavefd, TCFLSH, TCIFLUSH));

    char* port = "/tmp/ttySIM0";
    unlink(port);
    SYSCALL_LT0(symlink(slave_name, port));
    
    printf("Simulated UART over %s (%s)\n", port, slave_name);

    while (1)
    {
    }

    return 0;
}
