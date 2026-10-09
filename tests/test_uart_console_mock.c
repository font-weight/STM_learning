#include "main.h"
#include "uart_console.h"
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

int mock_usart1_instance;
UART_HandleTypeDef huart1 = {USART1, 0u};
static uint32_t primask;
static bool usart_irq_enabled = true;
static uint8_t *rx_address;
static bool rx_armed;
static bool fail_next_rearm;
static bool fail_next_abort;
static bool fail_next_tx;
static uint32_t ore_clears;
static const uint8_t *tx_address;
static uint16_t tx_length;
static uint32_t tx_starts;
static digital_command_t commands[128];
static unsigned command_count;

uint32_t __get_PRIMASK(void) { return primask; }
void __disable_irq(void) { primask = 1u; }
void __set_PRIMASK(uint32_t mask) { primask = mask; }
void mock_uart_disable_it(UART_HandleTypeDef *uart, uint32_t interrupt)
{
    assert(uart == &huart1);
    if (interrupt == UART_IT_RXNE) rx_armed = false;
}
void mock_uart_clear_ore(UART_HandleTypeDef *uart)
{
    assert(uart == &huart1);
    ++ore_clears;
}
HAL_StatusTypeDef HAL_UART_Receive_IT(UART_HandleTypeDef *uart, uint8_t *data, uint16_t size)
{
    assert(uart == &huart1 && size == 1u);
    if (fail_next_rearm) { fail_next_rearm = false; return HAL_BUSY; }
    assert(!rx_armed);
    rx_address = data;
    rx_armed = true;
    return HAL_OK;
}
HAL_StatusTypeDef HAL_UART_Transmit_IT(UART_HandleTypeDef *uart, const uint8_t *data, uint16_t size)
{
    assert(uart == &huart1);
    if (fail_next_tx) { fail_next_tx = false; return HAL_ERROR; }
    assert(tx_address == NULL);
    tx_address = data;
    tx_length = size;
    ++tx_starts;
    return HAL_OK;
}
HAL_StatusTypeDef HAL_UART_AbortReceive(UART_HandleTypeDef *uart)
{
    assert(uart == &huart1 && !usart_irq_enabled);
    rx_armed = false;
    if (fail_next_abort) { fail_next_abort = false; return HAL_ERROR; }
    return HAL_OK;
}
uint32_t HAL_UART_GetError(UART_HandleTypeDef *uart) { return uart->ErrorCode; }
void HAL_NVIC_DisableIRQ(int interrupt)
{
    assert(interrupt == USART1_IRQn);
    usart_irq_enabled = false;
}
void HAL_NVIC_EnableIRQ(int interrupt)
{
    assert(interrupt == USART1_IRQn);
    usart_irq_enabled = true;
}
void uart_console_on_command(const digital_command_t *command)
{
    assert(command_count < sizeof commands / sizeof commands[0]);
    commands[command_count++] = *command;
}

static void receive_byte(uint8_t byte)
{
    assert(rx_armed && usart_irq_enabled && primask == 0u);
    *rx_address = byte;
    rx_armed = false; /* HAL completes the one-byte request before callback. */
    HAL_UART_RxCpltCallback(&huart1);
}
static void receive_text(const char *text)
{
    for (size_t i = 0u; text[i] != '\0'; ++i) receive_byte((uint8_t)text[i]);
}
static void finish_tx(void)
{
    assert(tx_address != NULL);
    tx_address = NULL;
    tx_length = 0u;
    HAL_UART_TxCpltCallback(&huart1);
}
static void trigger_error(uint32_t error)
{
    huart1.ErrorCode = error;
    HAL_UART_ErrorCallback(&huart1);
}

