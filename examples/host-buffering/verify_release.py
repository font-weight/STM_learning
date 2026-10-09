#!/usr/bin/env python3
"""Release validation: oracle GREEN, untouched exercise RED, both stated explicitly."""
import argparse
from pathlib import Path
import subprocess
import sys


def run(program, *args):
    return subprocess.run([str(program.resolve()), *args], check=False,
                          capture_output=True, text=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--student", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    args = parser.parse_args()
    oracle = run(args.oracle)
    sys.stdout.write(oracle.stdout)
    sys.stderr.write(oracle.stderr)
    if oracle.returncode != 0 or oracle.stdout.count("PASS ") != 7:
        print("FAIL release: reference/oracle contract suite did not pass", file=sys.stderr)
        return 1
    print("GREEN: reference/oracle passed 6 host contract tests.")
    starter = run(args.student, "initial_empty")
    expected = "Test failed: initial_empty"
    if starter.returncode != 1 or expected not in starter.stderr:
        sys.stdout.write(starter.stdout)
        sys.stderr.write(starter.stderr)
        print("FAIL release: untouched starter did not produce the expected RED. "
              "If you implemented student.c, run make exercise-check instead.", file=sys.stderr)
        return 1
    print("EXPECTED RED: initial student.c fails initial_empty (test exit 1).")
    print("PASS release package only. Student solution: incomplete. STM32 hardware: never run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
