/* Integration material; not standalone firmware, not hardware-validated.
 * This module uses HAL_UART_Receive_IT/Transmit_IT and NO UART DMA.
 * USE_HAL_UART_REGISTER_CALLBACKS must stay 0 (normal weak callback model).
 */
#include "main.h"
#include "uart_console.h"
#include <stddef.h>
#include <string.h>

extern UART_HandleTypeDef huart1; /* created by CubeMX */

static volatile digital_byte_queue_t rx_queue;
static digital_line_parser_t line_parser;
static uint8_t rx_byte;
static uint8_t tx_buffer[128];
static volatile uint8_t tx_busy;
static volatile uint8_t recovery_pending;
static volatile uint8_t drop_until_eol;
static volatile uint32_t rx_epoch;
static uint32_t parser_epoch;
static volatile uart_console_stats_t stats;

static uint32_t irq_save(void)
{
    const uint32_t saved = __get_PRIMASK();
    __disable_irq();
    return saved;
}

static bool is_eol(uint8_t byte)
{
    return byte == (uint8_t)'\r' || byte == (uint8_t)'\n';
}

static void request_recovery(void)
{
    recovery_pending = 1u;
    /* Prevent repeated RX errors from starving main before it can recover. */
    __HAL_UART_DISABLE_IT(&huart1, UART_IT_RXNE);
    __HAL_UART_DISABLE_IT(&huart1, UART_IT_PE);
    __HAL_UART_DISABLE_IT(&huart1, UART_IT_ERR);
}

bool uart_console_start(void)
{
    digital_queue_init(&rx_queue);
    digital_line_init(&line_parser);
    parser_epoch = 0u;
    rx_epoch = 0u;
    recovery_pending = 0u;
    drop_until_eol = 0u;
    tx_busy = 0u;
    const HAL_StatusTypeDef result = HAL_UART_Receive_IT(&huart1, &rx_byte, 1u);
    if (result != HAL_OK) {
        ++stats.rearm_failures;
        request_recovery();
        return false;
    }
    return true;
}

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *uart)
{
    if (uart->Instance != USART1) return;
    ++stats.rx_bytes;
    if (drop_until_eol != 0u) {
        if (is_eol(rx_byte)) drop_until_eol = 0u;
    } else if (!digital_queue_push(&rx_queue, rx_byte)) {
        ++stats.queue_overflows;
        /* A missing byte can turn one command into another: discard, resync. */
        digital_queue_init(&rx_queue);
        ++rx_epoch;
        drop_until_eol = (uint8_t)(is_eol(rx_byte) ? 0u : 1u);
    }
    if (recovery_pending == 0u &&
        HAL_UART_Receive_IT(uart, &rx_byte, 1u) != HAL_OK) {
        ++stats.rearm_failures;
        request_recovery();
    }
}

void HAL_UART_ErrorCallback(UART_HandleTypeDef *uart)
{
    if (uart->Instance != USART1) return;
    ++stats.hal_errors;
    stats.last_hal_error = HAL_UART_GetError(uart);
    request_recovery(); /* No delay, printf, abort loop, or blocking transmit. */
}

void HAL_UART_TxCpltCallback(UART_HandleTypeDef *uart)
{
    if (uart->Instance == USART1) tx_busy = 0u;
}

static void recover_rx_if_needed(void)
{
    if (recovery_pending == 0u) return;
    /* This main-only function is the only place that masks USART1 in normal
       operation; CubeMX enables this IRQ. SysTick and other IRQs remain live.
       NO DMA is configured, so AbortReceive only stops the current IRQ RX. */
    HAL_NVIC_DisableIRQ(USART1_IRQn);
    HAL_StatusTypeDef result = HAL_UART_AbortReceive(&huart1);
    __HAL_UART_CLEAR_OREFLAG(&huart1); /* F1: SR read followed by DR read */
    digital_queue_init(&rx_queue);
    ++rx_epoch;
    drop_until_eol = 1u; /* also discard the possibly damaged line's tail */
    recovery_pending = 0u;
    if (result == HAL_OK) result = HAL_UART_Receive_IT(&huart1, &rx_byte, 1u);
    if (result != HAL_OK) {
        ++stats.rearm_failures;
        request_recovery();
    }
    HAL_NVIC_EnableIRQ(USART1_IRQn);
}

void uart_console_poll(void)
{
    recover_rx_if_needed();
    for (unsigned budget = 0u; budget < 32u; ++budget) {
        uint8_t byte = 0u;
        const uint32_t saved = irq_save();
        const uint32_t epoch = rx_epoch;
        const bool have_byte = digital_queue_pop(&rx_queue, &byte);
        __set_PRIMASK(saved);
        if (epoch != parser_epoch) {
            digital_line_init(&line_parser);
            parser_epoch = epoch;
        }
        if (!have_byte) break;
        digital_command_t command;
        const digital_line_result_t result =
            digital_line_feed(&line_parser, byte, &command);
        if (result == DIGITAL_LINE_COMMAND) {
            uart_console_on_command(&command);
        } else if (result == DIGITAL_LINE_INVALID || result == DIGITAL_LINE_OVERLONG) {
            ++stats.line_errors;
            (void)uart_console_reply("ERR LINE\r\n");
        }
    }
}

bool uart_console_reply(const char *text)
{
    if (tx_busy != 0u) {
        ++stats.tx_dropped;
        return false; /* explicit drop policy; caller may retry later */
    }
    size_t length = 0u;
    while (length < sizeof(tx_buffer) && text[length] != '\0') ++length;
    if (length == 0u || length == sizeof(tx_buffer)) {
        ++stats.tx_dropped;
        return false;
    }
    memcpy(tx_buffer, text, length);
    tx_busy = 1u;
    if (HAL_UART_Transmit_IT(&huart1, tx_buffer, (uint16_t)length) != HAL_OK) {
        tx_busy = 0u;
        ++stats.tx_dropped;
        return false;
    }
    return true;
}

bool uart_console_tx_idle(void)
{
    return tx_busy == 0u;
}

bool uart_console_rx_ready(void)
{
    return recovery_pending == 0u;
}

void uart_console_get_stats(uart_console_stats_t *out)
{
    const uint32_t saved = irq_save();
    out->rx_bytes = stats.rx_bytes;
    out->queue_overflows = stats.queue_overflows;
    out->hal_errors = stats.hal_errors;
    out->rearm_failures = stats.rearm_failures;
    out->line_errors = stats.line_errors;
    out->tx_dropped = stats.tx_dropped;
    out->last_hal_error = stats.last_hal_error;
    __set_PRIMASK(saved);
}
