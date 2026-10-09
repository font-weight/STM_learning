# Проверенные первоисточники

**Дата проверки: 2026-10-09.** В этом списке только документы производителя МК, производителей/разработчиков инструментов и официальные репозитории. Случайные Blue Pill pinout-картинки, форумы и видео не используются как основание для электрических пределов.

## Как читать источники

- **Datasheet** отвечает, какие выводы и электрические пределы есть у точного МК.
- **Reference manual** описывает регистры и поведение периферии. Он часто охватывает несколько разных подсемейств; проверяйте применимость.
- **Errata** описывает известные ограничения конкретной ревизии кристалла.
- **HAL source** показывает реальную реализацию API выбранной версии пакета.
- **Tool manual** объясняет текущий рабочий процесс, но не заменяет datasheet платы.

Ссылки ST могут сохранять адрес при обновлении PDF. Поэтому ниже указаны увиденные ревизии и названия разделов; при обновлении сверяйте оглавление. `latest` — изменяемый адрес, а не зафиксированная версия вашей среды.

## МК и аппаратная часть

<a id="s1"></a>
### S1. DS5319: STM32F103x8 / STM32F103xB

[Официальный datasheet STM32F103C8](https://www.st.com/resource/en/datasheet/stm32f103c8.pdf). Проверен **Rev 20, July 2025**.

Где смотреть:

- §2.1 / таблица 2: память и периферия варианта.
- §3 / таблица 5: выводы, альтернативные функции, FT; примечание 5 — ограничения PC13–PC15.
- §§5.2–5.3: absolute maximum ratings отдельно от рабочих условий.
- §5.3.13: электрические характеристики GPIO и условия FT.
- §5.3.18: ADC и связь VREF с аналоговым питанием.
- §7: схема обозначения заказа.

Используется в SAFETY, выборе C8/CB и аналоговых лабораториях. Это datasheet **кристалла**, не схема каждого экземпляра Blue Pill.

<a id="s2"></a>
### S2. RM0008: STM32F10xxx reference manual

[Официальный RM0008](https://www.st.com/resource/en/reference_manual/rm0008-stm32f101xx-stm32f102xx-stm32f103xx-stm32f105xx-and-stm32f107xx-advanced-armbased-32bit-mcus-stmicroelectronics.pdf). Проверен **Rev 21, February 2021**; PDF получен непосредственно с ST и текст прочитан локально, поскольку он велик для некоторых web-просмотрщиков.

Для medium-density F103:

- §3.3: Flash access / latency; §3.4: Boot configuration.
- **Глава 7**: low-/medium-/high-/XL-density RCC; §7.2 и рисунок clock tree; §§7.2.1–7.2.3 HSE, HSI, PLL. Не подменять главой connectivity line.
- Глава 9: GPIO/AFIO, альтернативные функции и SWJ configuration.
- Главы EXTI, DMA, ADC, TIM1, TIM2–TIM5, IWDG, SPI, USART: искать название периферии и нужный регистр по оглавлению.

Источник общего дерева частот курса и удвоения TIM clock при APB divider, отличном от `/1`.

<a id="s3"></a>
### S3. AN2586: аппаратная разработка STM32F10xxx

[Getting started with STM32F10xxx hardware development](https://www.st.com/resource/en/application_note/an2586-getting-started-with-stm32f10xxx-hardware-development-stmicroelectronics.pdf). Проверен **Rev 8**.

Разделы: питание и reset; §4.1–4.3 Boot configuration; §5.3, таблица 3 — PA13/SWDIO и PA14/SWCLK. Используется для подключения и восстановления. Примеры eval-плат не являются схемой Blue Pill.

<a id="s4"></a>
### S4. AN2606: системный ROM-загрузчик

[Introduction to system memory boot mode on STM32 MCUs](https://www.st.com/resource/en/application_note/an2606-stm32-microcontroller-system-memory-boot-mode-stmicroelectronics.pdf). Проверен **Rev 70, February 2026**.

Применимый раздел: **§21, STM32F10xxx devices**, таблица 45 и таблица версий загрузчика. Для C8/CB используется USART1; раздел F105/F107 находится отдельно. Основание ограниченной UART-ветки в DEBUGGING. Набор интерфейсов всего CubeProgrammer не означает, что все они есть в ROM каждого МК.

## Генерация и редактор

<a id="s5"></a>
### S5. UM1718 / CubeMX: генерация проекта

[UM1718 PDF](https://www.st.com/resource/en/user_manual/um1718-stm32cubemx-for-stm32-configuration-and-initialization-c-code-generation-stmicroelectronics.pdf), проверен **Rev 51**.

[Онлайн-раздел 4 документации CubeMX 6.18.1](https://dev.st.com/stm32cube-docs/stm32cubemx/6.18.1/en/docs/markup/CubeMX_UserManual/chapters/04_4_stm32cubemx_user_interface.html): §4.11 Project Manager; §4.11.1 Project tab; §4.11.2 Code Generator. Здесь подтверждены CMake, выбор GCC/Starm-Clang, Makefile и сохранение пользовательских секций.

[Раздел 6: C code generation overview](https://dev.st.com/stm32cube-docs/stm32cubemx/6.18.1/en/docs/markup/CubeMX_UserManual/chapters/06_6_stm32cubemx_c_code_generation_overview.html). Используется для границы между generated и пользовательским кодом.

На дату проверки redirect официального портала вёл на **6.18.1**; это фиксирует просмотренную документацию, а не объявляет её универсальной «проверенной сборкой» курса.

<a id="s6"></a>
### S6. Какой CubeMX нужен STM32F1

[STM32CubeMX: supported series и FAQ](https://www.st.com/content/st_com/en/stm32cubemx.html). Проверены блок «STM32 series supported» и вопросы о различии CubeMX/CubeMX2. F1 указан у CubeMX; разделение связано с HAL1/HAL2.

<a id="s7"></a>
### S7. ST VS Code: установка и требования

- [Installation](https://dev.st.com/stm32cube-docs/stm32cubeide-vscode/latest/en/docs/markup/getting_started/installation.html): установка официального расширения, отдельная установка драйверов пробника.
- [System requirements](https://dev.st.com/stm32cube-docs/stm32cubeide-vscode/latest/en/docs/markup/introduction/system_requirements.html): поддерживаемые ОС и архитектуры на дату проверки.

Не считайте эти страницы обещанием поддержки любой старой ОС или любого USB-адаптера.

<a id="s8"></a>
### S8. Почему CubeCLT больше не обязателен для нового расширения

[Migrating from extension 2.x to 3.x](https://dev.st.com/stm32cube-docs/stm32cubeide-vscode/latest/en/docs/markup/tutorials/migration.html). Подтверждены новая архитектура, отсутствие обязательной отдельной CLT-установки и возможные конфликты старых расширений. Наименование поколения взято из документации ST; не является номером установленного у читателя пакета.

<a id="s9"></a>
### S9. Пример пробника: STLINK-V3MINIE

[UM2910](https://www.st.com/resource/en/user_manual/um2910-stlinkv3minie-debuggerprogrammer-tiny-probe-for-stm32-microcontrollers-stmicroelectronics.pdf). Проверен **Rev 5**; §6, таблицы 3–4. `T_VCC` указан как input. Это доказательство для этой модели, а не универсальное утверждение о любом контакте «3.3V» на любом пробнике.

<a id="s10"></a>
### S10. CMake-проект CubeMX в VS Code

[First project creation](https://dev.st.com/stm32cube-docs/stm32cubeide-vscode/latest/en/docs/markup/getting_started/first_project_creation.html). Разделы «Import STM32CubeMX project» и «Open in VS Code»: CMake, открытие папки, preset, Discover STM32Cube project. Основной первоисточник маршрута TOOLCHAIN.

<a id="s11"></a>
### S11. Отладка собственным адаптером ST

[ST VS Code: Debug](https://dev.st.com/stm32cube-docs/stm32cubeide-vscode/latest/en/docs/markup/development/debug.html). Разделы «Debug launch», «Configuring debug sessions with launch.json», «Debugging a running target»; также предупреждение о сетевой доступности GDB server. Не путать формат ST adapter с Cortex-Debug.

## Сборка и запись

<a id="s12"></a>
### S12. STM32CubeCLT

[Официальная страница STM32CubeCLT](https://www.st.com/en/development-tools/stm32cubeclt.html). Разделы Description / All features: состав и роль CLI-набора. В курсе используется только как альтернативный способ организации инструментов.

<a id="s13"></a>
### S13. STM32CubeProgrammer CLI

[MCU command lines, документация 2.23.0](https://dev.st.com/stm32cube-docs/prog/2.23.0/en/docs/markup/CubeProg_Command_Lines.html). Проверены `-connect`, SWD `freq`/`mode=UR`, аппаратный reset, `-write`, `-verify`, `-rst`; единицы SWD-частоты — кГц. Для `-v` важно положение после write. Команды в TOOLCHAIN — примеры для собственных файлов и одного выбранного пробника, не результат реального программирования при подготовке курса.

<a id="s14"></a>
### S14. OpenOCD: программирование Flash

[OpenOCD User’s Guide: Flash Programming](https://openocd.org/doc/html/Flash-Programming.html). Проверена команда `program` с `verify`, `reset`, `exit` и необходимость адреса для raw binary. Смотрите руководство именно установленного релиза: ветка `/doc/html/` может отражать более новую разработку.

<a id="s15"></a>
### S15. OpenOCD: драйвер ST-LINK и target

- [Release manual: Debug Adapter Configuration](https://openocd.org/doc-release/html/Debug-Adapter-Configuration.html): разделы `st-link`, HLA и выбор транспорта.
- [Интерфейсный скрипт ST-LINK в официальном теге v0.12.0](https://github.com/openocd-org/openocd/blob/v0.12.0/tcl/interface/stlink.cfg) и [его текущая версия master](https://github.com/openocd-org/openocd/blob/master/tcl/interface/stlink.cfg): проверено различие HLA и прямого драйвера; пример в TOOLCHAIN явно обусловлен HLA.
- [Официальный target script stm32f1x.cfg](https://github.com/openocd-org/openocd/blob/master/tcl/target/stm32f1x.cfg).

Используется для предупреждения о несовместимых интерфейсных скриптах разных поколений. `master` — справочная изменяемая ветка, а не закреплённая зависимость курса.

<a id="s16"></a>
### S16. CMake presets

[CMake: cmake-presets(7)](https://cmake.org/cmake/help/latest/manual/cmake-presets.7.html). Разделы Introduction, Configure Preset, Build Preset, Versions. Подтверждает, что configure preset и build preset — разные сущности; локальный `CMakeUserPresets.json` не следует сохранять как общую машинно-независимую конфигурацию.

<a id="s17"></a>
### S17. Драйвер ST-LINK для Windows

[STSW-LINK009](https://www.st.com/en/development-tools/stsw-link009.html). Раздел Description содержит различия требований для V2/V2-1 и V3. Используется вместо неофициальных драйверных архивов.

<a id="s18"></a>
### S18. Точная цель C8

[STM32F103C8 product page](https://www.st.com/en/microcontrollers-microprocessors/stm32f103c8.html). Официальный объём C8 — 64 Kbytes Flash. Для соседнего CB характеристики проверяются отдельно по DS5319; название семейства «up to 128 Kbytes» не увеличивает объём конкретного C8.

<a id="s19"></a>
### S19. STM32CubeF1 и реализация HAL

[Официальный STM32CubeF1](https://github.com/STMicroelectronics/STM32CubeF1). README описывает структуру пакета; исходники и submodules позволяют перейти к точной версии HAL/CMSIS. Для воспроизводимости записывайте release/tag/commit своего пакета. Пример для другой ST-платы не переносится на Blue Pill без проверки выводов и clock tree.

<a id="s20"></a>
### S20. Поддерживаемые форматы CubeProgrammer

[STM32CubeProgrammer product page](https://www.st.com/en/development-tools/stm32cubeprog.html). Раздел All features подтверждает ELF, HEX и binary, GUI/CLI и разные классы интерфейсов. Конкретную доступность ROM-интерфейса МК проверяйте по AN2606.

<a id="s21"></a>
### S21. CMake Tools в VS Code

[Microsoft: Get started with CMake Tools](https://code.visualstudio.com/docs/cpp/cmake-linux). Разделы «Prerequisites», «Configure using CMake Presets», «Build». Используется для различения редактора, build tools и configure/build. Desktop-пример Microsoft не является подходящей Cortex-M3 конфигурацией сам по себе.

<a id="s22"></a>
### S22. Текущая архитектура STM32CubeIDE for VS Code

- [ST: Release note](https://dev.st.com/stm32cube-docs/stm32cubeide-vscode/latest/en/docs/markup/introduction/release_note.html), раздел Breaking changes: bundle manager, CLI, данные устройств, собственный debug adapter.
- [Официальный пакет ST в Visual Studio Marketplace](https://marketplace.visualstudio.com/items?itemName=stmicroelectronics.stm32-vscode-extension): проверены издатель/ID и описание функций.

## Native host-инструменты для упражнений

<a id="s23"></a>
### S23. MSYS2 UCRT64 для Windows x64

- [Getting Started](https://www.msys2.org/), раздел Installation: установка и native GCC.
- [Environments](https://www.msys2.org/docs/environments/): UCRT64, архитектуры и PATH.
- [Updating MSYS2](https://www.msys2.org/docs/updating/): поддерживаемая процедура обновления перед добавлением пакетов.
- Официальные карточки [GCC UCRT64](https://packages.msys2.org/packages/mingw-w64-ucrt-x86_64-gcc), [GNU Make](https://packages.msys2.org/packages/make) и [Python UCRT64](https://packages.msys2.org/packages/mingw-w64-ucrt-x86_64-python): проверены имена пакетов и наличие `python3.exe`.

Документы просмотрены 2026-10-09. Это проверка инструкции и состава инструментов; Windows-прогон курса не выполнялся.

<a id="s24"></a>
### S24. Native compiler и Python в Ubuntu

Официальные пакеты Ubuntu 24.04 LTS: [build-essential](https://packages.ubuntu.com/noble/build-essential), [python3](https://packages.ubuntu.com/noble/python3). Используются как конкретный Linux-пример. Для другого дистрибутива выбирайте его официальный репозиторий и повторяйте проверку версий.

<a id="s25"></a>
### S25. macOS: Apple tools и Python

[Apple: Command Line Tools FAQ, TN2339](https://developer.apple.com/library/archive/technotes/tn2339/_index.html), разделы «What is the Command Line Tools Package?» и «Install ... via the Terminal application»: Clang и `xcode-select --install`. Это архивный официальный документ; актуальную совместимость пакета определяет установщик Apple.

[Python: Using Python on macOS](https://docs.python.org/3/using/mac.html), §5.1: официальный installer и предостережение не удалять Apple-controlled Python. Mac-прогон курса не выполнялся.

<a id="s26"></a>
### S26. Node.js для сопровождающего сайта

[Официальная загрузка Node.js](https://nodejs.org/en/download): выбор поддерживаемого LTS под ОС и архитектуру. Node нужен для JavaScript-тестов сайта; готовый offline-сайт работает без его установки.

<a id="s27"></a>
### S27. PM0056: Cortex-M3, начальные векторы

[STM32F10xxx/20xxx/21xxx/L1xxxx Cortex-M3 programming manual](https://www.st.com/resource/en/programming_manual/pm0056-stm32f10xxx20xxx21xxxl1xxxx-cortexm3-programming-manual-stmicroelectronics.pdf). Проверен **Rev 7, December 2024**.

§2.3.4 и рисунок 12: первое слово таблицы — начальный SP, второе — reset; младший бит адреса обработчика обозначает Thumb. Используется для ограниченной проверки байтов ELF. Это не спецификация формата ELF и не доказательство корректности программы. §4.5 отдельно описывает остановку счётчика SysTick при halt ядра.

## Как разрешены расхождения документации

Некоторые общие страницы ST о Build ещё описывают Makefile-подобные действия и каталоги, тогда как руководство импорта и карточка текущего расширения описывают CMake. В курсе маршрут построен по **конкретному руководству импорта CMake** и реальным сгенерированным preset/пути из лога, а не по предположению, что все страницы обновлены одновременно.

Схему конкретной Blue Pill и происхождение установленного МК удалённая проверка документов не устанавливает. Полярность LED, маркировку кварца, питание и разъём пробника требуется подтвердить на своём стенде.

## Уровень проведённой проверки

- Проверены официальные документы, адреса источников и применимость ключевых ограничений к STM32F103x8/xB.
- Локальные ссылки/якоря, структура материалов и C-вставки проверяются отдельно от firmware. Текущие результаты всего комплекта приведены в [VALIDATION](../VALIDATION.md). Необязательный [checker файлов цели](../tools/README-project-check.md) имеет синтетические положительные и отрицательные тесты; они подтверждают поведение checker, а не наличие собранной ARM-прошивки.
- **Не выполнялись физические испытания Blue Pill, измерения осциллографом, прошивка ST-LINK, запуск реальной SWD-сессии или end-to-end генерация и сборка CubeMX-проекта в пользовательской среде.**
- Проверка синтаксиса на desktop GCC не доказывает ARM-сборку, размещение памяти, своевременность IRQ, отсутствие электрической ошибки или точность HSI. Лабораторная приёмка нужна именно для этого.

При обнаружении проблемы добавляйте к отчёту свою версию инструмента, точный шаг, лог и минимальное воспроизведение. Обновление источника или инструмента не должно молча изменять уже зафиксированный учебный результат.
