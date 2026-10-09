# L05. Аппаратный PWM: частота, скважность и границы

Предпосылка: L03; UART-регулировка требует L04. Результат: ты рассчитываешь PSC/ARR/CCR, проверяешь частоту прибором и меняешь duty без программного переключения GPIO.

## Схема

Выход — **PA1 / TIM2_CH2**, не PC13. Для первого измерения подключи PA1 к входу логического анализатора, GND к GND. Вход прибора должен подходить для 3,3 V. Если прибора нет, можно PA1 → 1 kΩ → анод LED → катод GND, но изменение яркости не доказывает правильную частоту. Никаких двигателей, реле и силовых нагрузок.

## CubeMX: ровно 1 kHz номинально

Общий clock contract: HSI8, PLL off, SYSCLK/HCLK/PCLK1/PCLK2 = 8 MHz, все bus dividers `/1`.

`TIM2`:

- Clock Source: Internal Clock
- Channel 2: PWM Generation CH2; default mapping PA1, без remap
- Prescaler `7`
- Counter Mode: Up
- Counter Period / ARR `999`
- Clock Division: DIV1
- Auto-reload preload: Enable
- PWM mode 1, Pulse `500`, output polarity High, fast mode Disable
- PA1 alternate-function push-pull, low speed 2 MHz
- TIM2 interrupt и DMA не включать

