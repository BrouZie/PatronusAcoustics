#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <termios.h>
#include <pty.h>

int main()
{
    pid_t pid = getpid();
    printf("PID: %d\n", pid);


    char name[64];
    int master, slave;
    struct termios tio;

    // tcgetattr(fd, tio);
    // why not do the tio setup shit and then call openpty?
    if (openpty(&master, &slave, name, NULL, NULL) < 0)
    {
        perror("openpty");
    }

    while (1)
    {
    }

    return 0;
}
