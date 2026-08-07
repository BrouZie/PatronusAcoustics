#ifndef APP_ENTRY_H
#define APP_ENTRY_H

/*
 * Every binary under src/apps/ defines main_app().
 * Core/Src/main.c calls it after HAL_Init(), SystemClock_Config()
 * and the MX_*_Init() functions have run. It is not expected to return.
 */
void app_main(void);

#endif /* APP_ENTRY_H */
