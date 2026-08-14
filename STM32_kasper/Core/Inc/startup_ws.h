#ifndef STARTUPWS_H
#define STARTUPWS_H

#include "stm32h7xx_hal.h"
#include "stdio.h"
#include "main.h"

extern TIM_HandleTypeDef htim7;

void Disable_SAI_FS_Pin(void);
void Enable_SAI_FS_Pin(void); 

#endif /* STARTUPWS_H */
