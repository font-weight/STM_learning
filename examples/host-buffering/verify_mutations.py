#!/usr/bin/env python3
"""Opt-in test sensitivity check; all data/defects are synthetic host-only cases."""
from __future__ import annotations

import os
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
MUTATIONS = (
    ("reset_keeps_old_rejected", "initial_empty", "q->rejected = 0U;", "/* rejected is not reset */"),
    ("copy_loses_timestamp", "full_fifo", "q->records[q->head] = *r;",
     "q->records[q->head] = *r; q->records[q->head].t_ms = 0U;"),
    ("wrap_one_slot_too_early", "wraparound", "q->head = (q->head + 1U) % RECORD_QUEUE_CAPACITY;",
     "q->head = (q->head + 1U) % (RECORD_QUEUE_CAPACITY - 1U);"),
    ("pop_reads_newest", "full_fifo", "*r = q->records[q->tail];",
     "*r = q->records[(q->head + RECORD_QUEUE_CAPACITY - 1U) % RECORD_QUEUE_CAPACITY];"),
    ("drop_counter_wraps", "drop_saturation", "if (q->rejected != UINT32_MAX) ++q->rejected;",
     "++q->rejected;"),
    ("truncated_csv_accepted", "csv_limits", "if (n < 0 || (size_t)n >= cap)", "if (n < 0)"),
)


def invoke(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, timeout=30, check=False)


def main() -> int:
    original = (ROOT / "reference/stream_reference.c").read_text(encoding="utf-8")
    compiler = shlex.split(os.environ.get("CC", "cc"))
    flags = shlex.split(os.environ.get("CFLAGS", "-std=c11 -O0 -g -Wall -Wextra -Werror -Wpedantic"))
    with tempfile.TemporaryDirectory(prefix="stream-mutants-") as scratch:
        directory = Path(scratch)
        for name, test, old, new in (("unmodified_reference", "", "", ""), *MUTATIONS):
            if old and original.count(old) != 1:
                print(f"FAIL harness: {name}: mutation anchor changed; review the script")
                return 1
            source = directory / f"{name}.c"
            binary = directory / name
            source.write_text(original.replace(old, new, 1) if old else original, encoding="utf-8")
            built = invoke([*compiler, *flags, "-I", str(ROOT), str(source),
                            str(ROOT / "test_stream.c"), "-o", str(binary)])
            if built.returncode != 0:
                print(f"FAIL harness: {name} did not compile; this is not a caught defect")
                print(built.stderr)
                return 1
            result = invoke([str(binary), *([test] if test else [])])
            if not old:
                if result.returncode != 0:
                    print("FAIL harness: unmodified reference must pass before mutants run")
                    print(result.stdout + result.stderr)
                    return 1
                print("PASS unmodified reference")
            elif result.returncode == 1 and f"Test failed: {test}" in result.stderr:
                print(f"CAUGHT {name} by {test}")
            else:
                print(f"FAIL sensitivity: {name}: expected assertion failure, exit={result.returncode}")
                print(result.stdout + result.stderr)
                return 1
    print(f"PASS sensitivity: {len(MUTATIONS)} deliberate host defects rejected. No STM32 tested.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.TimeoutExpired) as error:
        raise SystemExit(f"FAIL harness: {error}") from error
