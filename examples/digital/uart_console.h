#ifndef UART_CONSOLE_H
#define UART_CONSOLE_H

#include <stdbool.h>
#include <stdint.h>
#include "digital_helpers.h"

/* Integration example for generated STM32F1 HAL1, USART1 interrupt mode only.
 * Main-loop API: do not call these functions from an ISR.
 * There is one owner of huart1: do not start other transfers behind this module.
 */
typedef struct {
    uint32_t rx_bytes;
    uint32_t queue_overflows;
    uint32_t hal_errors;
    uint32_t rearm_failures;
    uint32_t line_errors;
    uint32_t tx_dropped;
    uint32_t last_hal_error;
} uart_console_stats_t;

bool uart_console_start(void);
void uart_console_poll(void); /* bounded: at most 32 received bytes per call */
bool uart_console_reply(const char *text); /* copies up to 127 chars to own TX buffer */
bool uart_console_tx_idle(void);
bool uart_console_rx_ready(void);
void uart_console_get_stats(uart_console_stats_t *out);

/* Implement exactly once in user main.c USER CODE BEGIN 4 or app.c.
 * Called only from uart_console_poll(), never from an ISR. */
void uart_console_on_command(const digital_command_t *command);

#endif
