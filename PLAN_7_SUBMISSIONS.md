# ARC Prize 2026 — стратегия и спринт на 7 валидных сабмитов

Редакция протокола: 2026-09-07. Исторические числа ниже относятся к 2026-09-05; актуальное сохранённое состояние находится в `experiment_state.json`.

## Изменение из-за дефицита Kaggle GPU

Подробный действующий протокол: [EXTERNAL_COMPUTE_PLAN.md](EXTERNAL_COMPUTE_PLAN.md). При противоречии он заменяет прежнее требование полного public25 в Kaggle Phase A.

S1=2.71 и S2=2.72 уже отклонены; S3 v6/ref 56075811 в сохранённом состоянии ожидает score. Новые номера не начинаем заново. Следующие задачи: P0 (короткая Phase A, переносимый harness и внешняя validation), затем **S4 → S6 → S7 → S5**. P0 не расходует LB submission. Этот документ обновлён как план; migration code и удалённый inference ещё не реализованы.

Каждый из трёх public25 Save & Run занимал около 2 ч 22 мин; всего 7.09 часа до Phase B. Переносим такие расчёты на NSU. Цель Kaggle smoke — 20–30 минут вместе с cold start, затем штатный скрытый rerun. Не считать proxy-модель на A100 точной копией Flash/Blackwell.

## Коротко о competition

ARC-AGI-3 — интерактивный benchmark: агент без инструкции видит последовательность цветных 2D-кадров, выбирает дискретные действия/клики, сам выводит правила игры и должен пройти несколько уровней. Важна не только успешность, но и экономность действий: вклад уровня примерно пропорционален `(human_actions / agent_actions)^2`, а поздние уровни весят больше ранних.

- 25 открытых игр; 110 скрытых игр разделены между Public и Private Leaderboard (55 + 55).
- Финальный результат определяется Private Leaderboard; можно выбрать два финальных сабмита.
- Notebook запускается без интернета, лимит CPU/GPU — 9 часов.
- Фактический лимит аккаунта и текущие rules/API: 1 leaderboard submission в сутки. В README starter-kit всё ещё встречается устаревшее значение 5/day.
- Для призового результата понадобятся открытые код, веса и воспроизводимые материалы.
- Ближайший milestone deadline — 2026-09-30 23:59 UTC; финальный deadline — 2026-11-02 23:59 UTC.

