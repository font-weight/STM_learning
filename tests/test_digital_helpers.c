#include "digital_helpers.h"
#include <assert.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>

static void test_time(void)
{
    assert(!digital_elapsed(99u, 0u, 100u));
    assert(digital_elapsed(100u, 0u, 100u));
    assert(digital_elapsed(100u, 100u, 0u));
    assert(!digital_elapsed(5u, UINT32_MAX - 4u, 11u));
    assert(digital_elapsed(5u, UINT32_MAX - 4u, 10u));
    assert(!digital_deadline_reached(UINT32_MAX - 3u, 5u));
    assert(digital_deadline_reached(5u, 5u));
    assert(digital_deadline_reached(6u, 5u));
    uint32_t anchor = UINT32_MAX - 9u;
    assert(digital_periods_due(4u, &anchor, 5u) == 2u);
    assert(anchor == 0u);
    assert(digital_periods_due(5u, &anchor, 5u) == 1u);
    assert(anchor == 5u);
    assert(digital_periods_due(36u, &anchor, 10u) == 3u);
    assert(anchor == 35u);
    assert(digital_periods_due(36u, &anchor, 0u) == 0u);
    assert(digital_periods_due(36u, &anchor, UINT32_MAX) == 0u);
    assert(anchor == 35u);
    /* L03 prediction trace: complete one slot and keep the original phase. */
    anchor = UINT32_C(0xFFFFFFF0);
    assert(digital_periods_due(UINT32_C(0x10), &anchor, 25u) == 1u);
    assert(anchor == 9u);
    assert((uint32_t)(UINT32_C(0x10) - anchor) == 7u);
    assert(digital_periods_due(UINT32_C(0x21), &anchor, 25u) == 0u);
    assert(digital_periods_due(UINT32_C(0x22), &anchor, 25u) == 1u);
    assert(anchor == UINT32_C(0x22));
    anchor = UINT32_C(0xFFFFFFF0);
    assert(digital_periods_due(UINT32_C(0x42), &anchor, 25u) == 3u);
    assert(anchor == UINT32_C(0x3B));
    /* Property: adding the same modulo offset changes neither elapsed result
       nor number of due periods, even when the representation wraps. */
    for (uint32_t interval = 1u; interval < 200u; ++interval) {
        for (uint32_t elapsed = 0u; elapsed < 500u; ++elapsed) {
            const uint32_t then = UINT32_MAX - 70u;
            const uint32_t now = then + elapsed;
            assert(digital_elapsed(now, then, interval) == (elapsed >= interval));
            anchor = then;
            assert(digital_periods_due(now, &anchor, interval) == elapsed / interval);
            assert((uint32_t)(now - anchor) == elapsed % interval);
        }
    }
}

static void test_debounce(void)
{
    digital_debounce_t b;
    digital_debounce_init(&b, false, 0u);
    assert(digital_debounce_update(&b, true, 1u, 20u) == DIGITAL_BUTTON_NONE);
    assert(digital_debounce_update(&b, false, 4u, 20u) == DIGITAL_BUTTON_NONE);
    assert(digital_debounce_update(&b, true, 7u, 20u) == DIGITAL_BUTTON_NONE);
    assert(digital_debounce_update(&b, true, 26u, 20u) == DIGITAL_BUTTON_NONE);
    assert(digital_debounce_update(&b, true, 27u, 20u) == DIGITAL_BUTTON_PRESSED);
    assert(digital_debounce_update(&b, true, 1000u, 20u) == DIGITAL_BUTTON_NONE);
    assert(digital_debounce_update(&b, false, 1001u, 20u) == DIGITAL_BUTTON_NONE);
    assert(digital_debounce_update(&b, false, 1021u, 20u) == DIGITAL_BUTTON_RELEASED);
    digital_debounce_init(&b, false, UINT32_MAX - 20u);
    assert(digital_debounce_update(&b, true, UINT32_MAX - 9u, 20u) == DIGITAL_BUTTON_NONE);
    assert(digital_debounce_update(&b, true, 9u, 20u) == DIGITAL_BUTTON_NONE);
    assert(digital_debounce_update(&b, true, 10u, 20u) == DIGITAL_BUTTON_PRESSED);
    digital_debounce_init(&b, true, 0u); /* pressed at boot is state, not a new edge */
    assert(digital_debounce_update(&b, true, 100u, 20u) == DIGITAL_BUTTON_NONE);
    assert(digital_debounce_update(&b, false, 101u, 0u) == DIGITAL_BUTTON_RELEASED);
}

