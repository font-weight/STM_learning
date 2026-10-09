# L11. Ошибка, безопасное состояние и независимый watchdog

Предпосылки: L04 и L10; минимальный опыт ниже использует только кнопку, LED и UART. Данные L10 добавляются после проверки минимального варианта. Результат: программа умеет объяснить, почему перезапустилась, перестаёт выдавать недостоверный результат и кормит watchdog только при реальном продвижении main.

## Не путать три вида неисправности

1. Неверная команда UART — ошибка ввода: отвергнуть строку, сохранить рабочее состояние.
2. Недостоверное измерение/пропущенный срок — ошибка приложения: перейти в FAULT, сообщить причину, оставить диагностику доступной.
3. Зависший main — потеря выполнения: IWDG перезапускает МК. После перезапуска не надо автоматически скрывать проблему и возвращаться в RUN.

Watchdog не исправляет гонки и не доказывает корректность измерений. Его задача здесь — ограничить длительность зависания учебного макета. Выходы только LED/PWM без силовой нагрузки.

## CubeMX и расчёт IWDG

Оставь HSI8, SysTick, PB12 Pull-up, PC13 active-low, USART1 9600 8N1. Включи IWDG в **software**-запускаемом варианте через обычный HAL init; option bytes в этой работе не изменять.

- IWDG prescaler `64`
- Reload `1249`
- LSI включён/доступен согласно сгенерированному коду
- `MX_IWDG_Init()` вызывается после базовой инициализации; убедись, что до первого refresh нет длинных стартовых ожиданий

```text
T_watchdog ≈ (reload + 1) × prescaler / f_LSI
           = 1250 × 64 / 40000 ≈ 2 s номинально
```