Полезные первоисточники: [competition overview](https://www.kaggle.com/competitions/arc-prize-2026-arc-agi-3/overview), [data](https://www.kaggle.com/competitions/arc-prize-2026-arc-agi-3/data), [rules](https://www.kaggle.com/competitions/arc-prize-2026-arc-agi-3/rules), [code requirements](https://www.kaggle.com/competitions/arc-prize-2026-arc-agi-3/overview/code-requirements), [timeline](https://www.kaggle.com/competitions/arc-prize-2026-arc-agi-3/overview/timeline), [leaderboard](https://www.kaggle.com/competitions/arc-prize-2026-arc-agi-3/leaderboard), [RHAE methodology](https://docs.arcprize.org/methodology), [official starter](https://github.com/arcprize/ARC-AGI-3-Kaggle-Starter), [technical report](https://arcprize.org/media/ARC_AGI_3_Technical_Report.pdf).

## Где мы сейчас и что означает «золото»

- Лучший наш Public LB: **3.39**, текущая позиция на снимке — около **92**.
- Один и тот же Flash v3 дал **3.39** и **2.95**. Значит, одиночное изменение меньше примерно 0.5 нельзя считать доказанным улучшением.
- На снимке: лидер — около **7.51**, третье место — **6.43**, граница top-15 — около **4.29**.
- При числе команд свыше 1000 Kaggle gold — примерно `top 10 + 0.2% команд`, сейчас это ориентировочно top-15/16. Это медаль, не обязательно первое место. Денежное первое место определяется Private LB; отдельный grand prize требует 100%.

До текущей публичной границы золота не хватает всего около 0.9 пункта, но оптимизироваться только под Public опасно: скрытый Private набор специально проверяет перенос на новые игры. Рабочая цель спринта — не «случайно пересечь 4.29», а получить воспроизводимый результат **6+** и два различающихся финальных кандидата.

Для золота нужны:

1. Сильная офлайн-модель и надёжный inference stack, помещающийся в Kaggle GPU.
2. Память о подтверждённых правилах и перенос знаний между уровнями без переноса случайных координат.
3. Семантическое сравнение кадров: отличать прогресс от таймера/HUD/анимации и не повторять бесполезные действия.
4. Экономные действия: штраф квадратичный, поэтому бессмысленные шаги очень дороги.
5. Планировщик 9-часового бюджета по 110 играм: сначала охватить все, затем тратить остаток на перспективные игры и поздние уровни.
6. Контролируемые абляции и полный журнал. Публичный score шумный, поэтому нельзя складывать неподтверждённые правки.

## Ресурсы для разработки

Текущий компьютер: RTX 2060 6 GB, 31.8 GB RAM, 12 логических CPU; свободно примерно 205 GB на C:, 272 GB на D:, 1.4 TB на E:.

| Режим | VRAM | RAM | SSD | Что реально делать |
|---|---:|---:|---:|---|
| Официальный engine, unit/replay tests | не нужна | 8–16 GB | <10 GB | Полная локальная разработка логики и проверка протокола |
| Комфортная CPU-разработка и хранение трасс | 0–6 GB | 32 GB | 20–50 GB | Подходит текущий ПК |
| 7–8B, 4-bit | 12–24 GB | 32–64 GB | 50–100 GB | Локальные эксперименты с небольшой моделью |
| 27B, 4-bit / FP8 | 24–32 / 48–96 GB | 64–192 GB | 100–200 GB | Уже нужен мощный GPU/workstation |
| Текущий Qwen3.8-Flash NVFP4 (~135 GB файлов) | около 96 GB | 128–192+ GB | 250–350 GB свободного быстрого SSD | Аналог текущего Kaggle G4: RTX PRO 6000 Blackwell 96 GB + CPU offload |

Вывод: покупать GPU не нужно. Доступны Quadro RTX 6000 24 GB, RTX 3080 10 GB и 2×A100 80 GB (Linux-хосты имеют около 251 GiB RAM). Основной внешний стенд — одна A100; pair allocation только для явно поддерживаемого distributed Flash. Подробности совместимости, дисковые бюджеты и незавершённая настройка общей очереди — в EXTERNAL_COMPUTE_PLAN.md. Kaggle Phase A больше не используется для полного public25 по умолчанию.

Ориентиры по железу: [Google G4 machine types](https://docs.cloud.google.com/compute/docs/accelerator-optimized-machines#g4_machine_types), [RTX PRO 6000 Blackwell specifications](https://www.nvidia.com/en-us/data-center/rtx-pro-6000-blackwell-server-edition/), [ARC local vs online guide](https://docs.arcprize.org/local-vs-online).

Технически разработка возможна полностью вне личного ПК. Для текущего спринта CPU-тесты выполняем локально, публичные rollouts — на внешнем GPU, короткую проверку финального окружения — на Kaggle. Внешняя модель служит только подготовке: скрытый агент вычисляет действия заново внутри Kaggle без сети.

## Базовая линия

Текущий champion: приватный notebook `dmitriigluzdov/duck-qwen3-8-flash-next-nvfp4-mtp`, version 3, модель `keithtyser/qwen3-8-flash-next-nvfp4/PyTorch/radixark-modelopt-fp4/1`, лучший submission ref `55959595`, score 3.39.

Уже присутствуют image + ASCII/segmentation, Python REPL, structured memory, batching действий, MTP3 и CPU offload. Поэтому не переписываем агент целиком. LCLD пока исключён: 0.00 и Phase B errors. GPT-OSS-120B исключён: около восьми часов на публичном прогоне и низкое покрытие. Копии публичных Flash-notebooks с более высоким одиночным score без причинной разницы не считаем улучшением.

## Протокол эксперимента (обновлён 2026-09-07)

Каждый S-ID означает отдельную гипотезу, а не обязательный календарный день или расход лимита. Порядок задаёт `execution_policy.experiment_order`. При ERROR текущая попытка остаётся на диагностике; новая отправка требует следующего разрешения пользователя. Кандидат, не прошедший внешнюю validation, получает `deferred_local`: дневной лимит на него не тратим, рассматриваем следующую гипотезу по очереди.

Для S2–S7 родитель — текущий champion, а не автоматически предыдущий эксперимент. В одном сабмите меняется ровно одна гипотеза. Телеметрия, тесты и исправление очевидной упаковочной ошибки не считаются второй гипотезой.

Перед Phase B обязательно:

1. локальные unit/smoke/replay-тесты и внешнее сравнение с родителем по EXTERNAL_COMPUTE_PLAN.md;
2. проверка допустимых action IDs и offline-only зависимостей;
3. успешный короткий Kaggle smoke / Phase A с реальной загрузкой checkpoint и несколькими действиями, без полного public25; offline_eval вынесен на NSU;
4. фиксация parent version, diff/hash, seed и inference config;
5. только после явной команды пользователя — ровно один Phase B submission.

Правило решения после score: фиксировать delta к parent и historical best, но решение опирать также на paired validation, coverage, actions/tokens и runtime. Старый порог ±0.50 получен из слишком малого числа повторов и служит сигналом перепроверки, не доказательством значимости. Повышать champion только при согласующихся свидетельствах внешней проверки и LB, без новых runtime failures; при расхождении — `inconclusive`. Исторические решения S1/S2 сохраняем. ERROR/OOM/timeout диагностировать отдельно.

## План семи сабмитов

Таблица сохраняет исходные гипотезы и их IDs. S1/S2 уже завершены, S3 отправлен; оставшиеся выполняются в порядке S4 → S6 → S7 → S5 по внешнему протоколу, только после прохождения отбора.

| ID | Единственное изменение | Гипотеза и критерий |
|---|---|---|
| **S1 — Deterministic control** | Заменить `seed=-1` на стабильный воспроизводимый per-game seed; добавить read-only telemetry с config/hash/runtime. Другую policy не менять. | Получить контролируемую базу и уменьшить разброс 3.39↔2.95. Принять как экспериментальную основу, если Phase A воспроизводим и нет заметной потери coverage/runtime. |
| **S2 — Memory capture fix** | Structured-memory extractor читает размеченные факты и из `reasoning`, и из `content`, с прежними лимитами длины. | Сейчас полезные world/goal/action facts из reasoning могут теряться. Unit tests должны доказать capture, dedup и caps. Сравнивать с champion. |
| **S3 — Cross-level transfer** | На переходе уровня сохранять только подтверждённые controls, action effects и goal invariants; очищать координаты, layout и текущий план. | Поздние уровни дороже и обычно развивают ту же механику. Нужны тесты, что универсальные факты остаются, а layout-specific данные исчезают. |
| **S4 — Semantic no-impact guard** | Считать diff без монотонных полос HUD/timer; запоминать `(semantic_state, action)` как no-impact после подтверждённого повторения и сообщать это модели. Не делать безусловный глобальный ban. | Снизить повторы действий, меняющих только HUD. Проверить на синтетических timer-only, animation и real-change кадрах. Это наиболее сильная внешне подтверждённая гипотеза недели. |
| **S5 — Animation-aware observation** | Передавать full actionable frame плюс компактную последовательность последних animation frames; явно маркировать, где анимация, а где новое состояние. Другую память/policy не менять. | Модель перестанет планировать по промежуточному кадру и увидит причинный эффект действия. Ограничить изображения/токены, чтобы не потерять throughput. |
| **S6 — Scheduled simplification** | Периодически сворачивать длинный transcript в verified facts, disproved hypotheses, open questions и current plan; держать около 8 последних assistant turns вместо 30. | Освободить context/KV-cache и уменьшить зацикливание без полной исполняемой world model. Gate: не меньше обработанных игр и не хуже soft-deadline margin. |
| **S7 — Adaptive compute scheduler** | На основе semantic progress/stuck signals ограничивать время на безнадёжно застрявшие игры, сначала гарантировать обслуживание всех 110, затем отдавать остаток прогрессирующим играм и поздним уровням. | Повысить coverage в пределах 9 часов. Родитель — лучший подтверждённый champion после S1–S6; никаких новых prompt/memory изменений. |

Не включать в этот спринт generic state graph: доступная абляция показала регрессию. ACTION7/API-completeness оставить в backlog отдельным экспериментом после проверки, что action действительно объявлен gateway; не смешивать с S5.

Основания для выбранных направлений: [официальный разбор Milestone 1](https://arcprize.org/blog/arc-prize-2026-milestone-1), [открытые Duck ablations](https://github.com/sonpham-org/arc-3), [Schema paper](https://arxiv.org/abs/2607.15439), [NVIDIA AVO report](https://developer.nvidia.com/blog/nvidia-avo-reaches-100-on-arc-agi-3-demonstrating-a-frontier-level-general-purpose-architecture-for-long-horizon-autonomous-agents/).

## Что записывать после каждого запуска

Обновить `experiment_state.json` и добавить запись в `reports/EXPERIMENT_LOG.md`:

- дата UTC и local, experiment ID, parent champion и hashes;
- точный causal diff;
- model/checkpoint/license, seed, temperature/top_p, context, concurrency, budgets;
- локальные тесты и публичная Phase A: игры/уровни/actions, runtime, failures, OOM margin;
- Kaggle kernel slug/version, submission ref, terminal status и score;
- team rank/teams, leader score и текущая граница gold;
- delta к parent и historical best;
- классификация `algorithmic`, `infrastructure` или `inconclusive`;
- решение `adopt`, `reject`, `repeat`; какой ID следующий.

После завершения оставшегося спринта анализируем score, coverage, action efficiency, later-level completions, runtime и failures вместе с затратами Kaggle/NSU. Финальными кандидатами должны стать два технически стабильных, по возможности различающихся решения с воспроизводимыми отчётами.
