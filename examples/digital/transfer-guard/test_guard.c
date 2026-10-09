#include "sample_guard.h"

#include <limits.h>
#include <stdio.h>

static unsigned checks;
static unsigned failures;
static const char *scenario;
#define CHECK(condition) do { \
    ++checks; \
    if (!(condition)) { \
        if (failures < 24u) \
            fprintf(stderr, "FAIL [%s] line %d: %s\n", scenario, __LINE__, #condition); \
        ++failures; \
    } \
} while (0)

static void test_first_deadline(void)
{
    scenario = "first block: before/at deadline";
    sample_guard_t g = {0};
    CHECK(sample_guard_poll(&g, 999u) == SAMPLE_STOPPED);
    CHECK(sample_guard_start(&g, 100u, 40u, 300u, 500u));
    CHECK(g.state == SAMPLE_WAIT_FIRST);
    CHECK(sample_guard_poll(&g, 399u) == SAMPLE_WAIT_FIRST);
    CHECK(sample_guard_accept(&g, 399u, 41u, true));
    CHECK(sample_guard_poll(&g, 898u) == SAMPLE_LIVE);
    CHECK(sample_guard_poll(&g, 899u) == SAMPLE_EXPIRED);

    CHECK(sample_guard_start(&g, 100u, 40u, 300u, 500u));
    CHECK(!sample_guard_accept(&g, 400u, 41u, true));
    CHECK(g.state == SAMPLE_EXPIRED);
    CHECK(!sample_guard_accept(&g, 401u, 42u, true));
    CHECK(sample_guard_poll(&g, 402u) == SAMPLE_EXPIRED);
}

static void test_progress_deadline(void)
{
    scenario = "accepted progress renews; exact deadline expires";
    sample_guard_t g = {0};
    CHECK(sample_guard_start(&g, 0u, 9u, 300u, 500u));
    CHECK(sample_guard_accept(&g, 100u, 10u, true));
    CHECK(sample_guard_accept(&g, 599u, 11u, true));
    CHECK(g.last_progress_ms == 599u);
    CHECK(sample_guard_poll(&g, 1098u) == SAMPLE_LIVE);
    CHECK(!sample_guard_accept(&g, 1099u, 12u, true));
    CHECK(g.state == SAMPLE_EXPIRED);
    CHECK(g.last_sequence == 11u && g.last_progress_ms == 599u);
}

static void test_rejected_blocks(void)
{
    scenario = "invalid, duplicate, old: no renewal";
    sample_guard_t g = {0};
    CHECK(sample_guard_start(&g, 0u, 100u, 300u, 500u));
    CHECK(!sample_guard_accept(&g, 10u, 100u, true));
    CHECK(!sample_guard_accept(&g, 20u, 99u, true));
    CHECK(!sample_guard_accept(&g, 30u, 101u, false));
    CHECK(g.state == SAMPLE_WAIT_FIRST && g.last_sequence == 100u);
    CHECK(sample_guard_accept(&g, 100u, 101u, true));
    CHECK(!sample_guard_accept(&g, 200u, 101u, true));
    CHECK(!sample_guard_accept(&g, 300u, 102u, false));
    CHECK(!sample_guard_accept(&g, 400u, 100u, true));
    CHECK(g.last_sequence == 101u && g.last_progress_ms == 100u);
    CHECK(sample_guard_poll(&g, 599u) == SAMPLE_LIVE);
    CHECK(sample_guard_poll(&g, 600u) == SAMPLE_EXPIRED);
}

