#ifndef TEST_MOCK_MAIN_H
#define TEST_MOCK_MAIN_H
/* Minimal HOST-ONLY HAL test double. This is not a replacement STM32 header.
 * It checks the console state machine, not registers, timing, or real IRQs. */
#include <stdint.h>
typedef enum { HAL_OK = 0, HAL_ERROR, HAL_BUSY, HAL_TIMEOUT } HAL_StatusTypeDef;
typedef struct { void *Instance; uint32_t ErrorCode; } UART_HandleTypeDef;
extern int mock_usart1_instance;
#define USART1 ((void *)&mock_usart1_instance)
#define USART1_IRQn 37
#define UART_IT_RXNE 1u
#define UART_IT_PE 2u
#define UART_IT_ERR 4u
uint32_t __get_PRIMASK(void);
void __disable_irq(void);
void __set_PRIMASK(uint32_t mask);
void mock_uart_disable_it(UART_HandleTypeDef *uart, uint32_t interrupt);
void mock_uart_clear_ore(UART_HandleTypeDef *uart);
#define __HAL_UART_DISABLE_IT(uart, interrupt) mock_uart_disable_it((uart), (interrupt))
#define __HAL_UART_CLEAR_OREFLAG(uart) mock_uart_clear_ore((uart))
HAL_StatusTypeDef HAL_UART_Receive_IT(UART_HandleTypeDef *uart, uint8_t *data, uint16_t size);
HAL_StatusTypeDef HAL_UART_Transmit_IT(UART_HandleTypeDef *uart, const uint8_t *data, uint16_t size);
HAL_StatusTypeDef HAL_UART_AbortReceive(UART_HandleTypeDef *uart);
uint32_t HAL_UART_GetError(UART_HandleTypeDef *uart);
void HAL_NVIC_DisableIRQ(int interrupt);
void HAL_NVIC_EnableIRQ(int interrupt);
void HAL_UART_RxCpltCallback(UART_HandleTypeDef *uart);
void HAL_UART_TxCpltCallback(UART_HandleTypeDef *uart);
void HAL_UART_ErrorCallback(UART_HandleTypeDef *uart);
#endif
