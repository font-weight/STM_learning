# L06. Измерить период: input capture, overflow и достоверность

Предпосылка: L05; вывод результатов UART требует L04. Результат: аппаратно зафиксировать момент фронта и отличить корректное измерение от устаревшего, переполненного или недостаточно обоснованного числа.

## Схема и границы задачи

На **одной** Blue Pill: PA1 / TIM2_CH2 → резистор 1 kΩ → PA8 / TIM1_CH1. Выход PWM оставь 1 kHz, 50%. Если используется внешний источник, допустим только заранее проверенный сигнал 0–3,3 V с общим GND. Здесь нет внешней силовой техники.

Таймер генератора TIM2 и таймер измерителя TIM1 отдельные: настройки ARR генератора не обрезают диапазон счётчика capture. TIM1_CH2 оставь выключенным, PA9 остаётся USART1_TX. Это также избегает ненужного для курса сочетания, отмеченного в errata.

**Рабочий диапазон этой лабораторной — известный чистый периодический сигнал 20–2000 Hz.** Это учебный измеритель, не универсальный частотомер и не доказательство, что ни один фронт не потерян. Если источник неизвестен, одного вычитания CCR недостаточно.

## CubeMX

TIM2 остаётся по L05. `TIM1`:

- Internal Clock, counter Up, Prescaler `7`
- ARR / Counter Period `65535`, Clock Division DIV1
- Repetition Counter `0`, auto-reload preload Disable
- Channel 1: Input Capture direct mode (`Direct TI`, TI1)
- Polarity Rising, IC prescaler DIV1, digital filter `0`
- PA8 default TIM1_CH1 input; Pull-down для определённого уровня при снятом проводе
- NVIC: TIM1 capture compare interrupt enabled, preemption priority `1`, subpriority `0`
- TIM1 update IRQ, trigger IRQ, DMA и все выходные/комплементарные каналы выключены

