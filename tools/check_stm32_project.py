#!/usr/bin/env python3
"""Read-only, deliberately narrow checks for the course's STM32F103C8/CB files.

No compiler, debugger, project commands, imports from the target project, network,
or hardware are invoked. A checked file is not evidence that it was used to build
or flash any other file. See README-project-check.md for the exact scope.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
import hashlib
import json
from pathlib import Path
import re
import struct

FLASH_BASE = 0x08000000
RAM_BASE = 0x20000000
RAM_SIZE = 20 * 1024
TARGETS = {"STM32F103C8T6": 64 * 1024, "STM32F103CBT6": 128 * 1024}
MAX_INPUT = 64 * 1024 * 1024
LIMITS = (
    "File evidence only: no Generate, ARM build, flash verify or board test was run.",
    "The supplied files are not proven to belong to the same build.",
    "ELF checks do not decode instructions or prove Cortex-M3 compatibility, "
    "stack headroom, peripheral setup, device identity or safe wiring.",
)


@dataclass
class Check:
    scope: str
    status: str
    detail: str


@dataclass
class Report:
    mcu: str
    files: list[dict[str, str | int]] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)

    def add(self, scope: str, status: str, detail: str) -> None:
        self.checks.append(Check(scope, status, detail))

    @property
    def exit_code(self) -> int:
        if any(c.status == "FAIL" for c in self.checks):
            return 1
        if any(c.status == "REVIEW" for c in self.checks):
            return 2
        return 0


def in_region(address: int, size: int, base: int, capacity: int) -> bool:
    return base <= address and 0 <= size and address + size <= base + capacity


def inspect_ioc(text: str, report: Report) -> None:
    """Read the explicit CPN; family names/ranges do not identify a C8 vs CB."""
    scope = "IOC declaration"
    values: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "!")) or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        if key in values and key == "Mcu.CPN":
            report.add(scope, "FAIL", "Duplicate Mcu.CPN: resolve the ambiguous target.")
            return
        values[key] = value
    part = values.get("Mcu.CPN")
    if part is None:
        report.add(scope, "REVIEW", "Mcu.CPN is absent. Confirm the exact part in CubeMX; "
                   "a family/range in Mcu.Name is insufficient.")
    elif part.upper() != report.mcu:
        report.add(scope, "FAIL", f"Mcu.CPN={part}; expected {report.mcu}.")
    else:
        report.add(scope, "OK", f"Mcu.CPN explicitly declares {part}.")
    for key in ("MxCube.Version", "ProjectManager.FirmwarePackage"):
        if key in values:
            report.add("IOC inventory", "INFO", f"{key}={values[key]}")
    report.add(scope, "NOT RUN", "Clock, pin, SWD and generated-code checks: inspect "
               "CubeMX and the build log; this reader does not validate those settings.")


def parse_number(value: str) -> int | None:
    """Parse supported GNU ld literals; unsupported/oversized forms need review.

    A leading zero selects octal, not decimal. Bound text before int() so a
    malformed file cannot hit Python's integer-string conversion limit. Memory
    addresses/lengths outside the 32-bit course target are reviewed, not wrapped.
    """
    value = value.strip().rstrip(";").strip()
    if len(value) > 64:
        return None
    match = re.fullmatch(r"(0[xX][0-9a-fA-F]+|[0-9]+)([kKmM]?)", value)
    if not match:
        return None
    number, suffix = match.groups()
    if number.lower().startswith("0x"):
        base = 16
    elif len(number) > 1 and number.startswith("0"):
        if any(digit not in "01234567" for digit in number):
            return None
        base = 8
    else:
        base = 10
    result = int(number, base) * {"": 1, "k": 1024, "m": 1024 * 1024}[suffix.lower()]
    return result if result <= 0xffffffff else None


def inspect_linker(text: str, report: Report) -> None:
    """Only literal MEMORY declarations; never evaluate linker expressions."""
    scope = "Linker declaration"
    text = re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.S)
    if re.search(r"\bINCLUDE\b", text):
        report.add(scope, "REVIEW", "INCLUDE is present; included linker files are not read.")
    blocks = re.findall(r"\bMEMORY\s*\{([^{}]*)\}", text, flags=re.S)
    if len(blocks) != 1:
        report.add(scope, "REVIEW", "Expected one literal MEMORY block; review the linker script.")
        return
    region_start = r"[A-Za-z_]\w*\s*(?:\([^)]*\))?\s*:\s*ORIGIN\s*="
    pattern = (r"([A-Za-z_]\w*)\s*(?:\([^)]*\))?\s*:\s*ORIGIN\s*=\s*"
               r"([^,]+),\s*LENGTH\s*=\s*(.+?)(?=\s+" + region_start + r"|\Z)")
    regions: dict[str, tuple[int | None, int | None]] = {}
    matches = list(re.finditer(pattern, blocks[0], flags=re.S))
    remainder = blocks[0]
    for match in reversed(matches):
        remainder = remainder[:match.start()] + remainder[match.end():]
    if remainder.strip(" ;\t\r\n"):
        report.add(scope, "REVIEW", "Unparsed content in MEMORY; only the documented literal "
                   "ORIGIN/LENGTH syntax is supported.")
    for match in matches:
        name, origin, length = match.groups()
        if name in regions:
            report.add(scope, "FAIL", f"Duplicate region {name}.")
            return
        regions[name] = (parse_number(origin), parse_number(length))
    expected = {"FLASH": (FLASH_BASE, TARGETS[report.mcu]), "RAM": (RAM_BASE, RAM_SIZE)}
    for name, (base, length) in expected.items():
        actual = regions.get(name)
        if actual is None or None in actual:
            report.add(scope, "REVIEW", f"{name}: missing, non-literal or oversized ORIGIN/LENGTH; "
                       "review manually rather than changing a valid script to fit this checker.")
        elif actual != (base, length):
            report.add(scope, "FAIL", f"{name}: found origin=0x{actual[0]:08x}, "
                       f"length={actual[1]} bytes; expected 0x{base:08x}, {length} bytes.")
        else:
            report.add(scope, "OK", f"{name}: origin=0x{base:08x}, length={length} bytes.")
    if set(regions) - set(expected):
        report.add(scope, "REVIEW", "Additional memory regions are outside the course baseline: "
                   + ", ".join(sorted(set(regions) - set(expected))))
    report.add(scope, "NOT RUN", "Actual linker selection and section rules: check the link "
               "command/map. This reads declarations only.")


def inspect_elf(data: bytes, report: Report) -> None:
    """Inspect ordinary ELF32 little-endian executable PT_LOAD records.