TIM2 в этом STM32F103C8 — **16-битный** таймер. Не переноси свойство 32-битного TIM2 из других серий STM32. GPIO speed — настройка электрического драйвера, она не задаёт PWM frequency. [DS5319, timer features и PA1](https://www.st.com/resource/en/datasheet/stm32f103c8.pdf).

## Посчитать до запуска

Для edge-aligned PWM с увеличением счётчика:

```text
f_counter = f_TIM / (PSC + 1)
f_PWM     = f_TIM / ((PSC + 1) * (ARR + 1))
duty      = CCR2 / (ARR + 1), в данном PWM mode 1 / active high
```

Здесь `8 000 000 / 8 = 1 000 000` отсчётов/с; 1000 отсчётов дают 1 ms. `CCR2=500` даёт 0,5 ms высокого уровня и 0,5 ms низкого. Поле PSC хранит делитель **минус один**; поле ARR задаёт последнюю величину счётчика, поэтому отсчёт 0 тоже входит в период.

На F1 clock таймера равен PCLK соответствующей APB, если её prescaler `/1`, и удвоенному PCLK при другом APB prescaler. У TIM2 это APB1; у TIM1 в следующей работе APB2. Сначала прочитай clock tree своего `.ioc`, потом подставляй числа. [RM0008, RCC clock tree и TIM2–TIM5 PWM mode](https://www.st.com/resource/en/reference_manual/rm0008-stm32f101xx-stm32f102xx-stm32f103xx-stm32f105xx-and-stm32f107xx-advanced-armbased-32bit-mcus-stmicroelectronics.pdf).

## Код в generated-проекте

`MX_TIM2_Init()` настраивает таймер, но сам по себе ещё не означает, что PWM запущен. В `USER CODE BEGIN 2`, после инициализации GPIO/TIM2:

```c
if (HAL_TIM_PWM_Start(&htim2, TIM_CHANNEL_2) != HAL_OK) {
    Error_Handler();
}
```

Если CubeMX вынес peripheral handles в отдельный `tim.h`, включи его в `USER CODE BEGIN Includes`. Если handle определён выше `main` в том же файле, дополнительный `extern` не нужен. Не объявляй второй экземпляр `htim2`.

Добавь `digital_helpers.h`. В `USER CODE BEGIN 0`:

```c
static bool pwm_set_percent(uint32_t percent)
{
    uint16_t compare;
    if (percent > 100u ||
        !digital_pwm_compare16(1000u, (uint8_t)percent, &compare)) {
        return false;
    }
    __HAL_TIM_SET_COMPARE(&htim2, TIM_CHANNEL_2, compare);
    return true;
}
```

Число 1000 здесь является `ARR+1` **текущей фиксированной настройки**. Если меняешь ARR, переделай этот договор. Helper намеренно принимает не более 65535 period counts: при ARR=65535 идеальное значение CCR для 100% равно 65536 и в 16-битный регистр не помещается. В нашей настройке ARR=999 значение CCR=1000 помещается и даёт постоянный высокий уровень.

В обработчик UART L04 добавь отдельный `case`, до `default`:

```c
case DIGITAL_CMD_PWM:
    if (pwm_set_percent(command->value))
        (void)uart_console_reply("OK PWM\r\n");
    else
        (void)uart_console_reply("ERR PWM\r\n");
    break;
```

Для варианта без UART меняй duty раз в секунду из main через scheduler L03: `0, 25, 50, 75, 100`. Не делай этот переход из ISR и не используй программное переключение PA1 параллельно с таймером.

При preload новое compare-значение применяется на границе обновления; это помогает избежать случайного укороченного импульса при изменении посреди периода. Проверь реальную конфигурацию compare preload и поведение осциллограммой. Изменение PSC/ARR на лету добавляет вопросы update event и предзагрузки: на этой стадии меняем только CCR. [AN4776, time-base и PWM examples](https://www.st.com/resource/en/application_note/an4776-generalpurpose-timer-cookbook-for-stm32-microcontrollers-stmicroelectronics.pdf).

## Наблюдения, которые важнее мигающего LED

1. При 0% линия постоянно низкая, при 100% постоянно высокая: на этих крайних значениях частоту по фронтам измерить нельзя.
2. При 25/50/75% период остаётся 1 ms, меняется только высокий интервал.
3. CPU может заниматься parser/кнопкой, пока таймер самостоятельно продолжает генерировать PWM.
4. Это цифровой сигнал 0/3,3 V, не настоящий DAC. Среднее идеального PWM можно вычислить, но вход внешнего устройства не обязан усреднять его.
5. Если измерить output и input capture тем же HSI, общий дрейф частоты может скрыться. Для абсолютного измерения нужен независимый timebase прибора.

## Намеренные неисправности

- Не вызвать `HAL_TIM_PWM_Start`: init есть, фронтов нет. Проверь CEN/CC2E, а не только цвет вывода в CubeMX
- Перепутать `TIM_CHANNEL_1` и `TIM_CHANNEL_2`: PA1 не выдаёт ожидаемый сигнал
- Поставить PSC=8 вместо 7: посчитать новую частоту и найти отличие измерением
- После перехода к проверенной конфигурации 72 MHz из clock appendix оставить PSC=7: расчёт станет другим. Восстанови базовый HSI8; не объясняй расхождение «магией HAL»

## Принять

С анализатором/осциллографом заполни таблицу из пяти строк: duty 0, 25, 50, 75, 100%; расчёт CCR; измеренный высокий интервал; измеренный период или «постоянный уровень»; инструмент и его ограничения.

**Без прибора допускается функциональный зачёт для перехода к L06:** проверить PSC/ARR/CCR и разрешение канала в debugger, постоянные уровни 0/100% и изменение яркости внешнего LED. Графы периода и высокого интервала пометить «не измерено»; не подменять измерение расчётом. В L06 loopback даст относительную проверку периода, но не независимую точность HSI и не измерение duty. Осциллограммы можно дополнить позже, это не скрытая обязательная покупка и не блокировка перехода к L06.

- При инструментальном зачёте: при 25/50/75% период близок к 1 ms с учётом HSI и прибора
- `PWM 101` и `PWM -1` не меняют выход
- Во время серии изменений PWM кнопка/CLI остаются отзывчивыми
- Ни один из этих опытов не требует IRQ TIM2
- Host-тесты подтверждают CCR endpoints и арифметику, но не форму сигнала

## По памяти

Без AI рассчитай настройку 2 kHz с resolution 1000 шагов и объясни, возможна ли она при f_TIM=8 MHz. Затем настрой 500 Hz с тем же ARR и докажи измерением. Не меняй одновременно PSC и ARR «пока не заработает».

Статус: расчёты и pure-C helper проверены; generated ARM build и осциллограммы на плате автором не выполнялись.
