# ARC Prize 2026 — стратегия residual value

Редакция протокола: 2026-09-08. Исторические числа ниже относятся к 2026-09-05; актуальное сохранённое состояние находится в `experiment_state.json`.

## Главный критерий (с 2026-09-08)

Перед любой тратой дневного LB-слота, длинного Kaggle GPU или аренды A100:

> Что проверенное останется после этого запуска, даже если Public score не вырастет?

Полный протокол: [COMMUNITY_TRACK.md](COMMUNITY_TRACK.md). При противоречии с «надо потратить сабмит / догнать золото форком» действует он.

Не клонируем чужие открытые notebooks как работу. Не гоняем S4–S7 по календарю. Датасет и writeup **сначала локальные черновики**. Открытая публикация на Kaggle — только после COMPLETE Phase B этого метода со score > 0.03 и отдельной фразы `опубликовать для сообщества`. S4 / 3.70 открывает eligibility, но не публикацию.

Очередь: **C1 локальный датасет → C2 локальный черновик writeup → C4 проверка на LB (S4 COMPLETE; S4b rejected; далее S6) → решение о публикации**. C3 LoRA — параллельно после честного FP8, тоже без public release до фразы. Harness S5/S7 — backlog.

S1=2.71, S2=2.72, S3=2.77, S4b=2.77 отклонены. Working champion — **S4 / 3.70** (parent Flash v3 3.39, delta +0.31). S6 Phase B **PENDING** ref 56137205. Native FP8 27B ещё сломан. C1/C2 eligible, но пользователь 2026-09-10: 3.70 не заметный для публикации.

## Изменение из-за дефицита Kaggle GPU

Подробный compute-протокол: [EXTERNAL_COMPUTE_PLAN.md](EXTERNAL_COMPUTE_PLAN.md). При противоречии он заменяет прежнее требование полного public25 в Kaggle Phase A.

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

## Где мы сейчас (медаль — факт доски, не критерий отбора)

- Лучший наш Public LB: **3.70** (S4). Serving-only Flash v3: **3.39** и unlucky repeat **2.95**. Одиночное изменение меньше примерно 0.5 нельзя считать доказанным улучшением; S4 +0.31 принят как working champion по решению 2026-09-09. S4b outer HUD **2.77** (ref 56122822) отклонён (−0.93).
- Снимок 2026-09-10: rank **121/2928**, лидер 11.04, 15-е 5.05, 16-е 4.99. Отображаемый score остаётся 3.70.
- Private набор специально другие игры. Public-охота и форки чужих notebooks не оставляют residual для сообщества и плохо переносятся.

Рабочая цель: локальное решение с тестами и черновиком для сообщества, затем **проверка сабмитом выше бейзлайна 0.03**, и только потом — решение, открывать ли датасет/writeup. Expert→Master по Notebooks/Datasets не обгоняет этот гейт.

Что всё ещё нужно для сильного агента (это backlog качеств, не чеклист сабмитов):

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

Технически разработка возможна полностью вне личного ПК. CPU-тесты и C1 — локально, rollouts/LoRA — на внешней A100, короткую проверку финального окружения — на Kaggle. 27B не заменяет скрытый Flash-агент внутри Kaggle.

## Базовая линия

Текущий champion: приватный notebook `dmitriigluzdov/duck-qwen3-8-flash-next-nvfp4-mtp`, **version 7 (S4)**, модель `keithtyser/qwen3-8-flash-next-nvfp4/PyTorch/radixark-modelopt-fp4/1`, submission ref `56097508`, score **3.70**. Serving-only parent остаётся kernel v3 / ref 55959595 / 3.39.

Уже присутствуют image + ASCII/segmentation, Python REPL, structured memory, batching действий, MTP3 и CPU offload. Поэтому не переписываем агент целиком. LCLD пока исключён: 0.00 и Phase B errors. GPT-OSS-120B исключён: около восьми часов на публичном прогоне и низкое покрытие. Копии публичных Flash-notebooks с более высоким одиночным score без причинной разницы не считаем улучшением.

## Протокол эксперимента (обновлён 2026-09-08)

По умолчанию работаем в C-track (`COMMUNITY_TRACK.md`): локальные черновики, затем LB-проверка метода, публикация отдельно. S-ID — harness-гипотеза, не календарный день. LB только если есть residual **и** пользователь написал `засабмить следующее решение`. Kaggle Dataset/public notebook — только после COMPLETE > 0.03 и фразы `опубликовать для сообщества`.