static void test_queue(void)
{
    struct guarded_queue {
        uint32_t before;
        digital_byte_queue_t queue;
        uint32_t after;
    } g = {UINT32_C(0xA5A5A5A5), {{0}, 0, 0, 0}, UINT32_C(0x5A5A5A5A)};
    digital_queue_init(&g.queue);
    uint8_t out = 222u;
    assert(!digital_queue_pop(&g.queue, &out) && out == 222u);
    for (unsigned round = 0; round < 1000; ++round) {
        for (unsigned i = 0; i < DIGITAL_QUEUE_CAPACITY; ++i) {
            assert(digital_queue_push(&g.queue, (uint8_t)i));
        }
        assert(g.queue.count == DIGITAL_QUEUE_CAPACITY);
        assert(!digital_queue_push(&g.queue, 99u));
        for (unsigned i = 0; i < DIGITAL_QUEUE_CAPACITY; ++i) {
            assert(digital_queue_pop(&g.queue, &out));
            assert(out == i);
        }
        assert(!digital_queue_pop(&g.queue, &out));
        /* Put the next full cycle across an index wrap. */
        assert(digital_queue_push(&g.queue, 201u));
        assert(digital_queue_pop(&g.queue, &out) && out == 201u);
    }
    assert(g.before == UINT32_C(0xA5A5A5A5));
    assert(g.after == UINT32_C(0x5A5A5A5A));
}

static void test_commands(void)
{
    struct good_case { const char *s; digital_command_kind_t kind; uint32_t value; };
    const struct good_case good[] = {
        {"LED 0", DIGITAL_CMD_LED, 0u}, {"LED 1", DIGITAL_CMD_LED, 1u},
        {"PERIOD 20", DIGITAL_CMD_PERIOD, 20u},
        {"PERIOD 5000", DIGITAL_CMD_PERIOD, 5000u},
        {"PWM 0", DIGITAL_CMD_PWM, 0u}, {"PWM 100", DIGITAL_CMD_PWM, 100u},
        {"PWM 050", DIGITAL_CMD_PWM, 50u},
        {"STATUS", DIGITAL_CMD_STATUS, 0u}, {"STALL", DIGITAL_CMD_STALL, 0u}
    };
    for (size_t i = 0; i < sizeof(good) / sizeof(good[0]); ++i) {
        digital_command_t out = {DIGITAL_CMD_STATUS, 77u};
        assert(digital_parse_command(good[i].s, strlen(good[i].s), &out));
        assert(out.kind == good[i].kind && out.value == good[i].value);
    }
    const char *bad[] = {
        "", "LED", "LED ", "LED 2", "LED -1", "LED +1", " LED 1", "LED 1 ",
        "led 1", "LED 1x", "LED 1 2", "PERIOD 19", "PERIOD 5001", "PWM 101",
        "PWM 4294967295", "PWM 4294967296", "PWM 99999999999999999999999999",
        "STATUS 1", "STATUSx", "PWM\t50", "STALL now"
    };
    for (size_t i = 0; i < sizeof(bad) / sizeof(bad[0]); ++i) {
        digital_command_t out = {DIGITAL_CMD_LED, 77u};
        assert(!digital_parse_command(bad[i], strlen(bad[i]), &out));
        assert(out.kind == DIGITAL_CMD_LED && out.value == 77u);
    }
    const char embedded_nul[] = {'L', 'E', 'D', ' ', '1', '\0', '0'};
    digital_command_t out;
    assert(!digital_parse_command(embedded_nul, sizeof(embedded_nul), &out));
    const char not_terminated[] = {'P', 'W', 'M', ' ', '5', '0'};
    assert(digital_parse_command(not_terminated, sizeof(not_terminated), &out));
    assert(out.kind == DIGITAL_CMD_PWM && out.value == 50u);
}

static digital_line_result_t feed_text(digital_line_parser_t *p, const char *s,
                                      digital_command_t *out)
{
    digital_line_result_t last = DIGITAL_LINE_NONE;
    for (size_t i = 0u; s[i] != '\0'; ++i) {
        const digital_line_result_t r = digital_line_feed(p, (uint8_t)s[i], out);
        if (r != DIGITAL_LINE_NONE) last = r;
    }
    return last;
}

