/* Optional answer key for test-oracle validation. Attempt student.c first.
 * Single-context queue only; this does not make ISR/main concurrency safe.
 */
#include "stream.h"
#include <inttypes.h>
#include <stdio.h>

void record_queue_init(record_queue_t *q)
{
    q->head = 0U;
    q->tail = 0U;
    q->count = 0U;
    q->rejected = 0U;
}
bool record_queue_push(record_queue_t *q, const stream_record_t *r)
{
    if (q->count == RECORD_QUEUE_CAPACITY) {
        if (q->rejected != UINT32_MAX) ++q->rejected;
        return false;
    }
    q->records[q->head] = *r;
    q->head = (q->head + 1U) % RECORD_QUEUE_CAPACITY;
    ++q->count;
    return true;
}
bool record_queue_pop(record_queue_t *q, stream_record_t *r)
{
    if (q->count == 0U) return false;
    *r = q->records[q->tail];
    q->tail = (q->tail + 1U) % RECORD_QUEUE_CAPACITY;
    --q->count;
    return true;
}
size_t stream_format_csv(char *dst, size_t cap, const stream_record_t *r)
{
    if (cap == 0U) return 0U;
    int n = snprintf(dst, cap,
        "%" PRIu32 ",%" PRIu32 ",%" PRIu32 ",%" PRIu32 ",%" PRIu32
        ",%" PRIu32 ",%" PRIu32 ",%" PRIu32 ",%" PRIu32 ",%" PRIu32 "\r\n",
        r->seq, r->t_ms, r->n, r->min, r->max, r->mean_x100,
        r->freq_mHz, r->signal_valid, r->dropped_adc, r->dropped_tx);
    if (n < 0 || (size_t)n >= cap) {
        dst[0] = '\0';
        return 0U;
    }
    return (size_t)n;
}
