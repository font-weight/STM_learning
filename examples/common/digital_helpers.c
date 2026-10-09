#include "digital_helpers.h"

#include <limits.h>
#include <string.h>

_Static_assert(DIGITAL_QUEUE_CAPACITY <= UINT8_MAX, "queue index type too small");
_Static_assert(DIGITAL_LINE_CAPACITY <= UINT8_MAX, "line length type too small");

bool digital_elapsed(uint32_t now, uint32_t then, uint32_t interval)
{
    return (uint32_t)(now - then) >= interval;
}

uint32_t digital_periods_due(uint32_t now, uint32_t *anchor, uint32_t period)
{
    if (period == 0u || period > INT32_MAX) {
        return 0u;
    }
    const uint32_t periods = (uint32_t)(now - *anchor) / period;
    *anchor += periods * period;
    return periods;
}

bool digital_deadline_reached(uint32_t now, uint32_t deadline)
{
    return (uint32_t)(now - deadline) < UINT32_C(0x80000000);
}

void digital_debounce_init(digital_debounce_t *button, bool pressed, uint32_t now)
{
    button->stable = pressed;
    button->candidate = pressed;
    button->candidate_since = now;
}

digital_button_event_t digital_debounce_update(digital_debounce_t *button,
                                               bool pressed, uint32_t now,
                                               uint32_t stable_ms)
{
    if (pressed != button->candidate) {
        button->candidate = pressed;
        button->candidate_since = now;
    }
    if (button->candidate != button->stable &&
        digital_elapsed(now, button->candidate_since, stable_ms)) {
        button->stable = button->candidate;
        return button->stable ? DIGITAL_BUTTON_PRESSED : DIGITAL_BUTTON_RELEASED;
    }
    return DIGITAL_BUTTON_NONE;
}

void digital_queue_init(volatile digital_byte_queue_t *queue)
{
    queue->read_index = 0u;
    queue->write_index = 0u;
    queue->count = 0u;
}

bool digital_queue_push(volatile digital_byte_queue_t *queue, uint8_t byte)
{
    if (queue->count == DIGITAL_QUEUE_CAPACITY) {
        return false;
    }
    queue->data[queue->write_index] = byte;
    uint8_t next = (uint8_t)(queue->write_index + 1u);
    if (next == DIGITAL_QUEUE_CAPACITY) {
        next = 0u;
    }
    queue->write_index = next;
    queue->count++;
    return true;
}

bool digital_queue_pop(volatile digital_byte_queue_t *queue, uint8_t *byte)
{
    if (queue->count == 0u) {
        return false;
    }
    *byte = queue->data[queue->read_index];
    uint8_t next = (uint8_t)(queue->read_index + 1u);
    if (next == DIGITAL_QUEUE_CAPACITY) {
        next = 0u;
    }
    queue->read_index = next;
    queue->count--;
    return true;
}

static bool parse_decimal(const char *text, size_t length, uint32_t *out)
{
    if (length == 0u) {
        return false;
    }
    uint32_t value = 0u;
    for (size_t i = 0u; i < length; ++i) {
        const unsigned char ch = (unsigned char)text[i];
        if (ch < (unsigned char)'0' || ch > (unsigned char)'9') {
            return false;
        }
        const uint32_t digit = (uint32_t)(ch - (unsigned char)'0');
        if (value > (UINT32_MAX - digit) / 10u) {
            return false;
        }
        value = value * 10u + digit;
    }
    *out = value;
    return true;
}

static bool parse_argument(const char *text, size_t length, const char *prefix,
                           size_t prefix_length, uint32_t minimum,
                           uint32_t maximum, uint32_t *value)
{
    return length > prefix_length &&
           memcmp(text, prefix, prefix_length) == 0 &&
           parse_decimal(text + prefix_length, length - prefix_length, value) &&
           *value >= minimum && *value <= maximum;
}

bool digital_parse_command(const char *text, size_t length, digital_command_t *out)
{
    digital_command_t command = { DIGITAL_CMD_STATUS, 0u };
    if (length == 6u && memcmp(text, "STATUS", 6u) == 0) {
        command.kind = DIGITAL_CMD_STATUS;
    } else if (length == 5u && memcmp(text, "STALL", 5u) == 0) {
        command.kind = DIGITAL_CMD_STALL;
    } else if (parse_argument(text, length, "LED ", 4u, 0u, 1u, &command.value)) {
        command.kind = DIGITAL_CMD_LED;
    } else if (parse_argument(text, length, "PERIOD ", 7u, 20u, 5000u, &command.value)) {
        command.kind = DIGITAL_CMD_PERIOD;
    } else if (parse_argument(text, length, "PWM ", 4u, 0u, 100u, &command.value)) {
        command.kind = DIGITAL_CMD_PWM;
    } else {
        return false;
    }
    *out = command;
    return true;
}

void digital_line_init(digital_line_parser_t *parser)
{
    parser->length = 0u;
    parser->data[0] = '\0';
    parser->discard_reason = DIGITAL_LINE_NONE;
}

digital_line_result_t digital_line_feed(digital_line_parser_t *parser,
                                        uint8_t byte, digital_command_t *out)
{
    if (byte == (uint8_t)'\r' || byte == (uint8_t)'\n') {
        if (parser->discard_reason != DIGITAL_LINE_NONE) {
            const digital_line_result_t reason = parser->discard_reason;
            digital_line_init(parser);
            return reason;
        }
        if (parser->length == 0u) {
            return DIGITAL_LINE_NONE;
        }
        const bool valid = digital_parse_command(parser->data, parser->length, out);
        digital_line_init(parser);
        return valid ? DIGITAL_LINE_COMMAND : DIGITAL_LINE_INVALID;
    }
    if (parser->discard_reason != DIGITAL_LINE_NONE) {
        return DIGITAL_LINE_NONE;
    }
    if (byte < 32u || byte > 126u) {
        parser->discard_reason = DIGITAL_LINE_INVALID;
        return DIGITAL_LINE_NONE;
    }
    if (parser->length >= DIGITAL_LINE_CAPACITY - 1u) {
        parser->discard_reason = DIGITAL_LINE_OVERLONG;
        return DIGITAL_LINE_NONE;
    }
    parser->data[parser->length] = (char)byte;
    parser->length++;
    parser->data[parser->length] = '\0';
    return DIGITAL_LINE_NONE;
}

uint16_t digital_capture16_delta(uint16_t previous, uint16_t current)
{
    return (uint16_t)(current - previous);
}

bool digital_pwm_compare16(uint16_t period_counts, uint8_t percent, uint16_t *out)
{
    if (period_counts == 0u || percent > 100u) {
        return false;
    }
    *out = (uint16_t)(((uint32_t)period_counts * percent) / 100u);
    return true;
}

void digital_health_init(digital_health_t *health, uint32_t required)
{
    health->required = required;
    health->seen = 0u;
}

void digital_health_mark(digital_health_t *health, uint32_t completed)
{
    health->seen |= completed;
}

bool digital_health_take_window(digital_health_t *health)
{
    const bool complete = health->required != 0u &&
                          (health->seen & health->required) == health->required;
    health->seen = 0u;
    return complete;
}
