#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/check_course.py
bash tests/run_digital_tests.sh
python3 tests/check_digital_transfers.py
python3 tests/check_digital_startup.py
make -C examples/host-buffering release-check
python3 -m unittest discover -s tests -p 'test_capture_checker.py'
python3 -m unittest discover -s tests -p 'test_stm32_project_checker.py'
node --test tests/state.test.cjs
python3 tests/test_build.py
python3 -m py_compile tools/check_capture.py tools/check_stm32_project.py scripts/check_course.py scripts/build_site.py
node --check site/app.js
node --check site/state.js
python3 scripts/build_site.py
python3 tests/check_site.py
node practice/timer/tests/timer.test.cjs
node practice/timer/tests/ui.test.cjs
node practice/timer/tests/boundaries.test.cjs
python3 tests/test_timer_integration.py
printf '\nPASS: host and structural checks only. ARM, physical hardware and real-browser checks are not included.\n'
