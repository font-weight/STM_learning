# L04. UART: свой протокол, IRQ-приём и восстановление

Предпосылка: L03. Результат: компьютер управляет только LED и учебными параметрами; неверная или слишком длинная строка не превращается в «почти правильную» команду. При потере данных канал умеет найти следующую границу строки.

## Сначала электричество, затем текст

Нужен USB–UART адаптер с **проверенным TX уровня 3,3 V**, не порт RS-232. RS-232 использует другой электрический интерфейс и не подключается прямо к выводам МК. Положение джампера питания адаптера не всегда меняет уровень его TX: проверь документацию/измерь до подключения.

- PA9 / USART1_TX → RX адаптера
- PA10 / USART1_RX ← TX адаптера
- GND ↔ GND
- Питание платы остаётся как в L00; вывод VCC адаптера не подключать при уже выбранном источнике питания
- PA13/PA14 не трогать; встроенный USB-разъём Blue Pill сам по себе не создаёт этот UART

Сначала можно проверить адаптер отдельно замыканием его TX/RX, затем разомкнуть и соединить с платой. Не соединяй два push-pull TX друг с другом.

## CubeMX

Оставь базу HSI8 и SysTick. `USART1 → Asynchronous`:

- Baud rate `9600`; word length 8 bits; parity none; stop bits 1
- Mode TX/RX, hardware flow control none, oversampling 16
- PA9 default USART1_TX, alternate-function push-pull; PA10 default USART1_RX
- USART1 global interrupt enabled; preemption priority `2`, subpriority `0`
- UART DMA выключен; callback registration `USE_HAL_UART_REGISTER_CALLBACKS=0`

В терминале тоже 9600 8N1, no flow control. Выключи local echo или явно пометь его: показанные терминалом собственные символы ещё не доказывают ответ платы. Terminator — LF либо CRLF.

