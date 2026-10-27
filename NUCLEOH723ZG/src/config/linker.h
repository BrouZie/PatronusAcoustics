#ifndef LINKER_H
#define LINKER_H

#define DTCM __attribute__((section(".dtcm_buf")))
#define RAM1 __attribute__((section(".d1_buf")))
#define RAM2 __attribute__((section(".d2_buf")))

#endif
