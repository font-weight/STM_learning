#ifndef STM_LEARNING_STREAM_H
#define STM_LEARNING_STREAM_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

enum { RECORD_QUEUE_CAPACITY = 8 };

typedef struct {
    uint32_t seq;
    uint32_t t_ms;
    uint32_t n;
    uint32_t min;
    uint32_t max;
    uint32_t mean_x100;
    uint32_t freq_mHz;
    uint32_t signal_valid;
    uint32_t dropped_adc;
    uint32_t dropped_tx;
} stream_record_t;

typedef struct {
    stream_record_t records[RECORD_QUEUE_CAPACITY];
    size_t head;  /* Next write position. */
    size_t tail;  /* Next read position. */
    size_t count;
    uint32_t rejected; /* Saturates at UINT32_MAX. */
} record_queue_t;

/* All pointers must be non-null. This API is single-context, NOT ISR-safe. */
void record_queue_init(record_queue_t *queue);
/* Full: return false, preserve queued records, increment/saturate rejected. */
bool record_queue_push(record_queue_t *queue, const stream_record_t *record);
/* Empty: return false and leave *record unchanged. */
bool record_queue_pop(record_queue_t *queue, stream_record_t *record);

/*
 * Decimal CSV, exactly 10 fields in struct order, then CRLF and NUL.
 * Return bytes before NUL. Return 0 on insufficient capacity.
 * On failure, set dst[0] = '\0' if capacity > 0; never send truncated output.
 * dst may be NULL only when capacity == 0. record must be non-null.
 * Every uint32_t value is accepted here; domain validation is caller-owned.
 */
size_t stream_format_csv(char *dst, size_t capacity,
                         const stream_record_t *record);

#endif
