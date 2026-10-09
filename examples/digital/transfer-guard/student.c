#include "sample_guard.h"

/* Learner scaffold: intentionally incomplete, but warning-clean C11.
 * Edit THIS file. Do not edit test expectations to make the exercise green.
 * It is separate from the course firmware and its regression suite.
 */
bool sample_guard_start(sample_guard_t *guard, uint32_t now,
                        uint32_t latest_sequence, uint32_t first_budget_ms,
                        uint32_t stale_budget_ms)
{
    /* TODO 1: reject invalid budgets without mutation; reset one run. */
    (void)guard;
    (void)now;
    (void)latest_sequence;
    (void)first_budget_ms;
    (void)stale_budget_ms;
    return false;
}

void sample_guard_stop(sample_guard_t *guard)
{
    /* One completed transition: STOP does not mean a failing sensor. */
    guard->state = SAMPLE_STOPPED;
}

sample_state_t sample_guard_poll(sample_guard_t *guard, uint32_t now)
{
    /* TODO 2: select the correct anchor/budget, then latch an expired run. */
    (void)now;
    return guard->state;
}

bool sample_guard_accept(sample_guard_t *guard, uint32_t now,
                         uint32_t sequence, bool validated)
{
    /* TODO 3: deadline, block validity, sequence order, then commit progress. */
    (void)guard;
    (void)now;
    (void)sequence;
    (void)validated;
    return false;
}
