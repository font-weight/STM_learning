#include "stream.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define REQUIRE(expr) do { \
    if (!(expr)) { \
        fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #expr); \
        return 1; \
    } \
} while (0)

static stream_record_t sample(uint32_t seq)
{
    stream_record_t result = {
        seq, 100U, 100U, 0U, 4095U, 204750U, 1000000U, 1U, 0U, 0U
    };
    return result;
}

static bool same_record(const stream_record_t *a, const stream_record_t *b)
{
    return a->seq == b->seq && a->t_ms == b->t_ms && a->n == b->n
        && a->min == b->min && a->max == b->max
        && a->mean_x100 == b->mean_x100 && a->freq_mHz == b->freq_mHz
        && a->signal_valid == b->signal_valid
        && a->dropped_adc == b->dropped_adc && a->dropped_tx == b->dropped_tx;
}

static int test_initial_empty(void)
{
    record_queue_t q;
    /* Ensure init really sets state, not just depends on static zeroing. */
    memset(&q, 0xA5, sizeof q);
    record_queue_init(&q);
    REQUIRE(q.head == 0U && q.tail == 0U && q.count == 0U);
    REQUIRE(q.rejected == 0U);
    stream_record_t out = sample(77U);
    REQUIRE(!record_queue_pop(&q, &out));
    stream_record_t unchanged = sample(77U);
    REQUIRE(same_record(&out, &unchanged));
    return 0;
}

static int test_full_fifo(void)
{
    record_queue_t q;
    record_queue_init(&q);
    for (uint32_t i = 0U; i < RECORD_QUEUE_CAPACITY; ++i) {
        stream_record_t in = sample(i);
        in.dropped_tx = i + 10U;
        REQUIRE(record_queue_push(&q, &in));
    }
    REQUIRE(q.count == RECORD_QUEUE_CAPACITY);
    stream_record_t rejected = sample(999U);
    REQUIRE(!record_queue_push(&q, &rejected));
    REQUIRE(q.rejected == 1U);
    REQUIRE(q.count == RECORD_QUEUE_CAPACITY);
    for (uint32_t i = 0U; i < RECORD_QUEUE_CAPACITY; ++i) {
        stream_record_t out = {0};
        REQUIRE(record_queue_pop(&q, &out));
        stream_record_t expected = sample(i);
        expected.dropped_tx = i + 10U;
        REQUIRE(same_record(&out, &expected));
    }
    REQUIRE(q.count == 0U);
    stream_record_t untouched = sample(123U);
    REQUIRE(!record_queue_pop(&q, &untouched));
    REQUIRE(untouched.seq == 123U);

    /* Producer may reuse its local source as soon as push returns. */
    stream_record_t source = {17U, 23U, 29U, 31U, 37U, 41U, 43U, 47U, 53U, 59U};
    stream_record_t copied = source;
    stream_record_t copied_out = {0};
    REQUIRE(record_queue_push(&q, &source));
    memset(&source, 0xA5, sizeof source);
    REQUIRE(record_queue_pop(&q, &copied_out));
    REQUIRE(same_record(&copied_out, &copied));
    /* Reset a nonempty used queue; keep this here so initial_empty needs only
     * init + empty-pop, as required by the staged student exercise. */
    REQUIRE(record_queue_push(&q, &copied));
    q.rejected = 17U;
    record_queue_init(&q);
    REQUIRE(q.head == 0U && q.tail == 0U && q.count == 0U);
    REQUIRE(q.rejected == 0U);
    REQUIRE(!record_queue_pop(&q, &copied_out));
    REQUIRE(same_record(&copied_out, &copied));
    return 0;
}