Проверь, что `USART1_IRQHandler()` вызывает `HAL_UART_IRQHandler(&huart1)`. `HAL_UART_Receive_IT(..., 1)` получает **один** байт; после callback нужно запустить следующий приём. HAL возвращает `HAL_OK/BUSY/ERROR`, этот результат нельзя молча игнорировать. [Официальный UART HAL1 driver](https://github.com/STMicroelectronics/stm32f1xx-hal-driver/blob/master/Src/stm32f1xx_hal_uart.c).

## Договор протокола

Команда завершается CR или LF. Пустые строки игнорируются. Регистр букв важен; знаки, лишние пробелы, не-ASCII и мусор после числа запрещены. В числах допускаются ведущие нули.

| Команда | Действие в L04 |
|---|---|
| `LED 0` / `LED 1` | выключить / включить LED, остановить автоматическое мигание |
| `PERIOD 20` … `PERIOD 5000` | установить полупериод LED в ms и включить мигание |
| `STATUS` | краткие счётчики приёма/ошибок |
| `PWM 0` … `PWM 100` | синтаксис зарезервирован для L05; здесь `ERR UNSUPPORTED` |
| `STALL` | зарезервировано для контролируемого опыта L11; здесь запрещено обработчиком |

`LED 1garbage`, `LED -1`, `PERIOD 99999999999999999999` не исполняются. Максимум 47 печатных байт **до** разделителя. При 48-м байте вся строка отбрасывается до следующего CR/LF. Нельзя просто обрезать её до буфера и исполнить.

Это учебный локальный ASCII-протокол без аутентификации, CRC и номеров запросов. Он управляет только безвредными сигналами макета. Не превращай его в управление опасной нагрузкой.

## Подключить готовый транспорт, написать свою политику

1. Включи `digital_helpers.[ch]` и [uart_console.c](../../examples/digital/uart_console.c) и [uart_console.h](../../examples/digital/uart_console.h) в generated-проект по [инструкции](../../examples/digital/README.md). `.c` должен быть добавлен в build target.
2. `uart_console.c` определяет `HAL_UART_RxCpltCallback`, `HAL_UART_ErrorCallback`, `HAL_UART_TxCpltCallback`. Не создавай дубликаты в `main.c`.
3. В `main.c / USER CODE BEGIN Includes` добавь `uart_console.h`, `digital_helpers.h`, `stdbool.h`, `stdio.h`.
4. На этой стадии убери прежнюю логику записи в PC13 из L03. При желании сохраняй опрос кнопки и её счётчик, но только новый LED-handler управляет выходом.

`USER CODE BEGIN PV`:

```c
static bool led_on;
static bool blinking;
static uint32_t led_half_period_ms = 250u;
static uint32_t led_anchor;
volatile uint32_t unsupported_commands;
volatile bool console_start_failed;
```

`USER CODE BEGIN 2`, после `MX_USART1_UART_Init()`:

```c
led_anchor = HAL_GetTick();
console_start_failed = !uart_console_start();
/* При ошибке counter транспорта сохранён; poll повторит recovery.
   console_start_failed можно проверить в debugger. */
```

`USER CODE BEGIN 3`:

```c
uart_console_poll();
uint32_t now = HAL_GetTick();
if (blinking) {
    uint32_t due = digital_periods_due(now, &led_anchor, led_half_period_ms);
    if ((due & 1u) != 0u) led_on = !led_on;
}
HAL_GPIO_WritePin(GPIOC, GPIO_PIN_13,
                  led_on ? GPIO_PIN_RESET : GPIO_PIN_SET);
/* Другие короткие задачи, например debounce, продолжают работать здесь. */
```

`USER CODE BEGIN 4`:

```c
void uart_console_on_command(const digital_command_t *command)
{
    switch (command->kind) {
    case DIGITAL_CMD_LED:
        blinking = false;
        led_on = command->value != 0u;
        (void)uart_console_reply("OK LED\r\n");
        break;
    case DIGITAL_CMD_PERIOD:
        led_half_period_ms = command->value;
        led_anchor = HAL_GetTick();
        blinking = true;
        (void)uart_console_reply("OK PERIOD\r\n");
        break;
    case DIGITAL_CMD_STATUS: {
        uart_console_stats_t s;
        char response[128];
        uart_console_get_stats(&s);
        int n = snprintf(response, sizeof response,
            "rx=%lu q=%lu err=%lu line=%lu txdrop=%lu\r\n",
            (unsigned long)s.rx_bytes, (unsigned long)s.queue_overflows,
            (unsigned long)s.hal_errors, (unsigned long)s.line_errors,
            (unsigned long)s.tx_dropped);
        if (n > 0 && (size_t)n < sizeof response)
            (void)uart_console_reply(response);
        break;
    }
    default:
        ++unsupported_commands;
        (void)uart_console_reply("ERR UNSUPPORTED\r\n");
        break;
    }
}
```

Ответ копируется в собственный статический TX-буфер транспорта и уходит через `HAL_UART_Transmit_IT`. Стековый `response` поэтому не остаётся dangling pointer после выхода callback. Если предыдущий ответ ещё передаётся, новый ответ **отбрасывается**, растёт `tx_dropped`. Обработанная команда и гарантированно полученный клиентом ответ — разные вещи. Для ручного терминала отправляй следующую команду после ответа; полноценная очередь ответов — отдельное расширение.

## Разобрать транспорт по слоям

Прочитай код, затем нарисуй:

`USART DR → HAL IRQ → 1 byte callback → FIFO → line parser → command → application`.

- ISR не разбирает строки и не печатает. Он кладёт байт, перезапускает RX и выходит
- FIFO на 64 байта имеет проверку full/empty. Операции главного цикла защищены короткой critical section с восстановлением PRIMASK
- Переполнение FIFO очищает повреждённый поток; ISR отбрасывает хвост строки, а `rx_epoch` заставляет главный parser забыть прежний префикс
- Ошибки HAL (`ORE/FE/NE/PE`) учитываются отдельно от переполнения программного FIFO
- Восстановление выполняется из main: приостановить USART IRQ, `HAL_UART_AbortReceive`, штатно очистить ORE, сбросить очередь, запустить однобайтный RX, возобновить IRQ
- После такой ошибки сначала пошли пустую строку, затем новую команду: транспорт намеренно отбрасывает неопределённый хвост до границы
- `poll` обрабатывает не более 32 байт за вызов, чтобы поток UART не монополизировал весь main

Для F1 очистка некоторых UART flags требует последовательности чтений SR/DR, а не произвольной записи нуля. Открытый в debugger peripheral view может читать регистры с побочными эффектами. Не используй непрерывное чтение `DR` debugger как безобидный «просмотр UART». [RM0008, USART status/data registers](https://www.st.com/resource/en/reference_manual/rm0008-stm32f101xx-stm32f102xx-stm32f103xx-stm32f105xx-and-stm32f107xx-advanced-armbased-32bit-mcus-stmicroelectronics.pdf).

## Бюджет времени и RAM

8N1 расходует 10 бит на байт: при 9600 это максимум 960 байт/с, 64-байтный FIFO заполняется примерно за 66,7 ms без обслуживания. При 115200 — 11 520 байт/с и всего 5,56 ms. Буфер не исправляет бесконечно медленного потребителя.

Подними **и прошивку, и терминал** до 115200, измерь длительность бита и проверь ошибки. HSI и округление USART divider дают отклонение от номинала; успешный опыт при комнатной температуре не доказывает связь во всём диапазоне условий. Вернись к 9600, если цель текущей работы — parser, а не предел канала.

Запиши `sizeof` и map: FIFO payload 64, строка 48, TX 128 байт; поверх этого есть индексы, counters, alignment и стек `snprintf`. Helpers не используют heap. Оценка RAM «только 64+48+128» неполная.

## Намеренные неисправности

1. Удали только повторный `HAL_UART_Receive_IT` в callback: первый байт придёт, дальнейшие — нет. Восстанови код
2. Отправь 60 символов `X`, затем LF, затем `LED 1` + LF: первая строка отвергнута, вторая выполняется
3. В main на один опыт добавь паузу 250 ms и во время неё вставь в терминал длинную строку. IRQ продолжает работать, но FIFO переполнится; `q` увеличится. Удали паузу, отправь пустую строку и `STATUS`
4. Отдельно искусственно задержи обслуживание **USART IRQ** во время потока, затем восстанови его. Это тест аппаратного overrun, не тот же самый тест FIFO. Tick не отключай, а код эксперимента не оставляй в нормальном проекте

## Принять

- `LED 1`, `LED 0`, `PERIOD 250`, `STATUS` работают последовательно; полный период мигания при `PERIOD 250` около 500 ms
- Неверные, отрицательные, слишком большие и overlong аргументы не меняют состояние приложения
- CRLF даёт один результат, пустая строка не даёт ложную команду
- После full FIFO/ошибки RX связь восстанавливается без ручного reset после разделителя и новой корректной команды
- При обычной ручной работе `q=0`, `err=0`; при flood допускаются документированные `txdrop`, но запрещены выход за RAM и исполнение обрезанного сообщения
- Host-тесты parser/FIFO проходят. Target build, размер образа, тип адаптера и испытания на плате записаны отдельно

## По памяти

Закрой transport-код. Нарисуй отличие `volatile`, атомарной загрузки, critical section и очереди. Потом добавь команду `RATE 1..10`, не применяя `atoi`, не оставляя непроверенного хвоста и не меняя рабочие настройки при ошибке. Прежде чем подключать её к ADC, напиши host-тесты крайних значений и переполнения числа.

Статус: helpers и UART adapter с имитацией HAL проверены GCC и sanitizers; [подробный состав тестов](../../tests/DIGITAL_TESTS.md). Реальная компиляция STM32-проекта и UART на плате автором не выполнялись.
