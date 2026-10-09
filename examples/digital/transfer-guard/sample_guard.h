#ifndef SAMPLE_GUARD_H
#define SAMPLE_GUARD_H

#include <stdbool.h>
#include <stdint.h>

/* HOST-ONLY learning contract. Not wired to HAL, DMA or IWDG.
 * All guard pointers must be non-null and refer to a valid object. start may
 * initialize a fresh object; other calls require start or zero initialization.
 * The caller owns synchronization and proves block validity/ownership first.
 * Time moves forward; intervals and gaps used for ordering stay < 2^31 ticks.
 * Sequence is monotonic modulo 2^32 within a run. If the producer resets on
 * START, stop acquisition and discard old delivery BEFORE resetting sequence
 * and taking the new baseline snapshot; only then begin the new stream.
 */
typedef enum {
    SAMPLE_STOPPED = 0,
    SAMPLE_WAIT_FIRST,
    SAMPLE_LIVE,
    SAMPLE_EXPIRED
} sample_state_t;

typedef struct {
    sample_state_t state;
    uint32_t started_ms;
    uint32_t last_progress_ms;
    uint32_t last_sequence;
    uint32_t first_budget_ms;
    uint32_t stale_budget_ms;
} sample_guard_t;

/* Initialize/reset all run-related tracking using an atomic current producer
 * snapshot. Budgets must each be 1..INT32_MAX; invalid budgets return false
 * without changing the old object. A successful START begins WAIT_FIRST.
 * This means a NEW run. An idempotent repeated START command during an active
 * application session must be handled as a no-op by its dispatcher, not here.
 */
bool sample_guard_start(sample_guard_t *guard, uint32_t now,
                        uint32_t latest_sequence, uint32_t first_budget_ms,
                        uint32_t stale_budget_ms);
void sample_guard_stop(sample_guard_t *guard);

/* Expiry is inclusive at the deadline and latches. No implicit recovery.
 * An uninitialized object must not be polled: use start or {0} initialization.
 */
sample_state_t sample_guard_poll(sample_guard_t *guard, uint32_t now);

/* Poll deadline BEFORE accepting a block. True only if active, still on time,
 * validated, and sequence is strictly forward modulo 2^32 by < 2^31.
 * Acceptance renews progress at now. A rejected block never renews progress.
 * Only explicit successful START may leave EXPIRED for an active state.
 */
bool sample_guard_accept(sample_guard_t *guard, uint32_t now,
                         uint32_t sequence, bool validated);

#endif
