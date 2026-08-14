#include "startup_ws.h"

void HAL_TIM_PeriodElapsedCallback(TIM_HandleTypeDef *htim) // Interrupt action for TIM7
{
  if (htim->Instance == TIM7)
  {
	Enable_SAI_FS_Pin();
  }
}

void Disable_SAI_FS_Pin(void) // Force WS low before/while configuring it
{
    HAL_GPIO_WritePin(GPIOE, GPIO_PIN_4, GPIO_PIN_RESET);

    GPIO_InitTypeDef GPIO_InitStruct = {0};

    GPIO_InitStruct.Pin = GPIO_PIN_4;
    GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
    GPIO_InitStruct.Pull = GPIO_NOPULL;
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;

    HAL_GPIO_Init(GPIOE, &GPIO_InitStruct);
}

void Enable_SAI_FS_Pin(void) // Helper function to re-assign PE4 from GPIO mode to SAI_FS_A
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};
  
  GPIO_InitStruct.Pin = GPIO_PIN_4; // PE4 = SAI1_FS_A
  GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;
  GPIO_InitStruct.Alternate = GPIO_AF6_SAI1;
  HAL_GPIO_Init(GPIOE, &GPIO_InitStruct);
}