static void test_restart(void)
{
    scenario = "START discards old progress and producer baseline";
    sample_guard_t g = {0};
    CHECK(sample_guard_start(&g, 0u, 10u, 300u, 500u));
    CHECK(sample_guard_accept(&g, 100u, 11u, true));
    /* Producer reached 20 while stopped/elsewhere; this is the new snapshot. */
    sample_guard_stop(&g);
    CHECK(sample_guard_poll(&g, 800u) == SAMPLE_STOPPED);
    CHECK(!sample_guard_accept(&g, 801u, 21u, true));
    CHECK(sample_guard_start(&g, 1000u, 20u, 300u, 500u));
    CHECK(g.state == SAMPLE_WAIT_FIRST);
    CHECK(!sample_guard_accept(&g, 1001u, 11u, true));
    CHECK(!sample_guard_accept(&g, 1100u, 20u, true));
    CHECK(sample_guard_poll(&g, 1299u) == SAMPLE_WAIT_FIRST);
    CHECK(sample_guard_poll(&g, 1300u) == SAMPLE_EXPIRED);
    /* Explicit new START is the recovery action, not an arriving late block. */
    CHECK(sample_guard_start(&g, 2000u, 21u, 300u, 500u));
    CHECK(sample_guard_accept(&g, 2100u, 22u, true));
    CHECK(g.state == SAMPLE_LIVE);
    /* Restart directly from LIVE must also reset first-sample tracking. */
    CHECK(sample_guard_start(&g, 2200u, 30u, 300u, 500u));
    CHECK(sample_guard_poll(&g, 2499u) == SAMPLE_WAIT_FIRST);
    CHECK(sample_guard_poll(&g, 2500u) == SAMPLE_EXPIRED);
    /* A producer may restart numbering after its old delivery is purged.
       The guard is given the NEW baseline; it cannot prove the purge itself. */
    CHECK(sample_guard_start(&g, 3000u, 0u, 300u, 500u));
    CHECK(!sample_guard_accept(&g, 3001u, 0u, true));
    CHECK(sample_guard_accept(&g, 3100u, 1u, true));
}

static void test_tick_wrap(void)
{
    scenario = "time wrap has the same relative trace";
    const uint32_t origin = UINT32_MAX - 99u;
    sample_guard_t g = {0};
    CHECK(sample_guard_start(&g, origin, 40u, 300u, 500u));
    CHECK(sample_guard_poll(&g, origin + 299u) == SAMPLE_WAIT_FIRST);
    CHECK(sample_guard_poll(&g, origin + 300u) == SAMPLE_EXPIRED);
    CHECK(sample_guard_start(&g, origin, 40u, 300u, 500u));
    CHECK(sample_guard_accept(&g, origin + 50u, 41u, true));
    CHECK(sample_guard_poll(&g, origin + 549u) == SAMPLE_LIVE);
    CHECK(sample_guard_poll(&g, origin + 550u) == SAMPLE_EXPIRED);
}

static void test_sequence_wrap(void)
{
    scenario = "sequence wrap; zero is a usable sequence";
    sample_guard_t g = {0};
    CHECK(sample_guard_start(&g, 0u, UINT32_MAX - 1u, 300u, 500u));
    CHECK(sample_guard_accept(&g, 10u, UINT32_MAX, true));
    CHECK(sample_guard_accept(&g, 20u, 0u, true));
    CHECK(!sample_guard_accept(&g, 30u, UINT32_MAX, true));
    CHECK(!sample_guard_accept(&g, 40u, 0u, true));
    CHECK(!sample_guard_accept(&g, 50u, UINT32_C(0x80000000), true));
    CHECK(sample_guard_accept(&g, 60u, 3u, true)); /* skip is not automatically invalid */
    CHECK(g.last_sequence == 3u && g.last_progress_ms == 60u);
}

static void test_changed_condition(void)
{
    scenario = "independent transfer: budgets 180/420, not magic constants";
    sample_guard_t g = {0};
    CHECK(sample_guard_start(&g, 1000u, 8u, 180u, 420u));
    CHECK(sample_guard_poll(&g, 1179u) == SAMPLE_WAIT_FIRST);
    CHECK(!sample_guard_accept(&g, 1180u, 9u, true));
    CHECK(g.state == SAMPLE_EXPIRED);
    CHECK(sample_guard_start(&g, 2000u, 8u, 180u, 420u));
    CHECK(sample_guard_accept(&g, 2100u, 9u, true));
    CHECK(sample_guard_poll(&g, 2519u) == SAMPLE_LIVE);
    CHECK(sample_guard_poll(&g, 2520u) == SAMPLE_EXPIRED);
}