static int test_wraparound(void)
{
    record_queue_t q;
    record_queue_init(&q);
    uint32_t next_in = 0U;
    uint32_t next_out = 0U;
    /* Repeatedly fill, consume three, and refill: head/tail cross the end. */
    for (unsigned round = 0U; round < 1000U; ++round) {
        while (q.count < RECORD_QUEUE_CAPACITY) {
            stream_record_t in = sample(next_in++);
            REQUIRE(record_queue_push(&q, &in));
        }
        for (unsigned i = 0U; i < 3U; ++i) {
            stream_record_t out = {0};
            REQUIRE(record_queue_pop(&q, &out));
            REQUIRE(out.seq == next_out++);
        }
        REQUIRE(q.head < RECORD_QUEUE_CAPACITY);
        REQUIRE(q.tail < RECORD_QUEUE_CAPACITY);
        REQUIRE(q.count == RECORD_QUEUE_CAPACITY - 3U);
    }
    while (q.count != 0U) {
        stream_record_t out = {0};
        REQUIRE(record_queue_pop(&q, &out));
        REQUIRE(out.seq == next_out++);
    }
    REQUIRE(next_in == next_out);
    REQUIRE(q.rejected == 0U);

    /* A deliberately different model: shift a small array, no ring indices.
     * Fixed seed makes mixed full/empty/interleaving failures reproducible.
     * Synthetic data only; neither scheduling nor ISR concurrency is modeled.
     */
    stream_record_t model[RECORD_QUEUE_CAPACITY];
    size_t model_count = 0U;
    uint32_t model_rejected = 0U;
    uint32_t random_state = 0xB10E1234U;
    for (uint32_t step = 0U; step < 4096U; ++step) {
        random_state = random_state * 1664525U + 1013904223U;
        if ((random_state >> 30) != 0U) {
            stream_record_t in = sample(step);
            in.t_ms = random_state;
            bool expected = model_count < RECORD_QUEUE_CAPACITY;
            REQUIRE(record_queue_push(&q, &in) == expected);
            if (expected) {
                model[model_count++] = in;
            } else {
                ++model_rejected;
            }
        } else {
            stream_record_t out = sample(0xDEADBEEFU);
            stream_record_t expected = model_count > 0U ? model[0] : out;
            REQUIRE(record_queue_pop(&q, &out) == (model_count > 0U));
            REQUIRE(same_record(&out, &expected));
            if (model_count > 0U) {
                --model_count;
                for (size_t i = 0U; i < model_count; ++i) model[i] = model[i + 1U];
            }
        }
        REQUIRE(q.head < RECORD_QUEUE_CAPACITY && q.tail < RECORD_QUEUE_CAPACITY);
        REQUIRE(q.count == model_count && q.rejected == model_rejected);
    }
    while (model_count > 0U) {
        stream_record_t out = {0};
        REQUIRE(record_queue_pop(&q, &out));
        REQUIRE(same_record(&out, &model[0]));
        --model_count;
        for (size_t i = 0U; i < model_count; ++i) model[i] = model[i + 1U];
    }
    REQUIRE(q.count == 0U);
    return 0;
}

static int test_drop_saturation(void)
{
    record_queue_t q;
    record_queue_init(&q);
    stream_record_t in = sample(1U);
    for (unsigned i = 0U; i < RECORD_QUEUE_CAPACITY; ++i) {
        REQUIRE(record_queue_push(&q, &in));
    }
    q.rejected = UINT32_MAX - 1U;
    REQUIRE(!record_queue_push(&q, &in));
    REQUIRE(q.rejected == UINT32_MAX);
    REQUIRE(!record_queue_push(&q, &in));
    REQUIRE(q.rejected == UINT32_MAX);
    return 0;
}

static int test_csv_exact(void)
{
    const char expected[] = "1,100,100,0,4095,204750,1000000,1,0,0\r\n";
    stream_record_t in = sample(1U);
    char output[128];
    size_t used = stream_format_csv(output, sizeof output, &in);
    REQUIRE(used == strlen(expected));
    REQUIRE(strcmp(output, expected) == 0);
    char exact[sizeof expected];
    REQUIRE(stream_format_csv(exact, sizeof exact, &in) == sizeof expected - 1U);
    REQUIRE(strcmp(exact, expected) == 0);
    return 0;
}

