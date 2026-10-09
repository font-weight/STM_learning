# Первичные источники для цифровых лабораторных

Проверено 9 октября 2026 года. Это карта, **где проверять утверждение**, а не приглашение читать все руководства подряд. Для конкретного проекта также зафиксируй версию STM32CubeF1/HAL, которую реально сгенерировал CubeMX. Онлайн-ветка `master` может меняться.

## Документы ST

1. [STM32F103x8/xB datasheet DS5319](https://www.st.com/resource/en/datasheet/stm32f103c8.pdf), просмотрена Rev 20, July 2025. Проверены: C8 = 64 KiB Flash, SRAM 20 KiB; HSI nominal 8 MHz; таблица выводов PA1/TIM2_CH2, PA8/TIM1_CH1, PA9/PA10/USART1; 16-битные timers; ограничения PC13; таблица LSI 30/40/60 kHz. Не путать таблицу семейства x8/xB с разрешением использовать 128 KiB на C8.
2. [RM0008 reference manual](https://www.st.com/resource/en/reference_manual/rm0008-stm32f101xx-stm32f102xx-stm32f103xx-stm32f105xx-and-stm32f107xx-advanced-armbased-32bit-mcus-stmicroelectronics.pdf), Rev 21. Использованные разделы: Low-/medium-/high-/XL-density RCC; §9 GPIO и AFIO; §10 EXTI/NVIC; §14 TIM1/TIM8, особенно Input capture mode; §15 TIM2–TIM5; §19 IWDG; §27 USART. Ручной просмотр проверяет смысл clock gate, APB timer clock ×2 при prescaler≠1, CRL/CRH и BSRR, EXTI routing, PSC/ARR/CCR, захват/overflow, последовательность очистки ORE SR→DR и watchdog/debug freeze.
3. [UM1850, STM32F1 HAL and low-layer drivers](https://www.st.com/resource/en/user_manual/um1850-description-of-stm32f1-hal-and-lowlayer-drivers-stmicroelectronics.pdf), Rev 3, February 2020. API-модель HAL1, timebase, GPIO, TIM, UART и IWDG. Версия подтверждена на [официальной странице STM32CubeF1](https://www.st.com/en/embedded-software/stm32cubef1.html). Для поведения конкретной версии HAL окончательная проверка — исходник в своём проекте, а не пример для другой серии.
4. [PM0056, Cortex-M3 programming manual](https://www.st.com/resource/en/programming_manual/pm0056-stm32f10xxx20xxx21xxxl1xxxx-cortexm3-programming-manual-stmicroelectronics.pdf), Rev 7, December 2024. Stacks, vector table, exception priorities/grouping и PRIMASK. Используется в L01/L02; не заменяет datasheet выводов.
5. [ES096, medium-density device errata](https://www.st.com/resource/en/errata_sheet/es096-stm32f101x8b-stm32f102x8b-and-stm32f103x8b-mediumdensity-device-limitations-stmicroelectronics.pdf), Rev 15. Для L06: §2.6.5/2.6.6 ограничивают выводы по capture/overcapture flags; §2.3.10 предупреждает о сочетании USART1_TX/PA9 и TIM1_CH2 PWM. Поэтому TIM1_CH2 в курсе не используется. Для иной silicon revision проверяй applicability table.
6. [AN4776, general-purpose timer cookbook](https://www.st.com/resource/en/application_note/an4776-generalpurpose-timer-cookbook-for-stm32-microcontrollers-stmicroelectronics.pdf). Наглядное дополнение для timebase/PWM и измерения; разрешённые функции конкретного F103C8 всё равно определяются DS5319/RM0008.

## Исходники, опубликованные ST

- [stm32f1xx_hal.c](https://github.com/STMicroelectronics/stm32f1xx-hal-driver/blob/master/Src/stm32f1xx_hal.c): `HAL_InitTick`, `HAL_GetTick`, `HAL_Delay`; подтверждено предупреждение о tick priority при вызове Delay из ISR.
- [stm32f1xx_hal_uart.c](https://github.com/STMicroelectronics/stm32f1xx-hal-driver/blob/master/Src/stm32f1xx_hal_uart.c): Receive_IT, Transmit_IT, IRQ callbacks, AbortReceive, различие ORE и продолжаемых RX ошибок. Учебный адаптер намеренно использует одну IRQ-RX с одним байтом, без DMA.
- [stm32f1xx_hal_uart.h](https://github.com/STMicroelectronics/stm32f1xx-hal-driver/blob/master/Inc/stm32f1xx_hal_uart.h): типы, flags и HAL-макросы; не смешивать заголовок одной версии с драйвером другой.
- [stm32f1xx_hal_tim.c](https://github.com/STMicroelectronics/stm32f1xx-hal-driver/blob/master/Src/stm32f1xx_hal_tim.c): отдельные Init/Start, IC callback, PWM channel configuration и compare preload.
- [stm32f1xx_hal_iwdg.h](https://github.com/STMicroelectronics/stm32f1xx-hal-driver/blob/master/Inc/stm32f1xx_hal_iwdg.h): prescaler constants и `HAL_IWDG_Refresh`.

## Что является решением этого курса

Debounce 20 ms, polling 1 ms, UART FIFO 64 байта, строка 47 байт, лимит 32 байта на poll, рабочий capture loopback 20–2000 Hz, signal timeout 150 ms, health service 100 ms и ADC grace/deadline 300/500 ms — выбранные учебные контракты. Это **не** гарантированные пределы STM32 или параметры из datasheet. Их пригодность проверяется измерением и бюджетом конкретного приложения.

Ни один источник и ни один host-тест не подтверждает монтаж неизвестной Blue Pill, происхождение её МК или качество HSI на конкретном экземпляре. Аппаратная приёмка остаётся отдельной частью каждой лабораторной.