Для S2–S7 родитель — текущий champion, а не автоматически предыдущий эксперимент. В одном сабмите меняется ровно одна гипотеза. Телеметрия, тесты и исправление очевидной упаковочной ошибки не считаются второй гипотезой.

Перед Phase B обязательно:

1. локальные unit/smoke/replay-тесты и внешнее сравнение с родителем по EXTERNAL_COMPUTE_PLAN.md;
2. проверка допустимых action IDs и offline-only зависимостей;
3. успешный короткий Kaggle smoke / Phase A с реальной загрузкой checkpoint и несколькими действиями, без полного public25; offline_eval вынесен на NSU;
4. фиксация parent version, diff/hash, seed и inference config;
5. только после явной команды пользователя — ровно один Phase B submission.

Правило решения после score: фиксировать delta к parent и historical best, но решение опирать также на paired validation, coverage, actions/tokens и runtime. Старый порог ±0.50 получен из слишком малого числа повторов и служит сигналом перепроверки, не доказательством значимости. Повышать champion только при согласующихся свидетельствах внешней проверки и LB, без новых runtime failures; при расхождении — `inconclusive`. Исторические решения S1/S2 сохраняем. ERROR/OOM/timeout диагностировать отдельно.

## Backlog harness (S1–S7)

Таблица сохраняет исходные гипотезы и их IDs. Это не очередь «обязательно сжечь 7 слотов». S1/S2/S3/S4b отклонены. S4 provisional_adopt 3.70. S6 на LB (kernel v10 / ref 56137205 PENDING).

| ID | Единственное изменение | Гипотеза и критерий |
|---|---|---|
| **S1 — Deterministic control** | Заменить `seed=-1` на стабильный воспроизводимый per-game seed; добавить read-only telemetry с config/hash/runtime. Другую policy не менять. | Получить контролируемую базу и уменьшить разброс 3.39↔2.95. Принять как экспериментальную основу, если Phase A воспроизводим и нет заметной потери coverage/runtime. |
| **S2 — Memory capture fix** | Structured-memory extractor читает размеченные факты и из `reasoning`, и из `content`, с прежними лимитами длины. | Сейчас полезные world/goal/action facts из reasoning могут теряться. Unit tests должны доказать capture, dedup и caps. Сравнивать с champion. |
| **S3 — Cross-level transfer** | На переходе уровня сохранять только подтверждённые controls, action effects и goal invariants; очищать координаты, layout и текущий план. | Поздние уровни дороже и обычно развивают ту же механику. Нужны тесты, что универсальные факты остаются, а layout-specific данные исчезают. |
| **S4 — Semantic no-impact guard** | Считать diff без верхних двух строк HUD/timer; запоминать `(semantic_state, action)` как no-impact после подтверждённого повторения и сообщать это модели. Не делать безусловный глобальный ban. | COMPLETE Public **3.70**. Working champion. Residual: фикстуры, C1 top-2 labels. |
| **S4b — Outer HUD strip** | Тот же S4 guard, но strip **верх+низ** по две строки. Одна гипотеза на родителе S4. | COMPLETE Public **2.77**. Reject −0.93 vs S4. Не стекать. |
| **S5 — Animation-aware observation** | Передавать full actionable frame плюс компактную последовательность последних animation frames; явно маркировать, где анимация, а где новое состояние. Другую память/policy не менять. | Модель перестанет планировать по промежуточному кадру и увидит причинный эффект действия. Ограничить изображения/токены, чтобы не потерять throughput. |
| **S6 — Scheduled simplification** | Периодически сворачивать длинный transcript в verified facts, disproved hypotheses, open questions и current plan; держать около 8 последних assistant turns вместо 30. | Освободить context/KV-cache и уменьшить зацикливание без полной исполняемой world model. Gate: не меньше обработанных игр и не хуже soft-deadline margin. Упакован `tmp/kernels/s6-simplify` на родителе S4. |
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

После C-track и LB-проверки решаем, открывать ли датасет/writeup. Финальными competition-кандидатами, если они появятся, должны стать два технически стабильных различающихся решения с воспроизводимыми отчётами — не два форка одной чужой базы.
