#include "stream.h"

/*
 * Intentionally incomplete exercise, not a firmware library.
 * Implement one function at a time. Read README.md before running tests.
 */
void record_queue_init(record_queue_t *queue)
{
    /* TODO: establish empty-queue invariants; no malloc. */
    (void)queue;
}

bool record_queue_push(record_queue_t *queue, const stream_record_t *record)
{
    /* TODO: preserve FIFO order; drop newest when full. */
    (void)queue;
    (void)record;
    return false;
}

bool record_queue_pop(record_queue_t *queue, stream_record_t *record)
{
    /* TODO: an empty pop must not modify the destination. */
    (void)queue;
    (void)record;
    return false;
}

size_t stream_format_csv(char *dst, size_t capacity,
                         const stream_record_t *record)
{
    /* TODO: bounded formatting; use inttypes.h for portable uint32_t formats. */
    (void)record;
    if (capacity > 0U) {
        dst[0] = '\0';
    }
    return 0U;
}
