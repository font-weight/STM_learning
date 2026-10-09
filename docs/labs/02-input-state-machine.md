# L02. Кнопка, debounce, EXTI и обмен с ISR

Предпосылка: L01. Результат: одно нажатие даёт одно действие; программа различает физические фронты, подтверждённое состояние кнопки и события приложения. Это первая конечная машина курса: вход может шуметь, состояние должно меняться по правилу.

## Схема и CubeMX

Соедини PB12 с одной стороной нормально разомкнутой кнопки, другую с GND. Включи внутренний Pull-up; для коротких проводов на макетке его достаточно для этого опыта. Не подавай на кнопку внешнее напряжение. У четырёхвыводной тактовой кнопки пары ножек уже соединены внутри: сначала прозвони без питания.

Оставь HSI 8 MHz, SWD и PC13 из L01. Этап A:

- PB12: `GPIO_Input`, Pull-up, метка `BUTTON`
- PC13: output push-pull, initial high, low speed
- Никаких внешних прерываний пока не нужно

Скопируй helper-файлы по [инструкции](../../examples/digital/README.md). Состояние `pressed` ниже — логическое «нажата», поэтому оно равно `ReadPin == RESET`.

## Этап A. Опрос и подтверждение устойчивого состояния

Параметр `20 ms` — выбранная стартовая настройка лабораторной, не универсальная характеристика всех кнопок. Сначала измеришь свою кнопку, затем обоснуешь значение.

В `USER CODE BEGIN Includes`:

```c
#include <stdbool.h>
#include "digital_helpers.h"
```

В `USER CODE BEGIN PV`:

```c
static digital_debounce_t button;
static uint32_t sample_anchor;
static bool led_on;
volatile uint32_t press_count;
volatile uint32_t sample_missed;
```

В `USER CODE BEGIN 2`:

```c
uint32_t now = HAL_GetTick();
digital_debounce_init(&button,
    HAL_GPIO_ReadPin(GPIOB, GPIO_PIN_12) == GPIO_PIN_RESET, now);
sample_anchor = now;
```

В `USER CODE BEGIN 3`, без `HAL_Delay`:

```c
uint32_t now = HAL_GetTick();
uint32_t due = digital_periods_due(now, &sample_anchor, 1u);
if (due != 0u) {
    if (due > 1u) sample_missed += due - 1u;
    bool pressed = HAL_GPIO_ReadPin(GPIOB, GPIO_PIN_12) == GPIO_PIN_RESET;
    digital_button_event_t event =
        digital_debounce_update(&button, pressed, now, 20u);
    if (event == DIGITAL_BUTTON_PRESSED) {
        ++press_count;
        led_on = !led_on;
        HAL_GPIO_WritePin(GPIOC, GPIO_PIN_13,
                         led_on ? GPIO_PIN_RESET : GPIO_PIN_SET);
    }
}
```

`candidate` меняется сразу при новом наблюдаемом уровне; `stable` — только когда этот кандидат сохраняется в выборках не менее заданного интервала. Отдельные устойчивые нажатие и отпускание дают отдельные события. Удержание кнопки не повторяет нажатие. Нажатая при старте кнопка становится начальным состоянием, а не синтетическим событием.

Опрос раз в 1 ms не доказывает, что между выборками не было импульса. Для данной кнопки это осознанное ограничение. Удалённый датчик или точный счётчик импульсов требует другого решения.

## Этап B. Сначала ISR, затем главный цикл