TIM1 питается от APB2 timer clock: при базовой схеме это 8 MHz; после PSC=7 счётчик идёт 1 MHz. Один tick — номинально 1 µs; полный оборот 65536 µs = 65,536 ms. [RM0008, advanced-control timers, input capture и status register](https://www.st.com/resource/en/reference_manual/rm0008-stm32f101xx-stm32f102xx-stm32f103xx-stm32f105xx-and-stm32f107xx-advanced-armbased-32bit-mcus-stmicroelectronics.pdf).

Проверь `TIM1_CC_IRQHandler()` → `HAL_TIM_IRQHandler(&htim1)`. В `USER CODE BEGIN 2` после init:

```c
if (HAL_TIM_IC_Start_IT(&htim1, TIM_CHANNEL_1) != HAL_OK)
    Error_Handler();
if (HAL_TIM_PWM_Start(&htim2, TIM_CHANNEL_2) != HAL_OK)
    Error_Handler();
```

Если PWM уже запускается из L05, не добавляй второй вызов. Сначала arm capture, затем запускай известный источник.

## Почему timestamp ISR и capture не одно и то же

На фронте аппаратный блок копирует CNT в CCR1. ISR читает уже сохранённую отметку; обычная задержка входа ISR поэтому не добавляется напрямую к каждому измеренному периоду. Но если не обслужить capture до следующих фронтов, данные могут быть перезаписаны. При высокой частоте interrupt-per-edge тоже имеет предел.

Если предыдущий CCR=65000, а следующий=464, разность **в uint16_t** равна 1000. Это правильно, только когда реальный интервал меньше одного оборота. Для интервала 66536 ticks получится то же число 1000. Математика не способна восстановить забытый полный оборот.

Теоретический нижний предел однооборотного вычитания при 1 MHz чуть выше `1 000 000 / 65536 ≈ 15,259 Hz`. Мы берём 20 Hz для запаса, вводим грубую проверку межфронтового времени и timeout. Для настоящих медленных сигналов понадобится другой PSC либо расширение timestamp счётчиком overflow с разбором гонки между update и capture. Это отдельное усложнение, не одна дополнительная строка.

## Mailbox: ISR публикует, main делает снимок

В `PV`:

```c
typedef struct {
    uint32_t sequence;
    uint32_t at_ms;
    uint32_t rejected;
    uint32_t overcapture_seen;
    uint16_t period_ticks;
    bool valid;
} capture_snapshot_t;
static volatile capture_snapshot_t capture;
static bool have_previous;
static uint16_t previous_ccr;
static uint32_t previous_ms;
```

`bool`, `uint*_t`, helper и TIM handle должны быть включены как в L05. В `USER CODE BEGIN 4`:

```c
void HAL_TIM_IC_CaptureCallback(TIM_HandleTypeDef *timer)
{
    if (timer->Instance != TIM1 || timer->Channel != HAL_TIM_ACTIVE_CHANNEL_1)
        return;

    uint16_t current = (uint16_t)HAL_TIM_ReadCapturedValue(timer, TIM_CHANNEL_1);
    uint32_t now = HAL_GetTick();
    bool overcapture = __HAL_TIM_GET_FLAG(timer, TIM_FLAG_CC1OF) != RESET;
    if (overcapture) {
        __HAL_TIM_CLEAR_FLAG(timer, TIM_FLAG_CC1OF);
        ++capture.overcapture_seen;
    }

    uint16_t delta = digital_capture16_delta(previous_ccr, current);
    bool valid = have_previous && !overcapture &&
        (uint32_t)(now - previous_ms) < 60u &&
        delta >= 500u && delta <= 50000u;

    capture.period_ticks = delta;
    capture.at_ms = now;
    capture.valid = valid;
    if (have_previous && !valid) ++capture.rejected;
    ++capture.sequence;
    previous_ccr = current;
    previous_ms = now;
    have_previous = true;
}
```

В `USER CODE BEGIN 0`:

```c
static capture_snapshot_t capture_read(void)
{
    capture_snapshot_t result;
    uint32_t saved_mask = __get_PRIMASK();
    __disable_irq();
    result.sequence = capture.sequence;
    result.at_ms = capture.at_ms;
    result.rejected = capture.rejected;
    result.overcapture_seen = capture.overcapture_seen;
    result.period_ticks = capture.period_ticks;
    result.valid = capture.valid;
    __set_PRIMASK(saved_mask);
    return result;
}
```

В main обновляй снимок и проверяй свежесть на **каждой итерации**. Только отправку UART ограничь до 5 раз/с; не печатай каждый фронт:

```c
capture_snapshot_t measured = capture_read();
uint32_t now = HAL_GetTick();
bool fresh = measured.sequence != 0u &&
             !digital_elapsed(now, measured.at_ms, 150u);
if (fresh && measured.valid) {
    uint32_t frequency_millihz =
        1000000000u / measured.period_ticks; /* 1 MHz * 1000; fits uint32_t */
    /* Сохрани/покажи period_ticks и frequency_millihz из одного снимка. */
    (void)frequency_millihz;
} else {
    /* Покажи NO SIGNAL или INVALID, а не прежнюю "хорошую" частоту. */
}
```

Добавь этот блок непосредственно в main. Отдельная периодическая задача L03 раз в 200 ms форматирует уже вычисленный результат через ограниченный `snprintf`, затем `uart_console_reply`; политика busy/drop из L04 остаётся. Внутренний `fresh` станет false примерно через 150 ms плюс задержка main; сообщение терминала при отчёте раз в 200 ms может появиться примерно через 350 ms плюс задержка передачи. Это разные сроки. Чтобы сравнивать результаты между запусками, запиши также `sequence`, `rejected`, `overcapture_seen`.

Mailbox хранит **последнее** измерение, а не все периоды. Разность sequence между снимками показывает, сколько публикаций прошло; это не равнозначно потерянным аппаратным фронтам. Для сохранения каждого sample нужна очередь с собственным бюджетом.

## Ограничения, которые нельзя спрятать за числом Hz

- Грубый `HAL_GetTick` gap проверяет слишком медленные интервалы, но зависит от своевременного SysTick. Длительное глобальное маскирование IRQ нарушает это предположение
- На 20 Hz период около 50000 ticks, на 2000 Hz — 500 ticks. У результата есть квантование и погрешность генератора
- Оба таймера используют один HSI: отношение может выглядеть идеальным, даже когда абсолютная частота HSI отличается от номинальной
- Флаг CC1OF полезен как предупреждение, но **не гарантирует** обнаружение каждого пропуска. Для среднеплотных F103 есть ограничения capture/overcapture в ES096 §2.6.5–2.6.6. Нулевой счётчик OF не сертификат отсутствия потерь
- На duty 0/100% фронтов нет: корректный результат — timeout, не деление на ноль
- Первый фронт после старта только создаёт исходную отметку; он не даёт периода

[Официальная errata ES096](https://www.st.com/resource/en/errata_sheet/es096-stm32f101x8b-stm32f102x8b-and-stm32f103x8b-mediumdensity-device-limitations-stmicroelectronics.pdf).

## Измерения и намеренные неисправности

1. База: TIM2 PSC=7, ARR=999, CCR2=500 → capture около 1000 ticks. Запусти дольше 1 s: сам CNT много раз переполнится, измерение должно продолжаться
2. 20 Hz: TIM2 PSC=7, ARR=49999, CCR2=25000 → около 50000 ticks. Это край разрешённого диапазона
3. 2000 Hz: TIM2 PSC=7, ARR=499, CCR2=250 → около 500 ticks. Наблюдай нагрузку, потерю отзывчивости и OF; аппаратный предел не объявляется только на основании этого теста
4. Сними перемычку: PA8 pull-down, внутренний validity становится false примерно через 150 ms плюс задержка main; следующий UART-отчёт показывает NO SIGNAL
5. Сделай заведомо 2 Hz: TIM2 PSC=7999, ARR=499, CCR2=250. Наивное 16-битное вычитание даст ложные десятки Hz; проверка gap должна отвергнуть интервал. Не расширяй «поддерживаемый диапазон» по случайному числу
6. Укажи в формуле ошибочную частоту capture counter 8 MHz вместо 1 MHz и объясни восьмикратную ошибку. Восстанови правильную единицу

После каждого изменения PWM проверь фактический `.ioc` и не используй фиксированный helper `ARR+1=1000` из L05 без изменения параметра.

## Принять

- Есть три строки измерений 20/1000/2000 Hz: расчёт PSC/ARR/CCR, ожидаемый ticks, наблюдённый ticks, показание независимого прибора если доступен
- Пересечение нуля CNT не ломает короткий период; host-тест `65000 → 464` даёт 1000
- Первый фронт и stale signal не выдаются за достоверную частоту
- 2 Hz отвергается, а не молча отображается как валидное число из диапазона
- UART выводится редко, ISR не форматирует строки; SWD остаётся доступен
- В отчёте явно записано, что доказана работоспособность bounded loopback, а не отсутствие всех потерь на произвольном источнике

## По памяти

Без AI выбери PSC для измерения 1–10 Hz одним оборотом 16-битного counter. Посчитай шаг времени и относительное квантование на 10 Hz. Затем объясни, почему одновременно расширить низкую границу и сохранить микросекундное разрешение без дополнительного механизма нельзя.

Статус: modulo-разность проверена host-тестами; TIM configuration, IRQ latency, errata workaround и электрические измерения на плате автором не тестировались.