У F103 LSI имеет широкий разброс: в DS5319 таблица LSI указывает 30/40/60 kHz (min/typ/max в заданных условиях). Для этих значений расчётный диапазон около **1,33–2,67 s**, а не точные 2 s. Обслуживание раз в 100 ms даёт большой запас относительно нижней границы. [DS5319, LSI oscillator characteristics](https://www.st.com/resource/en/datasheet/stm32f103c8.pdf).

После программного запуска IWDG нельзя просто выключить обычным вызовом Stop; для нового эксперимента перепрошивка/сброс и изменённая конфигурация должны быть спланированы. При остановленном debugger поведение зависит от debug freeze bit. [RM0008 §19, Independent watchdog](https://www.st.com/resource/en/reference_manual/rm0008-stm32f101xx-stm32f102xx-stm32f103xx-stm32f105xx-and-stm32f107xx-advanced-armbased-32bit-mcus-stmicroelectronics.pdf).

## Конечная машина и обратная связь

- IDLE: LED выключен, измерительная задача не считается запущенной
- RUN: heartbeat с полупериодом 250 ms; выполняется полезная задача
- FAULT: два коротких световых импульса за секунду, UART остаётся доступен
- Кнопка в IDLE → RUN; в RUN → IDLE; в FAULT → только IDLE, не сразу RUN
- После reset от IWDG стартуем в FAULT; пользователь сначала видит причину

Это policy макета, а не универсальное поведение любой системы. В L10 остановка выдачи измерений и маркировка `valid=false` важнее красивого LED.

## Сначала сохранить причину reset

В `USER CODE BEGIN PV`:

```c
static uint32_t boot_reset_flags;
static bool boot_from_iwdg;
```

В `USER CODE BEGIN Init`, сразу после `HAL_Init()` и **до** инициализации IWDG:

```c
boot_reset_flags = RCC->CSR;
boot_from_iwdg = __HAL_RCC_GET_FLAG(RCC_FLAG_IWDGRST) != RESET;
__HAL_RCC_CLEAR_RESET_FLAGS();
```

`boot_reset_flags` теперь можно смотреть весь сеанс. Сначала скопировать, потом очистить — иначе доказательство причины исчезнет. Не сохраняй каждую загрузку во Flash ради этого опыта: запись во Flash здесь не нужна.

## Код контроллера

Перенеси helpers и UART module из L04. В этой работе **замени** прежнюю логику LED и `uart_console_on_command`, не добавляй второго владельца PC13. Включи `stdbool.h`, `stdio.h`, `digital_helpers.h`, `uart_console.h`; если IWDG handle находится в отдельном файле генератора, включи соответствующий `iwdg.h`.

В `PV`:

```c
typedef enum { APP_IDLE, APP_RUN, APP_FAULT } app_state_t;
static app_state_t state;
static uint32_t state_entered;
static digital_debounce_t button;
static digital_health_t health;
static uint32_t control_anchor;
static uint32_t supervise_anchor;
static uint32_t health_misses;
static uint32_t refresh_count;
enum { HEALTH_IO = 1u << 0, HEALTH_CONTROL = 1u << 1 };
```

В `USER CODE BEGIN 0`:

```c
static void app_enter(app_state_t next, uint32_t now)
{
    state = next;
    state_entered = now;
}

static void app_control_tick(uint32_t now)
{
    bool pressed = HAL_GPIO_ReadPin(GPIOB, GPIO_PIN_12) == GPIO_PIN_RESET;
    digital_button_event_t event =
        digital_debounce_update(&button, pressed, now, 20u);
    if (event == DIGITAL_BUTTON_PRESSED) {
        app_enter(state == APP_IDLE ? APP_RUN : APP_IDLE, now);
    }

    uint32_t age = (uint32_t)(now - state_entered);
    bool on = false;
    if (state == APP_RUN) {
        on = ((age / 250u) & 1u) == 0u;
    } else if (state == APP_FAULT) {
        uint32_t phase = age % 1000u;
        on = phase < 100u || (phase >= 300u && phase < 400u);
    }
    HAL_GPIO_WritePin(GPIOC, GPIO_PIN_13,
                     on ? GPIO_PIN_RESET : GPIO_PIN_SET);
}
```

В `USER CODE BEGIN 2`, после всех `MX_*_Init()`:

```c
uint32_t now = HAL_GetTick();
app_enter(boot_from_iwdg ? APP_FAULT : APP_IDLE, now);
digital_debounce_init(&button,
    HAL_GPIO_ReadPin(GPIOB, GPIO_PIN_12) == GPIO_PIN_RESET, now);
digital_health_init(&health, HEALTH_IO | HEALTH_CONTROL);
control_anchor = now;
supervise_anchor = now;
(void)uart_console_start(); /* ошибки учитываются модулем и проверяются ниже */
```

В `USER CODE BEGIN 3`:

```c
uart_console_poll();
if (uart_console_rx_ready())
    digital_health_mark(&health, HEALTH_IO);

uint32_t now = HAL_GetTick();
if (digital_periods_due(now, &control_anchor, 10u) != 0u) {
    app_control_tick(now);
    digital_health_mark(&health, HEALTH_CONTROL);
}

if (digital_periods_due(now, &supervise_anchor, 100u) != 0u) {
    if (digital_health_take_window(&health)) {
        if (HAL_IWDG_Refresh(&hiwdg) == HAL_OK) ++refresh_count;
    } else {
        ++health_misses;
        app_enter(APP_FAULT, now);
        /* Не refresh в этом окне. Работающие сервисы могут восстановиться. */
    }
}
```

Флаги здоровья отмечаются после выполнения соответствующей работы и очищаются **каждое** окно, в том числе неудачное. Иначе успех одного сервиса вчера и другого сегодня мог бы ошибочно составить «всё хорошо». Это проверено host-тестом `test_health`.

Не требуй, чтобы пользователь присылал UART-команду каждые 100 ms. Исправный простаивающий интерфейс тоже здоров. При этом `rx_ready` означает только готовность данного software-модуля, а не физическую исправность провода или наличие компьютера.

## Диагностика и контролируемое зависание

В `USER CODE BEGIN 4`:

```c
void uart_console_on_command(const digital_command_t *command)
{
    if (command->kind == DIGITAL_CMD_STATUS) {
        char response[128];
        int n = snprintf(response, sizeof response,
            "state=%u iwdg=%u reset=%08lX miss=%lu feed=%lu\r\n",
            (unsigned)state, (unsigned)boot_from_iwdg,
            (unsigned long)boot_reset_flags, (unsigned long)health_misses,
            (unsigned long)refresh_count);
        if (n > 0 && (size_t)n < sizeof response)
            (void)uart_console_reply(response);
    } else if (command->kind == DIGITAL_CMD_STALL) {
        (void)uart_console_reply("STALLING\r\n");
        for (;;) { __NOP(); } /* Намеренно: только на безопасном учебном макете. */
    } else {
        (void)uart_console_reply("ERR UNSUPPORTED\r\n");
    }
}
```

Это единственная лабораторная, где `STALL` намеренно разрешён. Команда зависает в main, но прерывания остаются разрешёнными: UART TX может закончить сообщение, SysTick продолжит идти. Если кормить IWDG в SysTick ISR, такой зависший main **не** перезапустится. Именно поэтому ISR-feed — плохой критерий здоровья приложения.

В FAULT код продолжает кормить watchdog, если управляющие/диагностические сервисы живы. Это намеренно: обнаруженная ошибка данных не должна создавать бесконечную череду перезапусков без возможности прочитать диагностику.

## Подключить данные L10, не нарастить случайный проект

После минимального теста добавь **отдельный контроль прогресса измерений**, а не ещё один обязательный bit в 100 ms bitmap. Блоки ADC из L10 тоже приходят раз в 100 ms: одинаковые окна могут разъехаться по фазе и давать ложный FAULT.

Контракт для этого учебного проекта:

- При каждом переходе в RUN/START заново сохранить `run_started_ms`, сбросить `sample_seen` и базу sequence, чтобы старый блок прошлого запуска не считался новым
- Первому корректно обработанному **новому** блоку дать startup grace 300 ms
- После него допускать не более 500 ms с последнего успешного продвижения обработки; сохранить `last_sample_progress_ms` только после принятого нового sequence и успешной проверки ownership/validity
- Проверять age из main независимо от 100 ms watchdog service; при превышении срока пометить результат недействительным, записать ошибку и перейти в FAULT
- В IDLE/FAULT отсутствие новых блоков ожидаемо; продолжающие работать IO/control могут кормить watchdog
- Не считать успешным прогрессом сам запуск DMA, повторное чтение старого sequence или обнаруженный перезаписанный блок
- Потеря внешнего сигнала input capture означает `signal_valid=false` и не является сама по себе отказом main/ADC или обязательным общим FAULT

Псевдоусловие после сброса tracking при каждом START:

```c
bool sample_expired = sample_seen
    ? digital_elapsed(now, last_sample_progress_ms, 500u)
    : digital_elapsed(now, run_started_ms, 300u);
```

Эти переменные добавляются в прикладной слой L10/L13; приведённый минимальный LED-код выше не притворяется готовым ADC-менеджером. 300/500 ms — конкретный договор опыта для 100 ms блоков, его нужно пересчитать при смене частоты/размера DMA.

Задержка main на 350 ms может привести к учтённой потере блоков, но не обязана нарушать 500 ms deadline. Если политика L10 запрещает продолжать после такого overrun, она должна явно перейти в FAULT и предоставить процедуру восстановления; нельзя молча использовать повреждённый буфер. UART STATUS показывает state, validity, возраст данных и причину. Большой RTOS для этого не нужен.

## Измерение и намеренные неисправности

1. Обычный запуск: IDLE, STATUS отвечает, `feed` растёт. Кнопка переводит RUN↔IDLE
2. В RUN отправь STALL, не ставя breakpoint. Через ограниченное время МК перезагрузится, LED перейдёт к коду FAULT; `STATUS` покажет `iwdg=1`
3. Нажми кнопку один раз: FAULT→IDLE, ещё раз: IDLE→RUN. Удержание не создаёт многократных переходов
4. Для разового опыта после обычного reset замени отметку CONTROL на `if (boot_from_iwdg) digital_health_mark(&health, HEALTH_CONTROL);`. Первый запуск не подтверждает здоровье CONTROL: `health_misses` растёт и происходит IWDG reset. После него `boot_from_iwdg=true`, подтверждение снова разрешено и устройство остаётся в диагностическом FAULT без бесконечного reboot loop. Затем верни безусловную отметку после выполненной работы. Не оставляй постоянное удаление отметки: оно вызовет повторные reset на каждой загрузке
5. Сравни debugger halt с включённым и выключенным IWDG debug freeze, предварительно прочитав настройку debugger/DBGMCU. При приёмочном опыте ядро свободно работает; freeze не служит обходом watchdog

Измеряй время **от последнего refresh**, если нужен расчёт timeout. От команды STALL последний refresh мог быть до 100 ms назад, а видимое сообщение после reset добавляет время загрузки и UART. Не бракуй исправный LSI только потому, что получилось не ровно 2,000 s.

## Принять

- Есть журнал минимум пяти STALL-опытов: состояние до, способ измерения, длительность, флаг после, способ выхода из FAULT
- Ни один опыт не требует переподключать питание для продолжения работы
- Неверная UART-строка не вызывает reset; нет бесконечного reboot loop
- После IWDG restart полезная задача не запускается сама
- Host-тест health windows проходит; во время target build записаны Flash/RAM, IWDG configuration и версия HAL
- Диагностика отличает обнаруженную ошибку приложения от зависания выполнения

## По памяти

Без AI объясни: почему `volatile heartbeat=1` не доказывает прогресс? Почему feed из SysTick опасен? Почему нужно очистить bitmap после плохого окна? Затем нарисуй состояния для пропавшего датчика, вернувшегося датчика и зависшей программы, не объединяя их в один `Error_Handler()`.

Статус: health helper проверен на host. IWDG reset, debug freeze, причины reset и восстановление UART на аппаратуре автором не проверены.