static bool same_guard(const sample_guard_t *a, const sample_guard_t *b)
{
    /* Compare fields, not padding bytes. */
    return a->state == b->state && a->started_ms == b->started_ms &&
        a->last_progress_ms == b->last_progress_ms &&
        a->last_sequence == b->last_sequence &&
        a->first_budget_ms == b->first_budget_ms &&
        a->stale_budget_ms == b->stale_budget_ms;
}

static void test_configuration(void)
{
    scenario = "invalid configuration cannot partly reset a run";
    sample_guard_t g = {0};
    CHECK(sample_guard_start(&g, 50u, 7u, 300u, 500u));
    CHECK(sample_guard_accept(&g, 75u, 8u, true));
    const sample_guard_t before = g;
    CHECK(!sample_guard_start(&g, 100u, 9u, 0u, 500u));
    CHECK(same_guard(&g, &before));
    CHECK(!sample_guard_start(&g, 100u, 9u, 300u, 0u));
    CHECK(same_guard(&g, &before));
    CHECK(!sample_guard_start(&g, 100u, 9u, UINT32_C(0x80000000), 500u));
    CHECK(same_guard(&g, &before));
    CHECK(!sample_guard_start(&g, 100u, 9u, 300u, UINT32_MAX));
    CHECK(same_guard(&g, &before));
    CHECK(sample_guard_start(&g, 100u, 9u, INT32_MAX, INT32_MAX));
    CHECK(sample_guard_poll(&g, 101u) == SAMPLE_WAIT_FIRST);
    CHECK(sample_guard_start(&g, 100u, 9u, 1u, 1u));
    CHECK(sample_guard_accept(&g, 100u, 10u, true));
    CHECK(sample_guard_poll(&g, 101u) == SAMPLE_EXPIRED);
}

static void test_translation_property(void)
{
    scenario = "time translation: deterministic synthetic traces";
    const uint32_t origins[] = {0u, 19u, UINT32_MAX - 399u, UINT32_MAX - 9u};
    for (unsigned i = 0u; i < sizeof origins / sizeof origins[0]; ++i) {
        sample_guard_t g = {0};
        const uint32_t t = origins[i];
        CHECK(sample_guard_start(&g, t, 500u, 300u, 500u));
        CHECK(!sample_guard_accept(&g, t + 20u, 500u, true));
        CHECK(sample_guard_accept(&g, t + 100u, 501u, true));
        CHECK(!sample_guard_accept(&g, t + 200u, 502u, false));
        CHECK(sample_guard_accept(&g, t + 250u, 503u, true));
        CHECK(sample_guard_poll(&g, t + 749u) == SAMPLE_LIVE);
        CHECK(sample_guard_poll(&g, t + 750u) == SAMPLE_EXPIRED);
        CHECK(!sample_guard_accept(&g, t + 751u, 504u, true));
    }
}

int main(void)
{
    test_first_deadline();
    test_progress_deadline();
    test_rejected_blocks();
    test_restart();
    test_tick_wrap();
    test_sequence_wrap();
    test_changed_condition();
    test_configuration();
    test_translation_property();
    if (failures != 0u) {
        fprintf(stderr, "FAIL: sample guard: %u of %u checks failed%s\n",
                failures, checks, failures > 24u ? " (first 24 shown)" : "");
        return 1;
    }
    printf("PASS: sample guard: %u checks across 9 scenarios\n", checks);
    puts("NOTE: synthetic C11 logic only; no HAL, DMA, IWDG or board is exercised.");
    return 0;
}
