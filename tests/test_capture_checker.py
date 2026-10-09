"""All data here is synthetic and tests the checker, never STM32 hardware."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from check_capture import HEADER, UINT32_MAX, validate_text  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
