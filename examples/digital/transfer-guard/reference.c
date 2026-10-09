#include "sample_guard.h"

#include <limits.h>

/* REFERENCE: read after an independent attempt, not a firmware drop-in.
 * Real application state, buffer ownership and watchdog feed remain external.
 */
bool sample_guard_start(sample_guard_t *guard, uint32_t now,
                        uint32_t latest_sequence, uint32_t first_budget_ms,
                        uint32_t stale_budget_ms)
{
    if (first_budget_ms == 0u || first_budget_ms > INT32_MAX ||
        stale_budget_ms == 0u || stale_budget_ms > INT32_MAX) {
        return false;
    }
    guard->state = SAMPLE_WAIT_FIRST;
    guard->started_ms = now;
    guard->last_progress_ms = now;
    guard->last_sequence = latest_sequence;
    guard->first_budget_ms = first_budget_ms;
    guard->stale_budget_ms = stale_budget_ms;
    return true;
}

void sample_guard_stop(sample_guard_t *guard)
{
    guard->state = SAMPLE_STOPPED;
}

sample_state_t sample_guard_poll(sample_guard_t *guard, uint32_t now)
{
    uint32_t anchor;
    uint32_t budget;
    if (guard->state == SAMPLE_WAIT_FIRST) {
        anchor = guard->started_ms;
        budget = guard->first_budget_ms;
    } else if (guard->state == SAMPLE_LIVE) {
        anchor = guard->last_progress_ms;
        budget = guard->stale_budget_ms;
    } else {
        return guard->state;
    }
    if ((uint32_t)(now - anchor) >= budget) {
        guard->state = SAMPLE_EXPIRED;
    }
    return guard->state;
}

bool sample_guard_accept(sample_guard_t *guard, uint32_t now,
                         uint32_t sequence, bool validated)
{
    const sample_state_t state = sample_guard_poll(guard, now);
    if ((state != SAMPLE_WAIT_FIRST && state != SAMPLE_LIVE) || !validated) {
        return false;
    }
    const uint32_t forward = (uint32_t)(sequence - guard->last_sequence);
    if (forward == 0u || forward >= UINT32_C(0x80000000)) {
        return false;
    }
    guard->last_sequence = sequence;
    guard->last_progress_ms = now;
    guard->state = SAMPLE_LIVE;
    return true;
}
