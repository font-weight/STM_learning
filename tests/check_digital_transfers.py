#!/usr/bin/env python3
"""Host-only regressions for actual lesson snippet and transfer-test sensitivity.
No target toolchain, HAL, network, browser, or hardware access is attempted.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "examples/digital/transfer-guard"
CC = os.environ.get("CC", "gcc")
FLAGS = ["-std=c11", "-Wall", "-Wextra", "-Wpedantic", "-Wconversion",
         "-Wshadow", "-Werror", "-O2"]


def compile_run(source: Path, extra: list[Path], include: Path,
                executable: Path) -> subprocess.CompletedProcess[str]:
    build = subprocess.run([CC, *FLAGS, "-I" + str(include), str(source),
                            *(str(p) for p in extra), "-o", str(executable)],
                           text=True, capture_output=True)
    if build.returncode:
        raise AssertionError("Compile failed; this is not a detected logic mutation:\n" +
                             build.stdout + build.stderr)
    return subprocess.run([str(executable)], text=True, capture_output=True)


def check_capture_snippet(tmp: Path) -> None:
    text = (ROOT / "docs/labs/06-input-capture.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```c\n(.*?)\n```", text, re.S)
    matches = [block for block in blocks
               if block.startswith("capture_snapshot_t measured = capture_read();")]
    if len(matches) != 1:
        raise AssertionError("Expected exactly one L06 freshness snippet")
    # Compile the actual learner-facing block, with only its environment mocked.
    # This proves C logic and wrap behavior; not IRQ or physical capture timing.
    source = tmp / "capture_lesson.c"
    source.write_text('''#include "digital_helpers.h"
#include <assert.h>
#include <stdio.h>
typedef struct {
    uint32_t sequence, at_ms;
    uint16_t period_ticks;
    bool valid;
} capture_snapshot_t;
static capture_snapshot_t input;
static uint32_t tick;
static volatile bool capture_result_valid;
static volatile uint32_t capture_frequency_millihz;
static capture_snapshot_t capture_read(void) { return input; }
static uint32_t HAL_GetTick(void) { return tick; }
static bool lesson_valid(void)
{
    uint32_t now = HAL_GetTick(); /* L04 already owns this name in the loop. */
    (void)now;
''' + matches[0] + '''
    assert(capture_result_valid == (fresh && measured.valid));
    if (!capture_result_valid) assert(capture_frequency_millihz == 0u);
    return capture_result_valid;
}
int main(void)
{
    input = (capture_snapshot_t){0u, 100u, 1000u, true};
    tick = 100u;
    assert(lesson_valid());
    assert(capture_frequency_millihz == 1000000u); /* persistent main-owned result */
    /* sequence rollover zero is not 'never sampled' */
    tick = 249u;
    assert(lesson_valid());
    tick = 250u;
    assert(!lesson_valid()); /* exact 150 ms deadline */
    input = (capture_snapshot_t){1u, UINT32_MAX - 99u, 1000u, true};
    tick = 49u;
    assert(lesson_valid());
    tick = 50u;
    assert(!lesson_valid());
    input = (capture_snapshot_t){0u, 0u, 0u, false};
    tick = 0u;
    assert(!lesson_valid()); /* startup cannot divide by period zero */
    input = (capture_snapshot_t){1u, 10u, 0u, false};
    tick = 10u;
    assert(!lesson_valid()); /* first capture is not a period */
    input = (capture_snapshot_t){2u, 1234u, 1000u, true};
    const uint64_t complete_tick_cycle = UINT64_C(1) << 32;
    tick = (uint32_t)((uint64_t)input.at_ms + complete_tick_cycle);
    assert(tick == input.at_ms);
    assert(lesson_valid()); /* Deliberate negative control: full-cycle old age
                              cannot be inferred from these 32-bit inputs. */
    puts("PASS: actual L06 snippet: sequence zero, initial/first edge, deadline, tick wrap");
    puts("LIMIT: full 2^32-ms silent history aliases; explicitly outside this L06 profile");
    return 0;
}
''', encoding="utf-8")
    result = compile_run(source, [ROOT / "examples/common/digital_helpers.c"],
                         ROOT / "examples/common", tmp / "capture_lesson")
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    print(result.stdout.strip())


def check_guard_mutations(tmp: Path) -> None:
    reference = (GUARD / "reference.c").read_text(encoding="utf-8")
    mutations = [
        ("deadline addition across wrap",
         "if ((uint32_t)(now - anchor) >= budget)", "if (now >= anchor + budget)"),
        ("strict greater-than misses exact deadline",
         "if ((uint32_t)(now - anchor) >= budget)",
         "if ((uint32_t)(now - anchor) > budget)"),
        ("duplicate sequence counted as progress",
         "forward == 0u || forward >= UINT32_C(0x80000000)",
         "forward >= UINT32_C(0x80000000)"),
        ("invalid block counted as progress",
         "|| !validated)", "|| (validated && false))"),
        ("old sequence accepted",
         "forward == 0u || forward >= UINT32_C(0x80000000)", "forward == 0u"),
        ("START keeps old live state",
         "guard->state = SAMPLE_WAIT_FIRST;",
         "if (guard->state != SAMPLE_LIVE) guard->state = SAMPLE_WAIT_FIRST;"),
        ("accepted block renews from START rather than now",
         "guard->last_progress_ms = now;\n    guard->state = SAMPLE_LIVE;",
         "guard->last_progress_ms = guard->started_ms;\n    guard->state = SAMPLE_LIVE;"),
        ("late block revives expired state",
         "state != SAMPLE_WAIT_FIRST && state != SAMPLE_LIVE", "state == SAMPLE_STOPPED"),
        ("budgets hard-coded to original lab",
         "guard->first_budget_ms = first_budget_ms;\n    guard->stale_budget_ms = stale_budget_ms;",
         "guard->first_budget_ms = 300u;\n    guard->stale_budget_ms = 500u;"),
        ("accept skips deadline evaluation",
         "const sample_state_t state = sample_guard_poll(guard, now);",
         "const sample_state_t state = guard->state;"),
        ("START keeps old producer baseline",
         "guard->last_sequence = latest_sequence;", "(void)latest_sequence;"),
        ("STOPPED ages like an active wait",
         "guard->state == SAMPLE_WAIT_FIRST", "guard->state <= SAMPLE_WAIT_FIRST"),
    ]
    original = compile_run(GUARD / "reference.c", [GUARD / "test_guard.c"],
                           GUARD, tmp / "guard_reference")
    if original.returncode:
        raise AssertionError("Reference failed before mutation checks:\n" +
                             original.stdout + original.stderr)
    for number, (name, before, after) in enumerate(mutations):
        if reference.count(before) != 1:
            raise AssertionError(f"Mutation anchor is ambiguous or absent: {name}")
        mutant = tmp / f"guard_mutant_{number}.c"
        mutant.write_text(reference.replace(before, after, 1), encoding="utf-8")
        result = compile_run(mutant, [GUARD / "test_guard.c"], GUARD,
                             tmp / f"guard_mutant_{number}")
        if result.returncode == 0 or "FAIL: sample guard:" not in result.stderr:
            raise AssertionError(f"Mutation not rejected by assertions: {name}\n" +
                                 result.stdout + result.stderr)
        print("REJECTED:", name)
    print(f"PASS: all {len(mutations)} plausible guard mutations compiled and failed the contract tests")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="stm-digital-transfer-") as directory:
        temporary = Path(directory)
        check_capture_snippet(temporary)
        check_guard_mutations(temporary)


if __name__ == "__main__":
    main()
