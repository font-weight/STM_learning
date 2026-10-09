"""Synthetic parser tests only. No generated firmware, ARM build or board test."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import random
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from check_stm32_project import (  # noqa: E402
    FLASH_BASE, RAM_BASE, RAM_SIZE, Report, inspect_elf, inspect_ioc,
    inspect_linker, main, parse_number,
)

IOC = "Mcu.CPN=STM32F103C8T6\nMxCube.Version=fixture-only\n"
LINKER = """/* Synthetic fixture; not a generated firmware linker script. */
MEMORY
{
  RAM (xrw) : ORIGIN = 0x20000000, LENGTH = 20K
  FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 64K
}
SECTIONS { .text : { *(.text*) } >FLASH }
"""


def elf_fixture() -> bytes:
    """Minimal format fixture, deliberately without section headers/debug data."""
    data = bytearray(0x204)
    data[:16] = b"\x7fELF\x01\x01\x01" + b"\0" * 9
    struct.pack_into("<HHIIIIIHHHHHH", data, 16, 2, 40, 1, FLASH_BASE + 9,
                     52, 0, 0x05000000, 52, 32, 2, 40, 0, 0)
    struct.pack_into("<IIIIIIII", data, 52, 1, 0x100, FLASH_BASE,
                     FLASH_BASE, 32, 32, 5, 4)
    struct.pack_into("<IIIIIIII", data, 84, 1, 0x200, RAM_BASE,
                     FLASH_BASE + 32, 4, 16, 6, 4)
    struct.pack_into("<II", data, 0x100, RAM_BASE + RAM_SIZE, FLASH_BASE + 9)
    data[0x108:0x10a] = b"\x70\x47"  # Format fixture only; never executed.
    return bytes(data)


def changed(data: bytes, offset: int, value: int, fmt="<I") -> bytes:
    result = bytearray(data)
    struct.pack_into(fmt, result, offset, value)
    return bytes(result)


class CheckerTests(unittest.TestCase):
    def report_for(self, inspector, value, mcu="STM32F103C8T6"):
        report = Report(mcu)
        inspector(value, report)
        return report

    def assert_status(self, report, code, fragment):
        self.assertEqual(report.exit_code, code, report.checks)
        self.assertIn(fragment, "\n".join(c.detail for c in report.checks))

    def test_ioc_exact_target_and_inventory(self):
        report = self.report_for(inspect_ioc, IOC)
        self.assert_status(report, 0, "explicitly declares")
        self.assertTrue(any(c.status == "NOT RUN" for c in report.checks))
        self.assertTrue(any(c.status == "INFO" for c in report.checks))

    def test_ioc_wrong_target(self):
        self.assert_status(self.report_for(inspect_ioc, IOC.replace("C8T6", "CBT6")),
                           1, "expected STM32F103C8T6")

    def test_ioc_family_range_not_exact_part(self):
        self.assert_status(self.report_for(inspect_ioc, "Mcu.Name=STM32F103C(8-B)Tx\n"),
                           2, "Mcu.CPN is absent")

    def test_ioc_duplicate_target_is_not_silently_overwritten(self):
        self.assert_status(self.report_for(inspect_ioc, IOC + IOC), 1, "Duplicate Mcu.CPN")

    def test_ioc_comments_do_not_establish_target(self):
        self.assert_status(self.report_for(inspect_ioc, "#" + IOC), 2, "Mcu.CPN is absent")

    def test_linker_typical_literal_regions(self):
        self.assert_status(self.report_for(inspect_linker, LINKER), 0, "65536 bytes")

    def test_linker_c8_does_not_accept_128k(self):
        self.assert_status(self.report_for(inspect_linker, LINKER.replace("64K", "128K")),
                           1, "expected 0x08000000, 65536")

    def test_linker_cb_accepts_128k(self):
        self.assert_status(self.report_for(inspect_linker, LINKER.replace("64K", "128K"),
                                          "STM32F103CBT6"), 0, "131072 bytes")

    def test_linker_wrong_origin_and_ram(self):
        for a, b in (("0x08000000", "0x08002000"), ("20K", "64K")):
            with self.subTest(b=b):
                self.assertEqual(self.report_for(inspect_linker, LINKER.replace(a, b)).exit_code, 1)

    def test_linker_numeric_spellings_and_same_line_regions(self):
        text = "MEMORY { FLASH(rx): ORIGIN=134217728,LENGTH=0x10000 RAM(xrw):ORIGIN=536870912,LENGTH=20480 }"
        self.assertEqual(self.report_for(inspect_linker, text).exit_code, 0)

    def test_linker_comments_removed(self):
        text = LINKER.replace("20K", "20K /* old RAM was 64K */")
        self.assertEqual(self.report_for(inspect_linker, "/* MEMORY { bad } */\n" + text).exit_code, 0)

    def test_linker_expressions_require_review(self):
        for expr in ("64K + 64K", "FLASH_SIZE", "(64 * 1024)", "64K garbage"):
            with self.subTest(expr=expr):
                self.assert_status(self.report_for(inspect_linker, LINKER.replace("64K", expr)),
                                   2, "non-literal")

    def test_linker_include_requires_review(self):
        self.assert_status(self.report_for(inspect_linker, 'INCLUDE "other.ld"\n' + LINKER),
                           2, "included linker files are not read")

    def test_linker_missing_or_multiple_memory_blocks(self):
        for text in ("", LINKER + LINKER, LINKER.replace("MEMORY", "memory")):
            with self.subTest(text=text[:10]):
                self.assert_status(self.report_for(inspect_linker, text), 2, "one literal MEMORY")

    def test_linker_duplicate_region(self):
        text = LINKER.replace("  FLASH", "  RAM(xrw): ORIGIN=0x20000000,LENGTH=20K\n  FLASH")
        self.assert_status(self.report_for(inspect_linker, text), 1, "Duplicate region RAM")

    def test_linker_extra_region_requires_review(self):
        text = LINKER.replace("  FLASH", "  EXTRA(rx): ORIGIN=0x80000000,LENGTH=1K\n  FLASH")
        self.assert_status(self.report_for(inspect_linker, text), 2, "Additional memory regions")

    def test_linker_unparsed_extra_region_requires_review(self):
        text = LINKER.replace("  RAM", "  EXTRA(rx): org=0x90000000,len=1K\n  RAM")
        self.assert_status(self.report_for(inspect_linker, text), 2, "Unparsed content")

    def test_number_parser_does_not_eval(self):
        self.assertEqual(parse_number("0x10000"), 65536)
        self.assertEqual(parse_number("64k;"), 65536)
        self.assertEqual(parse_number("1M"), 1048576)
        for expr in ("1 << 16", "-1", "__import__('os')", "64K+1", "1e3"):
            self.assertIsNone(parse_number(expr))

    def test_number_parser_leading_zero_is_octal(self):
        self.assertEqual(parse_number("0100000"), 32768)
        self.assertEqual(parse_number("0200000"), 65536)
        self.assertEqual(parse_number("010K"), 8192)
        self.assertEqual(parse_number("0"), 0)
        self.assertEqual(parse_number("0000"), 0)
        self.assertIsNone(parse_number("09000"))

    def test_linker_valid_octal_lengths(self):
        text = LINKER.replace("64K", "0200000").replace("20K", "050000")
        self.assertEqual(self.report_for(inspect_linker, text).exit_code, 0)
        # 0100000 is 32 KiB and must not silently be interpreted as decimal 100000.
        report = self.report_for(inspect_linker, LINKER.replace("64K", "0100000"))
        self.assert_status(report, 1, "length=32768 bytes")

    def test_number_parser_bounds_tokens_values_and_scaled_values(self):
        for value in ("9" * 5000, "0x" + "f" * 5000, "0" * 5000,
                      "4294967296", "0x100000000", "4194304K"):
            with self.subTest(prefix=value[:20]):
                self.assertIsNone(parse_number(value))
        self.assertEqual(parse_number("4294967295"), 0xffffffff)
        self.assertEqual(parse_number("0xffffffff"), 0xffffffff)

    def test_linker_oversized_number_requires_review_without_traceback(self):
        report = self.report_for(inspect_linker, LINKER.replace("64K", "9" * 5000))
        self.assert_status(report, 2, "oversized ORIGIN/LENGTH")

    def test_elf_normal_format_fixture(self):
        report = self.report_for(inspect_elf, elf_fixture())
        self.assert_status(report, 0, "Initial SP=0x20005000")
        self.assertTrue(any("does not identify Cortex-M3" in c.detail for c in report.checks))

    def test_elf_not_elf32_little_endian(self):
        for data in (b"", b"hello", changed(elf_fixture(), 4, 2, "B"),
                     changed(elf_fixture(), 5, 2, "B")):
            with self.subTest(data=data[:8]):
                self.assert_status(self.report_for(inspect_elf, data), 1, "ELF32 little-endian")

    def test_elf_not_arm_or_not_executable(self):
        for offset, value in ((18, 3), (16, 1), (40, 64)):
            with self.subTest(offset=offset):
                self.assert_status(self.report_for(inspect_elf, changed(elf_fixture(), offset, value, "<H")),
                                   1, "Expected ET_EXEC")

    def test_elf_invalid_program_header_table(self):
        for offset, value, fmt in ((28, 0, "<I"), (28, 0xfffffff0, "<I"),
                                   (42, 56, "<H"), (44, 0, "<H"), (44, 65535, "<H")):
            with self.subTest(offset=offset, value=value):
                self.assert_status(self.report_for(inspect_elf, changed(elf_fixture(), offset, value, fmt)),
                                   1, "program-header table")

    def test_elf_truncated_file_bytes(self):
        self.assert_status(self.report_for(inspect_elf, elf_fixture()[:-1]), 1, "invalid/truncated")

    def test_elf_filesz_larger_than_memsz(self):
        self.assert_status(self.report_for(inspect_elf, changed(elf_fixture(), 52 + 20, 1)),
                           1, "filesz > memsz")

    def test_elf_flash_and_ram_runtime_overflows(self):
        for offset, value in ((52 + 8, FLASH_BASE + 65530), (84 + 20, RAM_SIZE + 1)):
            with self.subTest(offset=offset):
                self.assert_status(self.report_for(inspect_elf, changed(elf_fixture(), offset, value)),
                                   1, "exceeds the selected FLASH/RAM")

    def test_elf_data_load_image_counts_toward_flash(self):
        data = changed(elf_fixture(), 84 + 12, FLASH_BASE + 65534)
        self.assert_status(self.report_for(inspect_elf, data), 1, "file-backed load range")

    def test_elf_ram_only_image_is_outside_course_baseline(self):
        data = changed(elf_fixture(), 84 + 12, RAM_BASE)
        self.assert_status(self.report_for(inspect_elf, data), 1, "no bootloader/RAM load")

    def test_elf_overlapping_load_ranges(self):
        data = changed(elf_fixture(), 84 + 12, FLASH_BASE + 8)
        self.assert_status(self.report_for(inspect_elf, data), 1, "Overlapping")

    def test_elf_flash_runtime_and_load_mismatch(self):
        data = changed(elf_fixture(), 52 + 12, FLASH_BASE + 1024)
        self.assert_status(self.report_for(inspect_elf, data), 1, "runtime and load addresses differ")

    def test_elf_no_loadable_segments(self):
        data = changed(changed(elf_fixture(), 52, 0), 84, 0)
        self.assert_status(self.report_for(inspect_elf, data), 1, "No file-backed")

    def test_elf_missing_vectors_at_flash_base(self):
        data = changed(changed(elf_fixture(), 52 + 12, FLASH_BASE + 1024), 52 + 8, FLASH_BASE + 1024)
        self.assert_status(self.report_for(inspect_elf, data), 1, "initial vectors")

    def test_elf_stack_boundaries_and_alignment(self):
        for sp in (RAM_BASE, RAM_BASE - 4, RAM_BASE + RAM_SIZE + 4, RAM_BASE + 3):
            with self.subTest(sp=sp):
                self.assert_status(self.report_for(inspect_elf, changed(elf_fixture(), 0x100, sp)),
                                   1, "Initial SP")
        self.assertEqual(self.report_for(inspect_elf, changed(elf_fixture(), 0x100, RAM_BASE + 4)).exit_code, 0)

    def test_elf_reset_thumb_bit_and_real_file_extent(self):
        for reset in (FLASH_BASE + 8, FLASH_BASE + 33, 0xffffffff, RAM_BASE + 1):
            with self.subTest(reset=reset):
                self.assert_status(self.report_for(inspect_elf, changed(elf_fixture(), 0x104, reset)),
                                   1, "Reset vector")

    def test_elf_reset_requires_executable_segment(self):
        self.assert_status(self.report_for(inspect_elf, changed(elf_fixture(), 52 + 24, 4)),
                           1, "Reset vector")

    def test_elf_entry_requires_executable_flash(self):
        self.assert_status(self.report_for(inspect_elf, changed(elf_fixture(), 24, RAM_BASE)),
                           1, "ELF entry")

    def test_elf_zero_file_bss_segment_accepted(self):
        data = changed(elf_fixture(), 84 + 16, 0)
        data = changed(data, 84 + 12, RAM_BASE)
        self.assertEqual(self.report_for(inspect_elf, data).exit_code, 0)

    def test_elf_all_prefix_truncations_and_random_headers_are_bounded(self):
        original = elf_fixture()
        for length in range(len(original)):
            self.assertNotEqual(self.report_for(inspect_elf, original[:length]).exit_code, 0)
        rng = random.Random(103)
        for _ in range(100):
            data = rng.randbytes(128)
            self.assertEqual(self.report_for(inspect_elf, data).exit_code, 1)

    def run_cli(self, *args):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = main(list(args))
        return code, stream.getvalue()

    def test_cli_missing_file_fails_and_other_scopes_not_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, output = self.run_cli("--mcu", "STM32F103C8T6", "--ioc", str(Path(tmp)/"missing.ioc"))
        self.assertEqual(code, 1)
        self.assertIn("Cannot read", output)
        self.assertIn("[NOT RUN] ELF", output)

    def test_cli_json_records_hash_and_no_global_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"board.ioc"
            path.write_text(IOC)
            before = path.read_bytes()
            code, output = self.run_cli("--mcu", "STM32F103C8T6", "--ioc", str(path), "--json")
            self.assertEqual(before, path.read_bytes())
        report = json.loads(output)
        self.assertEqual(code, 0)
        self.assertEqual(len(report["files"][0]["sha256"]), 64)
        self.assertTrue(any(c["scope"] == "ELF" and c["status"] == "NOT RUN" for c in report["checks"]))
        self.assertNotIn("pass", report)
        self.assertIn("no Generate, ARM build", report["limits"][0])

    def test_cli_non_utf8_requires_manual_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"board.ioc"
            path.write_bytes(b"\xff\xfe")
            code, output = self.run_cli("--mcu", "STM32F103C8T6", "--ioc", str(path))
        self.assertEqual(code, 2)
        self.assertIn("Not UTF-8", output)

    def test_cli_directory_is_rejected_without_opening_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, output = self.run_cli("--mcu", "STM32F103C8T6", "--ioc", tmp)
        self.assertEqual(code, 1)
        self.assertIn("not a regular file", output)

    def test_cli_oversized_literal_returns_defined_json_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"memory.ld"
            path.write_text(LINKER.replace("64K", "9" * 5000))
            code, output = self.run_cli("--mcu", "STM32F103C8T6", "--linker", str(path), "--json")
        report = json.loads(output)
        self.assertEqual(code, 2)
        self.assertTrue(any(check["status"] == "REVIEW" for check in report["checks"]))
        self.assertNotIn("Traceback", output)

    def test_cli_all_three_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = [Path(tmp)/name for name in ("board.ioc", "memory.ld", "firmware.elf")]
            paths[0].write_text(IOC)
            paths[1].write_text(LINKER)
            paths[2].write_bytes(elf_fixture())
            code, output = self.run_cli("--mcu", "STM32F103C8T6", "--ioc", str(paths[0]),
                                       "--linker", str(paths[1]), "--elf", str(paths[2]))
        self.assertEqual(code, 0, output)
        self.assertIn("not proven to belong to the same build", output)
        self.assertNotIn("[PASS]", output)


if __name__ == "__main__":
    unittest.main()
