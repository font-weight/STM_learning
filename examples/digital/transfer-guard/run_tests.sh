#!/usr/bin/env bash
set -euo pipefail
here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
case "${1:---student}" in
    --student) source_file="$here/student.c" ;;
    --reference) source_file="$here/reference.c" ;;
    *) printf 'Usage: bash %s [--student|--reference]\n' "$0" >&2; exit 2 ;;
esac
build="$(mktemp -d "${TMPDIR:-/tmp}/stm-sample-guard.XXXXXX")"
trap 'rm -rf "$build"' EXIT
cc="${CC:-gcc}"
common=(-std=c11 -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Werror
        -I"$here" "$source_file" "$here/test_guard.c")
"$cc" "${common[@]}" -O2 -o "$build/guard_tests"
"$build/guard_tests"
if [[ "${SANITIZE:-1}" == 1 ]]; then
    "$cc" "${common[@]}" -O1 -g -fno-omit-frame-pointer \
        -fsanitize=address,undefined -o "$build/guard_tests_sanitized"
    ASAN_OPTIONS="${ASAN_OPTIONS:-detect_leaks=0}" "$build/guard_tests_sanitized"
fi