Измени PB12 на `GPIO_EXTI12`, режим interrupt on rising **and** falling edge, Pull-up. В NVIC включи `EXTI line[15:10] interrupts`, preemption priority `2`, subpriority `0`; priority grouping — 4 bits preemption, 0 bits subpriority. Оставь SysTick в типичной низкой приоритетности проекта. Меньшее числовое значение NVIC означает более высокий приоритет; прерывание равного приоритета не вытеснит текущее. [PM0056, NVIC](https://www.st.com/resource/en/programming_manual/pm0056-stm32f10xxx20xxx21xxxl1xxxx-cortexm3-programming-manual-stmicroelectronics.pdf).

Проверь после генерации в `stm32f1xx_it.c`:

```c
void EXTI15_10_IRQHandler(void)
{
    HAL_GPIO_EXTI_IRQHandler(GPIO_PIN_12);
}
```

Не копируй второе определение этого handler в `main.c`. Этот вектор общий для линий 10–15: если позже включишь другую линию, обработчик должен обслуживать и её. EXTI12 выбирает один источник порта: PB12 и PA12 нельзя независимо обслуживать как две разные EXTI12 одновременно. [RM0008, AFIO_EXTICR и EXTI](https://www.st.com/resource/en/reference_manual/rm0008-stm32f101xx-stm32f102xx-stm32f103xx-stm32f105xx-and-stm32f107xx-advanced-armbased-32bit-mcus-stmicroelectronics.pdf).

Добавь в `PV`:

```c
static volatile uint32_t edge_pending;
static volatile uint32_t edge_saturated;
volatile uint32_t edges_observed;
```

В `USER CODE BEGIN 4`:

```c
void HAL_GPIO_EXTI_Callback(uint16_t pin)
{
    if (pin == GPIO_PIN_12) {
        if (edge_pending != UINT32_MAX) ++edge_pending;
        else edge_saturated = 1u;
    }
}
```

В `USER CODE BEGIN 0`:

```c
static uint32_t take_edges(void)
{
    uint32_t saved_mask = __get_PRIMASK();
    __disable_irq();
    uint32_t result = edge_pending;
    edge_pending = 0u;
    __set_PRIMASK(saved_mask);
    return result;
}
```

В начале тела `while`: `edges_observed += take_edges();`. Опрос и debounce оставь прежними. Прерывание сообщает о фронтах; решение «считать нажатием» по-прежнему принимает обычный код. Для человеческой кнопки опрос часто проще и достаточен: EXTI здесь нужен, чтобы научиться передавать события и увидеть дребезг.

## Почему volatile недостаточно

`volatile` запрещает компилятору обращаться с общей переменной как с неизменной локальной копией. Он не превращает `++`, `copy; clear;`, проверку с последующей записью или обновление двух полей в одну неделимую операцию.

Без короткой критической секции ISR может увеличить `edge_pending` между копированием и обнулением: новое событие пропадёт. Выравненная 32-битная загрузка/запись на Cortex-M3 и составной алгоритм — разные вещи. Обработчик выше и главный цикл пользуются одним ясным протоколом. Маску восстанавливаем сохранённую, а не безусловно вызываем `__enable_irq()`: иначе вложенный вызов может неожиданно разрешить ранее запрещённые IRQ.

В критической секции только несколько операций с RAM. Не помещай туда ожидание, форматирование, UART send или обработку всех накопившихся событий. Host-тесты проверяют логику, но не доказывают корректность реального межконтекстного доступа.

## Запрещённый учебный антипример

Не исправляй дребезг через `HAL_Delay(20)` в `HAL_GPIO_EXTI_Callback`. При SysTick ниже текущего IRQ время HAL может не продвигаться, и ожидание зависнет. Даже если изменить приоритеты так, чтобы tick проходил, 20 ms внутри ISR блокируют другие задачи. Callback должен быстро записать факт и закончиться. [UM1850, HAL timebase и interrupt API](https://www.st.com/resource/en/user_manual/um1850-description-of-stm32f1-hal-and-lowlayer-drivers-stmicroelectronics.pdf).

## Намеренные неисправности

1. Поставь debounce `0 ms`: сравни физические фронты и число действий за 20 нажатий. Отсутствие лишних действий на конкретной кнопке не доказывает, что дребезга не бывает.
2. Временно отключи NVIC EXTI15_10. `edges_observed` перестанет расти, но опросная кнопка продолжит работать. Так разделяются GPIO, EXTI, NVIC и логика приложения.
3. Мысленно расставь ISR между `result = edge_pending` и `edge_pending = 0`, затем восстанови короткую критическую секцию. Не оставляй заведомо гоняющий код рабочей версией.

## Измерить и принять

- 20 обычных нажатий → ровно 20 изменений LED; удержание 2 s → одно изменение
- Отпускание на 30 ms и повторное нажатие распознаётся, сверхкороткий импульс менее порога может быть отвергнут
- Логическим анализатором на PB12 измерены дребезг и задержка подтверждения. Без анализатора честно записано, что измерены только программные события
- `edges_observed` показывает сырые фронты, `press_count` — подтверждённые нажатия; их равенство не требуется
- `sample_missed` не растёт в обычной работе без остановок debugger; при breakpoint может расти, что ожидаемо
- `tests/run_digital_tests.sh` проходит, включая debounce на переполнении `HAL_GetTick`

## По памяти и перенос

Без AI и исходного примера нарисуй переходы `stable/candidate`. Добавь событие «удержание 700 ms» так, чтобы оно срабатывало один раз и не мешало короткому нажатию. Сначала определи, считать ли короткое действие в момент нажатия или при отпускании: это продуктовая семантика, а не свойство EXTI.

Статус: чистая логика проверена host-тестами; IRQ, схема и временные измерения на плате не проверены автором.