static void test_lines(void)
{
    struct guarded_line {
        uint32_t before;
        digital_line_parser_t parser;
        uint32_t after;
    } g = {UINT32_C(0xA5A5A5A5), {{0}, 0, DIGITAL_LINE_NONE}, UINT32_C(0x5A5A5A5A)};
    digital_line_parser_t *p = &g.parser;
    digital_command_t cmd = {DIGITAL_CMD_STATUS, 99u};
    digital_line_init(p);
    assert(feed_text(p, "LED 1", &cmd) == DIGITAL_LINE_NONE);
    assert(digital_line_feed(p, '\r', &cmd) == DIGITAL_LINE_COMMAND);
    assert(cmd.kind == DIGITAL_CMD_LED && cmd.value == 1u);
    assert(digital_line_feed(p, '\n', &cmd) == DIGITAL_LINE_NONE);
    assert(feed_text(p, "\r\n\n", &cmd) == DIGITAL_LINE_NONE);
    assert(feed_text(p, "LED 7\n", &cmd) == DIGITAL_LINE_INVALID);
    assert(feed_text(p, "PERIOD 100\n", &cmd) == DIGITAL_LINE_COMMAND);
    /* Exactly 47 printable chars fit, the 48th enters drop-until-EOL. */
    digital_line_init(p);
    for (unsigned i = 0; i < DIGITAL_LINE_CAPACITY - 1u; ++i)
        assert(digital_line_feed(p, 'X', &cmd) == DIGITAL_LINE_NONE);
    assert(p->length == DIGITAL_LINE_CAPACITY - 1u);
    assert(p->discard_reason == DIGITAL_LINE_NONE);
    assert(digital_line_feed(p, '\n', &cmd) == DIGITAL_LINE_INVALID);
    for (unsigned i = 0; i < DIGITAL_LINE_CAPACITY; ++i)
        assert(digital_line_feed(p, 'X', &cmd) == DIGITAL_LINE_NONE);
    assert(p->discard_reason == DIGITAL_LINE_OVERLONG);
    assert(feed_text(p, "LED 1\n", &cmd) == DIGITAL_LINE_OVERLONG);
    assert(feed_text(p, "LED 0\n", &cmd) == DIGITAL_LINE_COMMAND);
    assert(cmd.kind == DIGITAL_CMD_LED && cmd.value == 0u);
    assert(feed_text(p, "LED ", &cmd) == DIGITAL_LINE_NONE);
    assert(digital_line_feed(p, 0u, &cmd) == DIGITAL_LINE_NONE);
    assert(feed_text(p, "1\n", &cmd) == DIGITAL_LINE_INVALID);
    assert(feed_text(p, "STATUS\n", &cmd) == DIGITAL_LINE_COMMAND);
    /* Deterministic byte fuzzing checks bounds and recovery, not concurrency. */
    uint32_t random = UINT32_C(0x31415926);
    for (unsigned i = 0; i < 200000u; ++i) {
        random = random * UINT32_C(1664525) + UINT32_C(1013904223);
        (void)digital_line_feed(p, (uint8_t)(random >> 24), &cmd);
        assert(p->length < DIGITAL_LINE_CAPACITY);
        assert(g.before == UINT32_C(0xA5A5A5A5));
        assert(g.after == UINT32_C(0x5A5A5A5A));
    }
    (void)digital_line_feed(p, '\n', &cmd);
    assert(feed_text(p, "STATUS\n", &cmd) == DIGITAL_LINE_COMMAND);
}

static void test_timer_math(void)
{
    assert(digital_capture16_delta(100u, 1100u) == 1000u);
    assert(digital_capture16_delta(65000u, 464u) == 1000u);
    assert(digital_capture16_delta(0u, 65535u) == 65535u);
    assert(digital_capture16_delta(65535u, 0u) == 1u);
    assert(digital_capture16_delta(100u, 100u) == 0u); /* ambiguous, not a frequency */
    for (uint32_t previous = 0u; previous <= UINT16_MAX; ++previous) {
        assert(digital_capture16_delta((uint16_t)previous,
               (uint16_t)(previous + 1000u)) == 1000u);
    }
    uint16_t compare = 123u;
    assert(!digital_pwm_compare16(0u, 50u, &compare) && compare == 123u);
    assert(!digital_pwm_compare16(1000u, 101u, &compare) && compare == 123u);
    assert(digital_pwm_compare16(1000u, 0u, &compare) && compare == 0u);
    assert(digital_pwm_compare16(1000u, 50u, &compare) && compare == 500u);
    assert(digital_pwm_compare16(1000u, 100u, &compare) && compare == 1000u);
    assert(digital_pwm_compare16(UINT16_MAX, 100u, &compare) && compare == UINT16_MAX);
    for (unsigned duty = 0u; duty <= 100u; ++duty) {
        assert(digital_pwm_compare16(1000u, (uint8_t)duty, &compare));
        assert(compare == duty * 10u);
    }
}

static void test_health(void)
{
    digital_health_t h;
    digital_health_init(&h, 3u);
    assert(!digital_health_take_window(&h));
    digital_health_mark(&h, 1u);
    assert(!digital_health_take_window(&h));
    digital_health_mark(&h, 2u); /* previous window's bit must not carry over */
    assert(!digital_health_take_window(&h));
    digital_health_mark(&h, 7u);
    assert(digital_health_take_window(&h));
    assert(!digital_health_take_window(&h));
    digital_health_init(&h, 0u);
    digital_health_mark(&h, UINT32_MAX);
    assert(!digital_health_take_window(&h));
}

int main(void)
{
    test_time();
    test_debounce();
    test_queue();
    test_commands();
    test_lines();
    test_timer_math();
    test_health();
    printf("PASS: digital helpers: time, debounce, queue, parser, capture, PWM, health\n");
    printf("RAM (host ABI): queue=%zu, parser=%zu, debounce=%zu bytes\n",
           sizeof(digital_byte_queue_t), sizeof(digital_line_parser_t),
           sizeof(digital_debounce_t));
    return 0;
}