int main(void)
{
    assert(uart_console_start());
    assert(uart_console_rx_ready());
    receive_text("LED 1\n");
    uart_console_poll();
    assert(command_count == 1u && commands[0].kind == DIGITAL_CMD_LED && commands[0].value == 1u);

    /* A previously parsed prefix must not survive FIFO loss. */
    receive_text("PER");
    uart_console_poll();
    for (unsigned i = 0u; i < DIGITAL_QUEUE_CAPACITY + 1u; ++i) receive_byte('X');
    receive_text("IOD 50\nLED 0\n");
    uart_console_poll();
    assert(command_count == 2u && commands[1].kind == DIGITAL_CMD_LED && commands[1].value == 0u);

    /* The overflowing byte can itself be EOL: do not drop the next good line. */
    for (unsigned i = 0u; i < DIGITAL_QUEUE_CAPACITY; ++i) receive_byte('X');
    receive_text("\nSTATUS\n");
    uart_console_poll();
    assert(command_count == 3u && commands[2].kind == DIGITAL_CMD_STATUS);

    /* HAL error: uncertain suffix is discarded until its next separator. */
    receive_text("LED ");
    uart_console_poll();
    trigger_error(8u);
    assert(!uart_console_rx_ready());
    uart_console_poll();
    assert(uart_console_rx_ready() && ore_clears == 1u);
    receive_text("1\nSTATUS\n");
    uart_console_poll();
    assert(command_count == 4u && commands[3].kind == DIGITAL_CMD_STATUS);

    /* Failed ISR rearm and failed abort each retry in a later main iteration. */
    fail_next_rearm = true;
    receive_byte('X');
    assert(!uart_console_rx_ready());
    fail_next_abort = true;
    uart_console_poll();
    assert(!uart_console_rx_ready() && usart_irq_enabled);
    uart_console_poll();
    assert(uart_console_rx_ready() && usart_irq_enabled);
    receive_text("\nPERIOD 100\n");
    uart_console_poll();
    assert(command_count == 5u && commands[4].kind == DIGITAL_CMD_PERIOD);

    /* Parser damage does not dispatch and subsequent line is valid. */
    receive_text("LED 9\n");
    uart_console_poll();
    assert(command_count == 5u && !uart_console_tx_idle());
    assert(tx_length == 10u && memcmp(tx_address, "ERR LINE\r\n", 10u) == 0);
    finish_tx();

    char reply[] = "STATUS COPY\r\n";
    assert(uart_console_reply(reply));
    memset(reply, 'X', sizeof reply - 1u);
    assert(tx_length == 13u && memcmp(tx_address, "STATUS COPY\r\n", 13u) == 0);
    const uint32_t starts_before_busy = tx_starts;
    assert(!uart_console_reply("BUSY\r\n"));
    assert(tx_starts == starts_before_busy);
    finish_tx();
    assert(uart_console_tx_idle());
    char too_long[129];
    memset(too_long, 'Z', 128u);
    too_long[128] = '\0';
    assert(!uart_console_reply(too_long));
    too_long[127] = '\0';
    assert(uart_console_reply(too_long));
    assert(tx_length == 127u);
    finish_tx();
    fail_next_tx = true;
    assert(!uart_console_reply("ERR\r\n") && uart_console_tx_idle());

    uart_console_stats_t stats;
    primask = 1u;
    uart_console_get_stats(&stats);
    assert(primask == 1u); /* restore old mask, do not blindly enable IRQs */
    primask = 0u;
    assert(stats.queue_overflows == 2u);
    assert(stats.hal_errors == 1u && stats.last_hal_error == 8u);
    assert(stats.rearm_failures == 2u);
    assert(stats.line_errors == 1u && stats.tx_dropped == 3u);
    assert(stats.rx_bytes > 128u);
    /* L04: a poll boundary is not a message boundary. Check every split of
       the same command, including before and after all content bytes. */
    const char fragmented[] = "PERIOD 250";
    for (size_t split = 0u; split <= sizeof fragmented - 1u; ++split) {
        const unsigned before = command_count;
        for (size_t i = 0u; i < split; ++i) receive_byte((uint8_t)fragmented[i]);
        uart_console_poll();
        assert(command_count == before);
        for (size_t i = split; i < sizeof fragmented - 1u; ++i)
            receive_byte((uint8_t)fragmented[i]);
        uart_console_poll();
        assert(command_count == before); /* still no delimiter */
        receive_text("\r\n");
        uart_console_poll();
        assert(command_count == before + 1u);
        assert(commands[before].kind == DIGITAL_CMD_PERIOD && commands[before].value == 250u);
    }
    /* Six seven-byte commands fit FIFO but exceed the per-poll 32-byte
       budget. Four dispatch now; two dispatch in the next iteration. */
    const unsigned before_budget = command_count;
    receive_text("STATUS\nSTATUS\nSTATUS\nSTATUS\nSTATUS\nSTATUS\n");
    uart_console_poll();
    assert(command_count == before_budget + 4u);
    uart_console_poll();
    assert(command_count == before_budget + 6u);
    for (unsigned i = before_budget; i < command_count; ++i)
        assert(commands[i].kind == DIGITAL_CMD_STATUS);

    puts("PASS: UART console mock: RX resync, HAL-error recovery, TX ownership, mask restore");
    puts("PASS: UART console mock: all command splits and bounded 32-byte poll");
    puts("NOTE: HAL is a host test double; this is not an ARM build or hardware test.");
    return 0;
}
