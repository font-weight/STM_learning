#!/usr/bin/env bash
set -euo pipefail
repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
build="$(mktemp -d "${TMPDIR:-/tmp}/stm-digital-tests.XXXXXX")"
trap 'rm -rf "$build"' EXIT
cc="${CC:-gcc}"
common=(-std=c11 -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Werror
        -I"$repo/examples/common"
        "$repo/examples/common/digital_helpers.c"
        "$repo/tests/test_digital_helpers.c")
"$cc" "${common[@]}" -O2 -o "$build/digital_tests"
"$build/digital_tests"
if [[ "${SANITIZE:-1}" == 1 ]]; then
    "$cc" "${common[@]}" -O1 -g -fno-omit-frame-pointer \
        -fsanitize=address,undefined -o "$build/digital_tests_sanitized"
    # No heap allocation is used. LeakSanitizer is disabled for ptrace-based CI.
    ASAN_OPTIONS="${ASAN_OPTIONS:-detect_leaks=0}" "$build/digital_tests_sanitized"
fi

mock=(-std=c11 -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Werror
      -I"$repo/tests/mocks" -I"$repo/examples/common" -I"$repo/examples/digital"
      "$repo/examples/common/digital_helpers.c"
      "$repo/examples/digital/uart_console.c"
      "$repo/tests/test_uart_console_mock.c")
"$cc" "${mock[@]}" -O2 -o "$build/uart_mock_tests"
"$build/uart_mock_tests"
if [[ "${SANITIZE:-1}" == 1 ]]; then
    "$cc" "${mock[@]}" -O1 -g -fno-omit-frame-pointer \
        -fsanitize=address,undefined -o "$build/uart_mock_tests_sanitized"
    ASAN_OPTIONS="${ASAN_OPTIONS:-detect_leaks=0}" "$build/uart_mock_tests_sanitized"
fi