The normal course image starts at 0x08000000 without a custom bootloader.
Unusual but valid ELF layouts can be outside this intentionally narrow contract.
"""
    scope = "ELF structure"
    if len(data) < 52 or data[:7] != b"\x7fELF\x01\x01\x01":
        report.add(scope, "FAIL", "Expected ELF32 little-endian, version 1 header (52 bytes minimum).")
        return
    (kind, machine, version, entry, phoff, _shoff, _flags, ehsize,
     phsize, phnum, _shsize, _shnum, _shstr) = struct.unpack_from("<HHIIIIIHHHHHH", data, 16)
    if (kind, machine, version, ehsize) != (2, 40, 1, 52):
        report.add(scope, "FAIL", "Expected ET_EXEC, EM_ARM=40, version=1, e_ehsize=52; "
                   f"got {kind}, {machine}, {version}, {ehsize}.")
        return
    if phsize != 32 or not 1 <= phnum <= 256 or phoff < 52 or phoff + phnum * phsize > len(data):
        report.add(scope, "FAIL", "Missing, truncated or unsupported program-header table.")
        return
    report.add(scope, "OK", "ELF32 ARM little-endian executable; this does not identify Cortex-M3.")
    flash_size = TARGETS[report.mcu]
    segments = []
    for i in range(phnum):
        kind, offset, vma, lma, filesz, memsz, flags, _align = struct.unpack_from(
            "<IIIIIIII", data, phoff + i * phsize)
        if kind != 1:  # PT_LOAD
            continue
        if filesz > memsz or (filesz and offset + filesz > len(data)):
            report.add(scope, "FAIL", f"PT_LOAD[{i}]: invalid/truncated file range or filesz > memsz.")
            return
        if memsz and not (in_region(vma, memsz, FLASH_BASE, flash_size)
                          or in_region(vma, memsz, RAM_BASE, RAM_SIZE)):
            report.add("ELF placement", "FAIL", f"PT_LOAD[{i}] runtime range "
                       f"0x{vma:08x}+{memsz} exceeds the selected FLASH/RAM.")
            return
        if filesz and not in_region(lma, filesz, FLASH_BASE, flash_size):
            report.add("ELF placement", "FAIL", f"PT_LOAD[{i}] file-backed load range "
                       f"0x{lma:08x}+{filesz} is outside baseline FLASH (no bootloader/RAM load).")
            return
        if filesz and in_region(vma, memsz, FLASH_BASE, flash_size) and lma != vma:
            report.add("ELF placement", "FAIL", f"PT_LOAD[{i}]: FLASH runtime and load "
                       "addresses differ; outside the direct-Flash course baseline.")
            return
        segments.append((offset, vma, lma, filesz, memsz, flags))
    if not segments or not any(s[3] for s in segments):
        report.add(scope, "FAIL", "No file-backed PT_LOAD segments.")
        return
    # Ambiguous overlapping load images are rejected rather than selecting one.
    intervals = sorted((s[2], s[2] + s[3]) for s in segments if s[3])
    if any(right > next_left for (_, right), (next_left, _) in zip(intervals, intervals[1:])):
        report.add("ELF placement", "FAIL", "Overlapping file-backed load ranges.")
        return
    report.add("ELF placement", "OK", "PT_LOAD runtime and file-backed load ranges fit "
               f"{flash_size // 1024} KiB FLASH / 20 KiB RAM.")
    vector_segments = [s for s in segments if s[2] == FLASH_BASE and s[3] >= 8]
    if len(vector_segments) != 1 or vector_segments[0][1] != FLASH_BASE:
        report.add("ELF vectors", "FAIL", "Expected initial vectors mapped to FLASH base 0x08000000.")
        return
    sp, reset = struct.unpack_from("<II", data, vector_segments[0][0])
    if not RAM_BASE < sp <= RAM_BASE + RAM_SIZE or sp % 4:
        report.add("ELF vectors", "FAIL", f"Initial SP=0x{sp:08x}: must be word-aligned "
                   "inside RAM or exactly at its upper boundary, with space below it.")
        return
    def executable_address(address: int) -> bool:
        return any(flags & 1 and in_region(address, 2, vma, filesz)
                   for _offset, vma, _lma, filesz, _memsz, flags in segments)
    if not reset & 1 or not in_region(reset & ~1, 2, FLASH_BASE, flash_size) or not executable_address(reset & ~1):
        report.add("ELF vectors", "FAIL", f"Reset vector=0x{reset:08x}: expected Thumb bit "
                   "and an address in file-backed executable FLASH.")
        return
    if not executable_address(entry & ~1) or not in_region(entry & ~1, 2, FLASH_BASE, flash_size):
        report.add(scope, "FAIL", f"ELF entry=0x{entry:08x}: outside file-backed executable FLASH.")
        return
    report.add("ELF vectors", "OK", f"Initial SP=0x{sp:08x}; reset=0x{reset:08x}; "
               f"ELF entry=0x{entry:08x}. The CPU resets via vectors, not ELF metadata.")


def read_file(path: Path, scope: str, report: Report) -> bytes | None:
    try:
        if not path.is_file():
            report.add(scope, "FAIL", f"Cannot read {path}: not a regular file.")
            return None
        # Bound reads even if the file grows after stat; no code in it is executed.
        with path.open("rb") as stream:
            data = stream.read(MAX_INPUT + 1)
        if len(data) > MAX_INPUT:
            report.add(scope, "REVIEW", f"{path}: exceeds the {MAX_INPUT}-byte inspection limit.")
            return None
        report.files.append({"scope": scope, "path": str(path), "bytes": len(data),
                             "sha256": hashlib.sha256(data).hexdigest()})
        return data
    except OSError as exc:
        report.add(scope, "FAIL", f"Cannot read {path}: {exc.strerror or exc}.")
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mcu", required=True, choices=tuple(TARGETS))
    parser.add_argument("--ioc", type=Path, help="exact .ioc file to inspect")
    parser.add_argument("--linker", type=Path, help="linker script named in your build log")
    parser.add_argument("--elf", type=Path, help="ELF path from your successful build log")
    parser.add_argument("--json", action="store_true", help="machine-readable report on stdout")
    args = parser.parse_args(argv)
    if not any((args.ioc, args.linker, args.elf)):
        parser.error("provide at least one of --ioc, --linker or --elf")
    report = Report(args.mcu)
    for path, scope, inspector in ((args.ioc, "IOC", inspect_ioc),
                                   (args.linker, "Linker", inspect_linker),
                                   (args.elf, "ELF", inspect_elf)):
        if path is None:
            report.add(scope, "NOT RUN", "No file supplied.")
            continue
        data = read_file(path, scope, report)
        if data is None:
            continue
        if inspector is inspect_elf:
            inspect_elf(data, report)
        else:
            try:
                inspector(data.decode("utf-8-sig"), report)
            except UnicodeDecodeError:
                report.add(scope, "REVIEW", "Not UTF-8 text; inspect the file manually.")
    if args.json:
        result = asdict(report)
        result["limits"] = LIMITS
        result["exit_code"] = report.exit_code
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Declared course target: {report.mcu}")
        for item in report.files:
            print(f"FILE {item['scope']}: {item['path']} ({item['bytes']} bytes)\n  sha256={item['sha256']}")
        for check in report.checks:
            print(f"[{check.status}] {check.scope}: {check.detail}")
        print("\nScope limits:")
        for limit in LIMITS:
            print(f"- {limit}")
        print(f"Exit code {report.exit_code}: 0 = supplied checks clear; 1 = contradiction/invalid "
              "file; 2 = manual review. NOT RUN remains unverified.")
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
