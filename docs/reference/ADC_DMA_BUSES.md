# Проверка оснований: ADC, DMA, I2C, SPI и хранение

Проверка источников: 9 октября 2026. Конфигурации курса относятся к **STM32F103C8Tx, STM32CubeF1, обычному HAL1**, не ко всем STM32. Blue Pill не является стандартной платой ST; документация MCU не подтверждает разводку или происхождение конкретного модуля.

## Что читать для конкретного вопроса

| Вопрос | Первичный источник и место |
|---|---|
| Каналы, regular rank, sample time, legal trigger | [RM0008 Rev 21](https://www.st.com/resource/en/reference_manual/rm0008-stm32f101xx-stm32f102xx-stm32f103xx-stm32f105xx-and-stm32f107xx-advanced-armbased-32bit-mcus-stmicroelectronics.pdf), глава ADC; table 67: TIM3_TRGO для ADC1/2 regular, EXTSEL=100 |
| DMA1 request mapping | RM0008, table 78: ADC1 → Channel 1; глава DMA: circular, CNDTR, half/full flags |
| Пределы ADC, входной источник, память C8 | [DS5319 Rev 20 / STM32F103x8/xB](https://www.st.com/resource/en/datasheet/stm32f103c8.pdf), pin definitions и ADC characteristics; Flash/RAM по точному part number |
| Архитектура и usage HAL | [UM1850](https://www.st.com/resource/en/user_manual/dm00154093-description-of-stm32f1-hal-and-lowlayer-drivers-stmicroelectronics.pdf), главы ADC, DMA, SPI, I2C, UART |
| Калибровка F1: один аргумент, до Start | [ST HAL ADCEx source](https://github.com/STMicroelectronics/stm32f1xx-hal-driver/blob/master/Src/stm32f1xx_hal_adc_ex.c), `HAL_ADCEx_Calibration_Start` |
| ADC external-trigger API и число rank | [ST HAL ADC header](https://github.com/STMicroelectronics/stm32f1xx-hal-driver/blob/master/Inc/stm32f1xx_hal_adc.h), `ADC_InitTypeDef`; [ADCEx header](https://github.com/STMicroelectronics/stm32f1xx-hal-driver/blob/master/Inc/stm32f1xx_hal_adc_ex.h), `ADC_EXTERNALTRIGCONV_T3_TRGO` |
| I2C address shift и отдельные timeout paths | [ST HAL I2C source](https://github.com/STMicroelectronics/stm32f1xx-hal-driver/blob/master/Src/stm32f1xx_hal_i2c.c), аргумент `DevAddress`, `HAL_I2C_Mem_Read`, `HAL_I2C_IsDeviceReady` |
| Завершение SPI full-duplex transfer | [ST HAL SPI source](https://github.com/STMicroelectronics/stm32f1xx-hal-driver/blob/master/Src/stm32f1xx_hal_spi.c), `HAL_SPI_TransmitReceive` |
| Таймерные triggers и F1 I2C caveats | [ES096 Rev 15](https://www.st.com/resource/en/errata_sheet/es096-stm32f101x8b-stm32f102x8b-and-stm32f103x8b-mediumdensity-device-limitations-stmicroelectronics.pdf), §2.6.2; §2.8.5 repeated START; §2.8.7 BUSY/analog filter |
| LIS3DH address, ID, режим и burst | [LIS3DH datasheet](https://www.st.com/resource/en/datasheet/lis3dh.pdf), §§6.1–6.2; WHO_AM_I, CTRL_REG1/4, OUT registers |
| Cortex-M3 cycle counter и маски | [Arm CMSIS core_cm3.h](https://github.com/ARM-software/CMSIS_5/blob/develop/CMSIS/Core/Include/core_cm3.h), DWT/CoreDebug |
| Flash page/program/erase restrictions | [PM0075](https://www.st.com/resource/en/programming_manual/pm0075-stm32f10xxx-flash-memory-microcontrollers-stmicroelectronics.pdf), §§1.2 и 2.3; endurance отдельно в даташите |

Ссылки HAL на `master` могут меняться. В реальном проекте запиши версию STM32CubeF1 и проверь именно поставленные в него `.h/.c`. Не заменяй API локальной версии кодом из более нового семейства или ветки.

## Что является выбором этого курса

HSI 8 МГц; ADC clock 4 МГц; TIM3 PSC=7/ARR=999; ADC sample time 55.5 cycles; half-block 100; DMA length 200; I2C 80 кГц; SPI1 mode 0 и prescaler 32 для loopback — это конкретный учебный стенд. Применимость выбранных peripheral routes сверена с первичными источниками, но параметры не объявляются единственно правильными для любого устройства.

Однослотовый копирующий mailbox, drop-newest, stop-on-DMA-deadline-fault, sequence, fixed-point CSV и main-only очередь восьми **сводок** — учебный дизайн. Они не являются гарантией производителя и требуют своих измерений.

Численные ориентиры в миссиях тоже учебные: ADC 2% полной шкалы для грубой диагностики; отношение длительностей SPI 1,9…2,1; LIS3DH около ±1 g с широким диагностическим коридором; cadence 100±5 мс и пороги достаточности CSV. Это не новые характеристики микросхем. Бумажные трассы, входные байты и тестовые данные помечены синтетическими; их нельзя сдавать вместо аппаратного опыта.

## Границы проверки готовых материалов

- Проверены первичные источники и согласованность pin/clock/API контрактов
- Host C: строгая компиляция starter; oracle проходит шесть усиленных контрактов, включая mixed-trace и срок жизни копии; начальный starter намеренно RED
- Проверка чувствительности: шесть отдельно скомпилированных синтетических мутаций oracle отвергнуты нужными тестами; компиляционная ошибка/краш не считаются успешным обнаружением
- AddressSanitizer и UBSan для oracle прошли с выключенным LeakSanitizer, который недоступен в проверочной среде; утечки этим не проверены
- Python CSV checker: 36 синтетических тестов формата, диапазонов, reset/session, wrap, потерь, повреждённых строк, CLI и необязательных требований к длительности/числу строк/cadence
- **Полная ARM-сборка приведённых HAL-фрагментов: не выполнялась**
- **Прошивка, ADC/DMA, UART, SPI/I2C, timing и Flash на физической плате: NEVER RUN / не выполнялись**

Поэтому не ставь себе аппаратный gate на основании зелёных host-тестов. Точные команды релизной и учебной проверки разделены в [README упражнения](../../examples/host-buffering/README.md); работа с реальным capture — в [инструкции checker](../../tools/README-capture.md).
