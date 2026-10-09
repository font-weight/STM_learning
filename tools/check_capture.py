#!/usr/bin/env python3
"""Validate saved L10/L12 CSV; never opens a port or claims hardware provenance."""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
import re
import sys

FIELDS = (
    "seq", "t_ms", "n", "min", "max", "mean_x100", "freq_mHz",
    "signal_valid", "dropped_adc", "dropped_tx",
)
HEADER = ",".join(FIELDS)
UINT32_MAX = (1 << 32) - 1
HALF_RANGE = 1 << 31
DECIMAL = re.compile(r"[0-9]+\Z")


@dataclass
class Session:
    label: str
    rows: int = 0
    sequence_gaps: int = 0
    elapsed_device_ms: int = 0
    first: dict[str, int] | None = None
    last: dict[str, int] | None = None


@dataclass
class Report:
    sessions: list[Session] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def rows(self) -> int:
        return sum(session.rows for session in self.sessions)

    @property
    def ok(self) -> bool:
        return not self.errors and self.rows > 0


def validate_text(text: str, *, expected_n: int = 100,
                  require_no_loss: bool = False,
                  min_rows_per_session: int = 1,
                  min_device_span_ms: int = 0,
                  expected_period_ms: int | None = None,
                  period_tolerance_ms: int = 5) -> Report:
    """Validate complete text. Comments never reset state except # session=... ."""
    if not 1 <= expected_n <= UINT32_MAX:
        raise ValueError("expected_n must be a positive uint32_t")
    if min_rows_per_session < 1 or min_device_span_ms < 0:
        raise ValueError("minimum rows must be positive and minimum span nonnegative")
    if expected_period_ms is not None and not 1 <= expected_period_ms < HALF_RANGE:
        raise ValueError("expected_period_ms must be positive and below uint32 half-range")
    if period_tolerance_ms < 0:
        raise ValueError("period_tolerance_ms must be nonnegative")
    report = Report()
    current: Session | None = None
    pending_label: str | None = None
    need_header = True

    if text and not text.endswith("\n"):
        report.errors.append("file: missing final newline; capture may be truncated")
    if "\x00" in text:
        report.errors.append("file: NUL byte found; UART must not send C terminators")

    # Split only on LF. str.splitlines() also treats VT/FF and Unicode separators
    # as boundaries, which could silently turn a damaged UART row into valid data.
    for line_number, raw_line in enumerate(text.split("\n"), 1):
        line = raw_line.removesuffix("\r")
        if not line:
            continue
        if line.startswith("# session="):
            if pending_label is not None:
                report.errors.append(f"line {line_number}: previous session marker not followed by header and data")
            pending_label = line[len("# session="):].strip()
            if not pending_label:
                report.errors.append(f"line {line_number}: empty session identifier")
            current = None
            need_header = True
            continue
        if line.startswith("#"):
            continue
        if line == HEADER:
            # Repeated exact header explicitly starts a new session after data.
            if current is None or current.rows > 0:
                label = pending_label or f"session-{len(report.sessions) + 1}"
                current = Session(label)
                report.sessions.append(current)
            pending_label = None
            need_header = False
            continue
        if need_header or current is None:
            report.errors.append(f"line {line_number}: data before exact CSV header")
            continue

        parts = line.split(",")
        if len(parts) != len(FIELDS):
            report.errors.append(f"line {line_number}: expected 10 fields, got {len(parts)}")
            continue
        if not all(DECIMAL.fullmatch(part) for part in parts):
            report.errors.append(f"line {line_number}: fields must be unsigned decimal integers")
            continue
        if any(len(part) > 10 for part in parts):
            report.errors.append(f"line {line_number}: decimal field longer than uint32_t contract")
            continue
        numbers = [int(part) for part in parts]
        if any(number > UINT32_MAX for number in numbers):
            report.errors.append(f"line {line_number}: value exceeds uint32_t")
            continue
        row = dict(zip(FIELDS, numbers))
        problems: list[str] = []
        if row["n"] != expected_n:
            problems.append(f"n must be {expected_n}")
        if not 0 <= row["min"] <= row["max"] <= 4095:
            problems.append("ADC min/max out of order or range")
        if not row["min"] * 100 <= row["mean_x100"] <= row["max"] * 100:
            problems.append("mean_x100 is outside min/max")
        if row["signal_valid"] not in (0, 1):
            problems.append("signal_valid must be 0 or 1")
        elif row["signal_valid"] == 0 and row["freq_mHz"] != 0:
            problems.append("invalid frequency must be represented as freq_mHz=0")
        elif row["signal_valid"] == 1 and row["freq_mHz"] == 0:
            problems.append("valid frequency must be nonzero")

        gap = 0
        elapsed = 0
        if current.last is not None:
            previous = current.last
            delta = (row["seq"] - previous["seq"]) & UINT32_MAX
            if delta == 0:
                problems.append("duplicate sequence")
            elif delta >= HALF_RANGE:
                problems.append("sequence moved backwards; reset needs a session boundary")
            else:
                gap = delta - 1
            elapsed = (row["t_ms"] - previous["t_ms"]) & UINT32_MAX
            if elapsed >= HALF_RANGE:
                problems.append("device time moved backwards; reset needs a session boundary")
            if (expected_period_ms is not None and 0 < delta < HALF_RANGE
                    and elapsed < HALF_RANGE):
                expected_elapsed = delta * expected_period_ms
                if abs(elapsed - expected_elapsed) > period_tolerance_ms:
                    problems.append(
                        f"device cadence mismatch: seq delta {delta} expects "
                        f"{expected_elapsed} ms +/- {period_tolerance_ms}, got {elapsed}")
            for name in ("dropped_adc", "dropped_tx"):
                if row[name] < previous[name]:
                    problems.append(f"{name} decreased within a session")
        if problems:
            report.errors.append(f"line {line_number}: " + "; ".join(problems))
            continue
        if current.first is None:
            current.first = row
        current.last = row
        current.rows += 1
        current.sequence_gaps += gap
        current.elapsed_device_ms += elapsed

    if report.rows == 0:
        report.errors.append("file: no valid data rows")
    for session in report.sessions:
        if session.rows == 0:
            report.errors.append(f"session {session.label!r}: header without data")
        elif session.rows < min_rows_per_session:
            report.errors.append(f"session {session.label!r}: only {session.rows} rows; "
                                 f"need at least {min_rows_per_session}")
        if session.rows and session.elapsed_device_ms < min_device_span_ms:
            report.errors.append(f"session {session.label!r}: device span "
                                 f"{session.elapsed_device_ms} ms; need at least {min_device_span_ms}")
        if require_no_loss and session.last is not None:
            if (session.sequence_gaps or session.last["dropped_adc"]
                    or session.last["dropped_tx"]):
                report.errors.append(f"session {session.label!r}: loss present under --require-no-loss")
    if pending_label is not None or need_header and report.rows > 0:
        report.errors.append("file: session marker is not followed by a header and data")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--expected-n", type=int, default=100,
                        help="expected samples per row (default: 100)")
    parser.add_argument("--require-no-loss", action="store_true",
                        help="fail on any sequence gap or reported drop in a session")
    parser.add_argument("--min-rows", type=int, default=1,
                        help="minimum data rows in EACH session (default: 1)")
    parser.add_argument("--min-device-span-ms", type=int, default=0,
                        help="minimum first-to-last MCU time span in EACH session; not external time")
    parser.add_argument("--expected-period-ms", type=int,
                        help="optional MCU timestamp interval per sequence increment")
    parser.add_argument("--period-tolerance-ms", type=int, default=5,
                        help="allowed absolute interval error with --expected-period-ms (default: 5)")
    args = parser.parse_args(argv)
    if not 1 <= args.expected_n <= UINT32_MAX:
        parser.error("--expected-n must be a positive uint32_t")
    if args.min_rows < 1 or args.min_device_span_ms < 0:
        parser.error("--min-rows must be positive; --min-device-span-ms must be nonnegative")
    if args.expected_period_ms is not None and not 1 <= args.expected_period_ms < HALF_RANGE:
        parser.error("--expected-period-ms must be positive and below uint32 half-range")
    if args.period_tolerance_ms < 0:
        parser.error("--period-tolerance-ms must be nonnegative")
    try:
        # utf-8-sig permits a BOM added by some terminal capture tools.
        with args.capture.open(encoding="utf-8-sig", newline="") as source:
            text = source.read()
    except (OSError, UnicodeError) as error:
        print(f"FAIL: cannot read capture: {error}", file=sys.stderr)
        return 2
    report = validate_text(text, expected_n=args.expected_n,
                           require_no_loss=args.require_no_loss,
                           min_rows_per_session=args.min_rows,
                           min_device_span_ms=args.min_device_span_ms,
                           expected_period_ms=args.expected_period_ms,
                           period_tolerance_ms=args.period_tolerance_ms)
    for session in report.sessions:
        if session.last is None:
            continue
        last = session.last
        assert session.first is not None
        print(f"{session.label}: rows={session.rows}, first_seq={session.first['seq']}, "
              f"last_seq={last['seq']}, sequence_gaps={session.sequence_gaps}, "
              f"device_span_ms={session.elapsed_device_ms}, "
              f"last_dropped_adc={last['dropped_adc']}, last_dropped_tx={last['dropped_tx']}")
    for error in report.errors:
        print(f"FAIL: {error}", file=sys.stderr)
    if not report.ok:
        return 1
    print("PASS format/range/session and requested evidence checks. "
          "Gaps and reported drops may overlap; do not add them.")
    print("File validity does not prove real hardware origin, calibrated voltage, or independent timing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
