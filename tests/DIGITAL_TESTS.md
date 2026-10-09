# Проверки цифровой части

Из корня репозитория:

```bash
bash tests/run_digital_tests.sh
```

Нужны Bash и C11-совместимый GCC. Скрипт собирает во временную папку и удаляет её при выходе. Альтернативный компилятор: `CC=clang bash tests/run_digital_tests.sh`. Только обычный прогон: `SANITIZE=0 bash tests/run_digital_tests.sh`.

## Фактически выполнено 2026-10-09

- GCC Debian 14.2.0, `-std=c11 -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Werror -O2`: PASS
- Те же тесты с AddressSanitizer и UndefinedBehaviorSanitizer: PASS
- LeakSanitizer выключен по умолчанию через `detect_leaks=0`, поскольку окружение запуска использует ptrace; код не выделяет heap
- `bash -n` для script: PASS
- Проверка закрытия Markdown fences и существования локальных ссылок цифровых документов: PASS

## Pure-C helpers

`test_digital_helpers.c` проверяет:

- Вычитание tick через UINT32_MAX, точные границы deadline, нулевой/недопустимый период, пропущенные слоты и сохранение фазы
- Debounce с дребезгом, удержанием, отпусканием, нажатой кнопкой при старте, rollover и нулевым порогом
- FIFO full/empty, сохранение порядка, 1000 циклов заполнения/освобождения с оборачиванием индексов, охранные слова вокруг буфера
- Строгую грамматику, диапазоны, отрицательные/слишком большие числа, UINT32 overflow, пробелы/суффиксы/NUL, вход без terminating NUL
- CR/LF/CRLF, точную границу 47/48 байт, drop-until-EOL и восстановление после ошибки
- 200000 детерминированных псевдослучайных входных байт и сохранение границ памяти
- Capture modulo 65536, все начальные значения 16-битной отметки для периода 1000
- PWM 0/50/100%, все целые проценты, отказ при неверных параметрах
- Health bitmap: очистку и после успешного, и после неуспешного окна; запрещённый пустой required mask

## UART transport с имитацией HAL

`test_uart_console_mock.c` компилирует настоящий учебный `uart_console.c` с маленьким **host-only test double** из `tests/mocks/main.h`. Это дополнительно проверяет:

- Приём и dispatch корректной команды
- Забывание уже разобранного префикса после full FIFO
- Переполнение ровно на CR/LF не отбрасывает следующую целую команду
- Сброс неопределённого хвоста после HAL error
- Восстановление после ошибки повторного arm и после неудачного abort
- Копирование ответа в собственный TX buffer, busy/drop, границу 127/128 байт и failed start
- Восстановление прежнего PRIMASK вместо безусловного разрешения IRQ

Mock не моделирует USART registers, NVIC timing, атомарность реального interrupt entry, HAL всех версий, ARM-инструкции или электрическую линию. Не копируй `tests/mocks/main.h` в CubeMX-проект.

## Не выполнялось

- Компиляция/link generated STM32 firmware ARM toolchain
- Прошивка и debugger на физической Blue Pill
- Измерения GPIO/PWM/capture/UART
- Reset от физического IWDG, debug freeze и проверка option bytes

В отчёте учащегося нужны отдельные строки «host tests», «target build» и «hardware». PASS первой строки не заполняет две остальные.
