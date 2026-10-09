#!/usr/bin/env python3
"""Native-only cold-route regression of actual L01 snippets.
Requires GCC-compatible C compiler, GNU-compatible linker gc-sections, and nm.
It does not build/link ARM firmware, model GPIO registers, or use a board.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CC = os.environ.get("CC", "gcc")


def one(blocks: list[str], prefix: str) -> str:
    matches = [block for block in blocks if block.startswith(prefix)]
    if len(matches) != 1:
        raise AssertionError(f"Expected one source block beginning {prefix!r}")
    return matches[0]


def check_variant(temporary: Path, variant: str, blocks: list[str]) -> None:
    defines = one(blocks, "#define APP_LED_PORT")
    if variant == "PB0":
        defines = (defines.replace("APP_LED_PORT GPIOC", "APP_LED_PORT GPIOB")
                   .replace("APP_LED_PIN GPIO_PIN_13", "APP_LED_PIN GPIO_PIN_0")
                   .replace("APP_LED_ON GPIO_PIN_RESET", "APP_LED_ON GPIO_PIN_SET")
                   .replace("APP_LED_OFF GPIO_PIN_SET", "APP_LED_OFF GPIO_PIN_RESET"))
    declarations = one(blocks, "volatile uint32_t probe_data")
    led_function = one(blocks, "static void led_write")
    initialization = one(blocks, "volatile uint32_t stack_probe")
    iteration = one(blocks, "HAL_GPIO_TogglePin")
    register_writes = one(blocks, "/* Selected pin high")
    fixture = '''#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
typedef struct { uint32_t BSRR; } GPIO_TypeDef;
GPIO_TypeDef mock_b, mock_c;
#define GPIOB (&mock_b)
#define GPIOC (&mock_c)
#define GPIO_PIN_0 UINT16_C(1)
#define GPIO_PIN_13 UINT16_C(8192)
#define GPIO_PIN_RESET 0u
#define GPIO_PIN_SET 1u
static GPIO_TypeDef *written_port;
static uint16_t written_pin;
static uint32_t written_level;
static void HAL_GPIO_WritePin(GPIO_TypeDef *port, uint16_t pin, uint32_t level)
{
    written_port = port; written_pin = pin; written_level = level;
}
static void HAL_GPIO_TogglePin(GPIO_TypeDef *port, uint16_t pin)
{
    written_port = port; written_pin = pin; written_level ^= 1u;
}
static void HAL_Delay(uint32_t milliseconds) { assert(milliseconds == 250u); }
'''
    source_text = (fixture + defines + "\n" + declarations + "\n" + led_function + '''
int main(void)
{
''' + initialization + '''
    assert(written_port == APP_LED_PORT && written_pin == APP_LED_PIN);
    assert(written_level == APP_LED_OFF);
    led_write(true);
    assert(written_level == APP_LED_ON);
''' + iteration + '''
    assert(written_port == APP_LED_PORT && written_pin == APP_LED_PIN);
    assert(written_level == APP_LED_OFF);
    assert(probe_bss == 1u && toggles == 1u);
''' + register_writes + '''
    assert(APP_LED_PORT->BSRR == ((uint32_t)APP_LED_PIN << 16));
    return 0;
}
''')
    for negative in (False, True):
        name = variant + ("_unused" if negative else "_referenced")
        source = temporary / (name + ".c")
        current = source_text
        if negative:
            current, count = re.subn(r"^\(void\)probe_data;[^\n]*\n", "", current, flags=re.M)
            if count != 1:
                raise AssertionError("Expected exactly one observable probe_data read")
        source.write_text(current, encoding="utf-8")
        executable = temporary / name
        command = [CC, "-std=c11", "-Wall", "-Wextra", "-Wpedantic",
                   "-Wconversion", "-Wshadow", "-Werror", "-O2",
                   "-ffunction-sections", "-fdata-sections", str(source),
                   "-Wl,--gc-sections", "-o", str(executable)]
        subprocess.run(command, check=True, text=True, capture_output=True)
        symbols = subprocess.run(["nm", str(executable)], check=True,
                                 text=True, capture_output=True).stdout
        retained = bool(re.search(r"\b[Dd] probe_data$", symbols, re.M))
        if retained == negative:
            raise AssertionError(f"Unexpected probe_data retention for {name}")
        if not negative:
            subprocess.run([str(executable)], check=True, text=True, capture_output=True)
    print(f"PASS: actual L01 {variant} init/on/toggle and BSRR-mask arithmetic in a native mock")
    print(f"PASS: {variant} native gc-sections retains referenced probe_data, drops unused control")


def check_inherited_led_calls() -> None:
    paths = ["01-debug-gpio.md", "02-input-state-machine.md",
             "03-timebase-scheduler.md", "04-uart-protocol.md",
             "11-recovery-watchdog.md"]
    count = 0
    for name in paths:
        text = (ROOT / "docs/labs" / name).read_text(encoding="utf-8")
        blocks = re.findall(r"```c\n(.*?)\n```", text, re.S)
        for code in blocks:
            calls = re.findall(r"HAL_GPIO_(?:Write|Toggle)Pin\s*\((.*?)\);", code, re.S)
            for call in calls:
                arguments = [part.strip() for part in call.split(",")]
                if arguments[:2] != ["APP_LED_PORT", "APP_LED_PIN"]:
                    raise AssertionError(f"LED port/pin branch lost in {name}: {call}")
                if len(arguments) == 3 and re.search(r"GPIO_PIN_(?:SET|RESET)", arguments[2]):
                    raise AssertionError(f"Hard-coded LED polarity in {name}: {call}")
                count += 1
    if count != 7:
        raise AssertionError(f"Expected seven owned LED write/toggle sites, found {count}")
    print(f"PASS: all {count} L01/L02/L03/L04/L11 LED sites inherit port, pin and polarity")


def main() -> None:
    check_inherited_led_calls()
    text = (ROOT / "docs/labs/01-debug-gpio.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```c\n(.*?)\n```", text, re.S)
    with tempfile.TemporaryDirectory(prefix="stm-startup-check-") as directory:
        for variant in ("PC13", "PB0"):
            check_variant(Path(directory), variant, blocks)
    print("NOTE: native mock/linker evidence only; no ARM startup, HAL or physical GPIO tested")


if __name__ == "__main__":
    main()