static int test_csv_limits(void)
{
    stream_record_t in = sample(1U);
    struct { unsigned char before; char data[8]; unsigned char after; } guarded;
    guarded.before = 0x5AU;
    guarded.after = 0xA5U;
    memset(guarded.data, 'x', sizeof guarded.data);
    REQUIRE(stream_format_csv(guarded.data, sizeof guarded.data, &in) == 0U);
    REQUIRE(guarded.data[0] == '\0');
    REQUIRE(guarded.before == 0x5AU && guarded.after == 0xA5U);
    REQUIRE(stream_format_csv(NULL, 0U, &in) == 0U);
    char zero_capacity = 'z';
    REQUIRE(stream_format_csv(&zero_capacity, 0U, &in) == 0U);
    REQUIRE(zero_capacity == 'z');
    char one = 'x';
    REQUIRE(stream_format_csv(&one, 1U, &in) == 0U);
    REQUIRE(one == '\0');
    /* Every uint32 field at its textual maximum: 100 digits + 9 commas + CRLF. */
    stream_record_t maximum = {
        UINT32_MAX, UINT32_MAX, UINT32_MAX, UINT32_MAX, UINT32_MAX,
        UINT32_MAX, UINT32_MAX, UINT32_MAX, UINT32_MAX, UINT32_MAX
    };
    char big[112];
    REQUIRE(stream_format_csv(big, sizeof big, &maximum) == 111U);
    REQUIRE(big[109] == '\r' && big[110] == '\n' && big[111] == '\0');
    char short_by_one[111];
    REQUIRE(stream_format_csv(short_by_one, sizeof short_by_one, &maximum) == 0U);
    REQUIRE(short_by_one[0] == '\0');
    /* All insufficient capacities, not just one selected short buffer. */
    for (size_t cap = 1U; cap < sizeof big; ++cap) {
        unsigned char guarded_output[114];
        memset(guarded_output, 0xA5, sizeof guarded_output);
        REQUIRE(stream_format_csv((char *)&guarded_output[1], cap, &maximum) == 0U);
        REQUIRE(guarded_output[0] == 0xA5U && guarded_output[1] == 0U);
        for (size_t i = cap + 1U; i < sizeof guarded_output; ++i) {
            REQUIRE(guarded_output[i] == 0xA5U);
        }
    }
    return 0;
}

typedef int (*test_fn)(void);
static const struct { const char *name; test_fn run; } cases[] = {
    {"initial_empty", test_initial_empty},
    {"full_fifo", test_full_fifo},
    {"wraparound", test_wraparound},
    {"drop_saturation", test_drop_saturation},
    {"csv_exact", test_csv_exact},
    {"csv_limits", test_csv_limits}
};

int main(int argc, char **argv)
{
    const size_t count = sizeof cases / sizeof cases[0];
    if (argc == 2 && strcmp(argv[1], "--list") == 0) {
        for (size_t i = 0U; i < count; ++i) {
            puts(cases[i].name);
        }
        return 0;
    }
    if (argc > 2) {
        fprintf(stderr, "Usage: %s [test_name|--list]\n", argv[0]);
        return 2;
    }
    unsigned ran = 0U;
    for (size_t i = 0U; i < count; ++i) {
        if (argc == 2 && strcmp(argv[1], cases[i].name) != 0) {
            continue;
        }
        ++ran;
        if (cases[i].run() != 0) {
            fprintf(stderr, "Test failed: %s\n", cases[i].name);
            return 1;
        }
        printf("PASS %s\n", cases[i].name);
    }
    if (ran == 0U) {
        fputs("Unknown test name\n", stderr);
        return 2;
    }
    puts("PASS host contracts only; no STM32 hardware was tested.");
    return 0;
}
