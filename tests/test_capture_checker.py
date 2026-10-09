"""All data here is synthetic and tests the checker, never STM32 hardware."""
from __future__ import annotations

from pathlib import Path
from contextlib import redirect_stderr, redirect_stdout
import io
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from check_capture import HEADER, UINT32_MAX, main, validate_text  # noqa: E402


def row(seq=1, t_ms=100, n=100, minimum=0, maximum=4095,
        mean=204750, freq=1000000, valid=1, adc=0, tx=0):
    return ",".join(map(str, (seq, t_ms, n, minimum, maximum, mean,
                              freq, valid, adc, tx))) + "\r\n"


def capture(*rows):
    return "# synthetic test only\r\n" + HEADER + "\r\n" + "".join(rows)


class CaptureCheckerTests(unittest.TestCase):
    def assert_bad(self, text, fragment):
        report = validate_text(text)
        self.assertFalse(report.ok)
        self.assertIn(fragment, "\n".join(report.errors))

    def test_nominal_two_rows(self):
        result = validate_text(capture(row(), row(2, 200)))
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.rows, 2)
        self.assertEqual(result.sessions[0].elapsed_device_ms, 100)

    def test_gaps_counted_not_auto_failed(self):
        result = validate_text(capture(row(), row(4, 400, tx=2)))
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.sessions[0].sequence_gaps, 2)

    def test_no_loss_gate(self):
        self.assertFalse(validate_text(capture(row(), row(3, 300)),
                                       require_no_loss=True).ok)
        self.assertFalse(validate_text(capture(row(adc=1)),
                                       require_no_loss=True).ok)
        self.assertTrue(validate_text(capture(row()), require_no_loss=True).ok)

    def test_duplicate(self):
        self.assert_bad(capture(row(), row()), "duplicate sequence")

    def test_backwards_requires_session(self):
        self.assert_bad(capture(row(8, 800), row(1, 100)), "sequence moved backwards")

    def test_arbitrary_comment_does_not_reset(self):
        self.assert_bad(capture(row(8, 800), "# status hello\n", row()),
                        "sequence moved backwards")

    def test_explicit_session_marker_and_header(self):
        text = capture(row(8, 800)) + "# session=boot-2\n" + HEADER + "\n" + row()
        result = validate_text(text)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(len(result.sessions), 2)
        self.assertEqual(result.sessions[1].label, "boot-2")

    def test_repeated_header_is_boundary(self):
        result = validate_text(capture(row(8, 800)) + HEADER + "\n" + row())
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(len(result.sessions), 2)

    def test_session_marker_requires_header(self):
        self.assert_bad(capture(row()) + "# session=2\n" + row(), "data before")

    def test_trailing_marker_rejected(self):
        self.assert_bad(capture(row()) + "# session=2\n", "not followed")

    def test_uint32_sequence_and_time_wrap(self):
        result = validate_text(capture(row(UINT32_MAX, UINT32_MAX - 49), row(0, 50)))
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.sessions[0].sequence_gaps, 0)
        self.assertEqual(result.sessions[0].elapsed_device_ms, 100)

    def test_counter_decrease(self):
        self.assert_bad(capture(row(tx=10), row(2, 200, tx=9)), "dropped_tx decreased")

    def test_counter_saturation_accepted(self):
        result = validate_text(capture(row(tx=UINT32_MAX), row(2, 200, tx=UINT32_MAX)))
        self.assertTrue(result.ok, result.errors)

    def test_adc_ranges(self):
        for kwargs in ({"maximum": 4096}, {"minimum": 3000, "maximum": 2000},
                       {"mean": 409501}, {"n": 99}):
            with self.subTest(kwargs=kwargs):
                self.assertFalse(validate_text(capture(row(**kwargs))).ok)

    def test_invalid_frequency_contract(self):
        self.assertTrue(validate_text(capture(row(freq=0, valid=0))).ok)
        for kwargs in ({"freq": 1, "valid": 0}, {"freq": 0, "valid": 1}, {"valid": 2}):
            with self.subTest(kwargs=kwargs):
                self.assertFalse(validate_text(capture(row(**kwargs))).ok)

    def test_malformed_rows(self):
        for bad in ("OK STATUS\n", "1,2,3\n", row().replace(",100,", ",-1,", 1),
                    row(seq=UINT32_MAX + 1), row().replace(",100,", ",1e2,", 1)):
            with self.subTest(bad=bad):
                self.assertFalse(validate_text(capture(bad)).ok)

    def test_excessively_long_integer_is_bounded(self):
        bad = ("9" * 5000) + row()[1:]
        self.assert_bad(capture(bad), "longer than uint32_t")

    def test_missing_final_newline(self):
        self.assert_bad(capture(row()).rstrip("\r\n"), "missing final newline")

    def test_nul(self):
        self.assert_bad(capture(row()) + "\x00\n", "NUL byte")

    def test_no_data(self):
        self.assert_bad("# metadata only\n", "no valid data")
        self.assert_bad(HEADER + "\n", "header without data")

    def test_data_without_header(self):
        self.assert_bad(row(), "data before")

    def test_device_time_backwards(self):
        self.assert_bad(capture(row(1, 200), row(2, 100)), "device time moved backwards")

    def test_duplicate_header_before_data_is_harmless(self):
        result = validate_text(HEADER + "\n" + HEADER + "\n" + row())
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(len(result.sessions), 1)

    def test_expected_n_override(self):
        result = validate_text(capture(row(n=50)), expected_n=50)
        self.assertTrue(result.ok, result.errors)

    def test_short_capture_is_not_duration_evidence(self):
        text = capture(row())
        self.assertTrue(validate_text(text).ok)
        result = validate_text(text, min_rows_per_session=600, min_device_span_ms=59000)
        self.assertFalse(result.ok)
        self.assertIn("only 1 rows", "\n".join(result.errors))
        self.assertIn("device span 0 ms", "\n".join(result.errors))

    def test_minimum_requirements_apply_to_each_session(self):
        text = capture(row(), row(2, 200)) + "# session=reset\n" + HEADER + "\n" + row()
        result = validate_text(text, min_rows_per_session=2, min_device_span_ms=100)
        self.assertFalse(result.ok)
        self.assertEqual(len(result.errors), 2)
        self.assertTrue(all("'reset'" in error for error in result.errors))

    def test_synthetic_one_minute_boundary(self):
        text = capture(*(row(seq=i, t_ms=i * 100) for i in range(1, 601)))
        result = validate_text(text, min_rows_per_session=600,
                               min_device_span_ms=59000,
                               expected_period_ms=100, require_no_loss=True)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.sessions[0].elapsed_device_ms, 59900)
        self.assertFalse(validate_text(text, min_device_span_ms=60000).ok)

    def test_cadence_handles_gaps_without_double_counting(self):
        text = capture(row(), row(4, 400, tx=2))
        self.assertTrue(validate_text(text, expected_period_ms=100).ok)
        self.assertFalse(validate_text(capture(row(), row(4, 200, tx=2)),
                                       expected_period_ms=100).ok)

    def test_cadence_tolerance_boundaries(self):
        for delta, good in ((95, True), (105, True), (94, False), (106, False), (0, False)):
            with self.subTest(delta=delta):
                self.assertEqual(validate_text(capture(row(), row(2, 100 + delta)),
                                               expected_period_ms=100).ok, good)

    def test_cadence_is_optional(self):
        text = capture(row(), row(2, 105))
        self.assertTrue(validate_text(text).ok)
        self.assertFalse(validate_text(text, expected_period_ms=100).ok)

    def test_cadence_wrap(self):
        text = capture(row(UINT32_MAX, UINT32_MAX - 49), row(0, 50))
        self.assertTrue(validate_text(text, expected_period_ms=100).ok)

    def test_replaced_unfinished_session_marker_is_error(self):
        self.assert_bad("# session=lost\n# session=next\n" + HEADER + "\n" + row(),
                        "previous session marker not followed")

    def test_strict_line_boundaries_and_whitespace(self):
        for separator in ("\v", "\f", "\r", "\x85", "\u2028", "\u2029"):
            with self.subTest(separator=repr(separator)):
                self.assertFalse(validate_text(capture(row().rstrip("\r\n") +
                                                       separator + row(2, 200))).ok)
        for line in (" " + row(), row().replace(",100,", ", 100,", 1),
                     row().rstrip("\r\n") + " \n"):
            with self.subTest(line=line):
                self.assertFalse(validate_text(capture(line)).ok)

    def test_api_argument_validation(self):
        for kwargs in ({"expected_n": 0}, {"min_rows_per_session": 0},
                       {"min_device_span_ms": -1}, {"expected_period_ms": 0},
                       {"expected_period_ms": 1 << 31}, {"period_tolerance_ms": -1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                validate_text(capture(row()), **kwargs)

    def test_cli_codes_and_preserved_carriage_returns(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capture.csv"
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                path.write_bytes(b"\xef\xbb\xbf" + capture(row()).encode())
                self.assertEqual(main([str(path)]), 0)
                self.assertEqual(main([str(path), "--min-rows", "600"]), 1)
                self.assertEqual(main([str(path), "--expected-period-ms", "100"]), 0)
                path.write_bytes(capture(row(), row(2, 200)).replace("\r\n", "\r").encode())
                self.assertEqual(main([str(path)]), 1)
                path.write_bytes(b"\xff\xfe")
                self.assertEqual(main([str(path)]), 2)
                self.assertEqual(main([str(path.with_name("missing.csv"))]), 2)

    def test_cli_invalid_thresholds(self):
        for option, value in (("--expected-n", "0"), ("--min-rows", "0"),
                              ("--min-device-span-ms", "-1"),
                              ("--expected-period-ms", "0"),
                              ("--period-tolerance-ms", "-1")):
            with self.subTest(option=option), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as stopped:
                    main(["not-opened.csv", option, value])
                self.assertEqual(stopped.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
