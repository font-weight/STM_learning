#ifndef DIGITAL_HELPERS_H
#define DIGITAL_HELPERS_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* Pure C11 helpers: no HAL, allocation, peripheral access, or hidden clock.
 * Callers own synchronization. The queue is volatile for ISR visibility;
 * volatile DOES NOT make queue operations atomic. See L02 and L04.
 * All pointer arguments must point to valid objects; text length must describe
 * readable bytes. Invalid pointers are not part of the input grammar.
 */

bool digital_elapsed(uint32_t now, uint32_t then, uint32_t interval);
/* Valid period: 1..INT32_MAX. Call at least once per 2^32 clock ticks.
 * Returns elapsed periods, moves anchor by that many periods, no catch-up loop.
 * Invalid period returns 0 without modifying anchor. */
uint32_t digital_periods_due(uint32_t now, uint32_t *anchor, uint32_t period);
/* Requires deadline and now less than 2^31 ticks apart. */
bool digital_deadline_reached(uint32_t now, uint32_t deadline);

typedef enum {
    DIGITAL_BUTTON_NONE = 0,
    DIGITAL_BUTTON_PRESSED,
    DIGITAL_BUTTON_RELEASED
} digital_button_event_t;

typedef struct {
    bool stable;
    bool candidate;
    uint32_t candidate_since;
} digital_debounce_t;

void digital_debounce_init(digital_debounce_t *button, bool pressed, uint32_t now);
digital_button_event_t digital_debounce_update(digital_debounce_t *button,
                                               bool pressed, uint32_t now,
                                               uint32_t stable_ms);

#define DIGITAL_QUEUE_CAPACITY 64u
typedef struct {
    uint8_t data[DIGITAL_QUEUE_CAPACITY];
    uint8_t read_index;
    uint8_t write_index;
    uint8_t count;
} digital_byte_queue_t;

void digital_queue_init(volatile digital_byte_queue_t *queue);
bool digital_queue_push(volatile digital_byte_queue_t *queue, uint8_t byte);
bool digital_queue_pop(volatile digital_byte_queue_t *queue, uint8_t *byte);

typedef enum {
    DIGITAL_CMD_LED = 1,
    DIGITAL_CMD_PERIOD,
    DIGITAL_CMD_PWM,
    DIGITAL_CMD_STATUS,
    DIGITAL_CMD_STALL
} digital_command_kind_t;

typedef struct {
    digital_command_kind_t kind;
    uint32_t value;
} digital_command_t;

/* Strict ASCII grammar, case-sensitive, no extra spaces or sign:
 * LED 0|1; PERIOD 20..5000; PWM 0..100; STATUS; STALL.
 * Input is length-delimited, need not have a trailing NUL. Failure leaves out
 * unchanged. STALL is parsed but must be explicitly enabled only for L11.
 */
bool digital_parse_command(const char *text, size_t length, digital_command_t *out);

#define DIGITAL_LINE_CAPACITY 48u /* 47 content bytes + trailing NUL */
typedef enum {
    DIGITAL_LINE_NONE = 0,
    DIGITAL_LINE_COMMAND,
    DIGITAL_LINE_INVALID,
    DIGITAL_LINE_OVERLONG
} digital_line_result_t;

typedef struct {
    char data[DIGITAL_LINE_CAPACITY];
    uint8_t length;
    digital_line_result_t discard_reason;
} digital_line_parser_t;

void digital_line_init(digital_line_parser_t *parser);
/* CR and LF each terminate a line; empty lines (including LF after CR) ignored.
 * Invalid/overlong lines are discarded through their delimiter, never executed
 * as truncated commands. Only COMMAND modifies out. */
digital_line_result_t digital_line_feed(digital_line_parser_t *parser,
                                        uint8_t byte, digital_command_t *out);

/* Difference modulo 65536. Caller MUST establish an actual interval <65536
 * timer ticks; the result alone cannot reveal missing wraps or missing edges. */
uint16_t digital_capture16_delta(uint16_t previous, uint16_t current);
/* period_counts is ARR+1, valid 1..65535. This intentionally excludes ARR=65535
 * because its 100% compare value (65536) does not fit a 16-bit CCR. */
bool digital_pwm_compare16(uint16_t period_counts, uint8_t percent, uint16_t *out);

typedef struct {
    uint32_t required;
    uint32_t seen;
} digital_health_t;
void digital_health_init(digital_health_t *health, uint32_t required);
void digital_health_mark(digital_health_t *health, uint32_t completed);
/* Clears seen on EVERY evaluation. required=0 is never healthy. */
bool digital_health_take_window(digital_health_t *health);

#endif
