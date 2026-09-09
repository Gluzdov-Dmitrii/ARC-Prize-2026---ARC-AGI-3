# ARC-AGI-3: перенос подготовки на NSU, редакция 2026-09-08

## Решение и факты

Переносим CPU-тесты, анализ трасс, локальный датасет C1 и модельные эксперименты на собственные/NSU ресурсы. Kaggle — короткий smoke, скрытый rerun и (только после LB-гейта) опциональный public writeup. Не создавать public Dataset/Notebook до COMPLETE score > 0.03 у описываемого метода. Критерий: [COMMUNITY_TRACK.md](COMMUNITY_TRACK.md).

P0a packaging уже в репозитории (`src/p0_phase_a_modes.py`, notebook `tmp/kernels/s4b-outer2` на родителе S4). P0c: на `nsu-a100` стоит `py3.11-cu124-vllm-v1` и официальный `Qwen/Qwen3.8-27B-FP8`; native FP8 quantizer ещё падает — это блокер честного C3 LoRA. P0b harness и P0d paired baseline не закрыты. Flash NVFP4 на A100 не подтверждён.

Источник ресурсов: `C:\Users\Dmitry\Desktop\Kaggle\Kaggle Agents\external-resources\AGENT_PROMPT.md` и связанные README, ACCESS, SETUP_STATUS, WORKFLOW, RESOURCE_POLICY. Live check 2026-09-09: `mode=DIRECT_USER_AUTHORIZED`, очередь пуста (все RELEASED), обе A100 0 MiB / 0%, driver 550.54.15, NFS home ~7.0T свободно. Stdlib-venv не трогаем; ML env `py3.11-cu124-vllm-v1` на `ngpu01`. Это не аренда GPU.

S1=2.71, S2=2.72 и S3=2.77 отклонены. S4 v7/ref 56097508 COMPLETE **3.70** — working champion. Историю не переписывать. Следующий notebook — S4b outer HUD; Phase B только после фразы сабмита. 27B LoRA в этот Flash-kernel не входит.

## Что расходует Kaggle

Измерено в журнале: S1 Phase A 8497 с, S2 8476 с, S3 8559 с. Всего **7.09 часа времени GPU-инстанса** до трёх Phase B. Это не измерение списанных quota-hours: коэффициент GPU и правила списания надо учитывать отдельно.

В текущем notebook:

- cell 9 безусловно исполняет `setup_commands.json` и запускает vLLM;
- cell 13 задаёт `max_runtime_s_per_game=7920`, concurrency=28;
- cell 15 запускает все 25 публичных игр в обычном Save & Run, затем требует `PUBLIC25_AUDIT`;
- лишь после benchmark создаётся Phase A placeholder `submission.parquet`;
- `KAGGLE_IS_COMPETITION_RERUN` уже отделяет скрытый gateway от открытых файлов игр.

Следовательно, полный public25 — наша текущая проверка, а не обязательный двухчасовой этап платформы. [Официальный starter описывает Phase A и Phase B раздельно](https://github.com/arcprize/ARC-AGI-3-Kaggle-Starter).

Первая цель: **20–30 минут Phase A целиком, включая cold start** вместо ~142 минут. Это потенциально 79–86% экономии подготовки, около 7.5–8.1 часа на четырёх следующих версиях. Это оценка, которую нужно проверить первым коротким запуском. Скрытый inference продолжает выполняться на Kaggle; внешнего сервера в submission нет.

Не считать отсутствие вычислений нулевым списанием: notebook с назначенным GPU занимает GPU-инстанс и при CPU-only коде. Не переключать финальную metadata на CPU в надежде автоматически получить GPU в Phase B. Отдельный CPU validation notebook возможен, но финальная версия сохраняет нужный accelerator. Раздельно журналировать доступность GPU-слотов, остаток GPU-квоты и число submissions.

## Размещение

| Ресурс | Подходящая роль | Ограничение |
|---|---|---|
| HASEE, 32 GB RAM | Все unit/replay-тесты, notebook builder, отчёты | Основной Flash не помещается на RTX 2060 |
| `nsu-pc`, RTX 3080 10 GB, RAM ~32 GB | Небольшая 3–7B модель в совместимом 4-bit backend; только при необходимости | Windows, ограничены VRAM/RAM; не переносить Linux vLLM wheels |
| `nsu-quadro`, Quadro RTX 6000 24 GB, RAM ~251 GiB | Небольшая multimodal proxy-модель, CPU engine и анализ | Это Turing, не Kaggle Blackwell 96 GB; проверять kernels, dtype и context |
| `nsu-a100`, одна A100 80 GB, RAM хоста ~251 GiB | Основной внешний стенд: 27B BF16 (~54 GB только веса) с небольшим batch/context либо совместимая INT4/weight-only версия | Оставить запас для KV, vision, activations; успех малой модели не доказывает эффект на Flash |
| Две A100 80 GB на `ngpu01` | Опциональный Flash compatibility pilot с TP=2/CPU offload при поддержке всех слоёв | VRAM не единый пул; проверить распределение весов, PLE, MoE, interconnect и peak per GPU |

Обычный ARC GPU-job занимает одну A100. Вторую при конкуренции оставляем другим проектам. Заявка на пару допустима только после доказательства необходимости и поддержки distributed backend. Работа разбивается на блоки до 2 часов по общей очереди.

## Совместимость Flash: проверить, не обещать

Текущий production: Qwen3.8-Flash-Next NVFP4, MTP3, PLE CPU offload, Kaggle Blackwell, около 135 GB checkpoint-файлов. У A100 нет нативного Blackwell FP4; текущие runtime wheels/настройки нельзя просто скопировать.

При этом «NVFP4 вообще невозможно на A100» тоже неверный вывод: в актуальном vLLM существуют Marlin/emulation пути. Нужна проверка **именно этой модели**, включая MoE и прочие custom layers; наличие linear kernel не доказывает полноценный запуск. Источники: [vLLM quantization matrix](https://docs.vllm.ai/en/latest/features/quantization/), [NVFP4 Marlin](https://docs.vllm.ai/en/latest/api/vllm/model_executor/kernels/linear/nvfp4/marlin/).

До скачивания весов: прочитать model config и serving source, зафиксировать поддерживаемые архитектуру, quantization, dtype, MTP, PLE, CUDA/driver и конкретный runtime commit. Если пригодного backend нет, перейти к 27B proxy. Не тратить дни и обе A100 на непроверенный порт. Новые wheels могут требовать драйвер новее имеющегося: выбрать совместимый user-space стек; обновление системного драйвера не входит в миграцию.

Если Flash запускается только с отключённым MTP, другим quantization или перераспределением вычислений, пометить профиль `approximate_flash`. Не считать его побитовой копией Kaggle. Если перенос требует новой модели для самого submission, оформить отдельную гипотезу после S4–S7, не заменять champion автоматически.

## P0 — подготовительные задачи перед следующей Phase A (без LB submission)

1. **P0a: укоротить packaging.** В общем builder выделить `offline_eval`, `kaggle_smoke`, `competition`. Реальный rerun определяется только штатным Kaggle flag и имеет приоритет над smoke-конфигом. Для smoke: реальная загрузка checkpoint, text+image/tool-call запросы, 1–2 открытые игры и несколько действий с коротким бюджетом, валидный placeholder, обязательное закрытие собственного vLLM. Прервать с ошибкой, если модель не ответила; пустая заглушка не smoke.
2. **Проверить разделение режимов на CPU.** При штатном rerun флаге всегда gateway и динамический список игр, не PUBLIC_GAME_IDS и не публичный cached parquet. Budget 32400 с, per-game 7920 с, deadline reserve и production-конфиг сохраняются. При обычном smoke нет public25 audit; offline_eval отдельно сохраняет полный scorer и трассы. Учесть все notebook cells: одного сокращения `bm.run` недостаточно, setup расположен раньше.
3. **P0b: подготовить переносимый harness.** Вынести только нужные agent/engine/builder файлы из Kaggle bundle, пути передавать параметрами. Один agent source hash для NSU и Kaggle, разные serving profiles. Сохранить pinned dependency manifests и mapping Kaggle inputs → внешние project paths. Никакого предположения, что Kaggle wheelhouse для Python 3.12 работает в Linux Python 3.11. Сначала CPU import/replay и одна корректная модельная реплика после выделения GPU.
4. **P0c: обеспечить внешнюю готовность.** Проверить доступ, scheduling/lease, approved storage budget, pinned ML environment. Только после этого staging разрешённых публичных inputs и выбранной модели. Начать с минимального pilot, затем baseline/candidate. Не запускать вычисления при `BLOCKED_COORDINATION` и не заменять их полным Kaggle benchmark автоматически.
5. **P0d: зафиксировать baseline.** На одном внешнем профиле сравнить родителя и кандидата на одинаковых играх и seed-наборах. Измерить cold start, throughput, RAM/VRAM, failures. Зафиксировать `runtime_compatibility.json`, `baseline_manifest.json`, `validation_manifest.json`, `eval_summary.json` в конкретном run, вернуть копии в проект. Эти файлы — задания на реализацию, сейчас они не созданы.

P0 — служебная работа, не новый номер сабмита. Общую packaging-правку заморозить до оценки S4; доказать неизменность production-ветки тестами и hash/diff. Первый короткий Kaggle smoke должен проверить это на финальном checkpoint. Целевой лимит 30 минут — порог остановки и диагностики, не обещание, что текущий cold start обязательно уложится.

## Как сравнивать кандидатов вне Kaggle

Сохранять три уровня доказательств: CPU replay проверяет обработку уже наблюдавшихся событий; proxy rollout проверяет замкнутый агент с другой моделью; production-profile rollout проверяет целевую модель. Replay после изменения действия не предсказывает новую траекторию и не даёт counterfactual score.

- Сначала тесты на существующих S2-трассах. 5599 кадров, 1808 identical. S4 (верхние 2 строки): 226 hud-only. Исторический scan 487 — это верх **и** низ по 2 строки; builder пишет оба поля. Не считать все такие изменения бессмысленным HUD без проверки.
- Один раз разбить 25 игр на фиксированные 8 development, 8 validation и 9 отложенных; сохранять game IDs и мотив выбора до нового подбора. Это уже известные публичные игры, не честно невидимый holdout. Все уровни игры принадлежат одной группе.
- На development-панели сравнить parent/candidate с seed-набором [101, 202, 303], одинаковыми action/token limits и serving profile. Seeds служат измерению и не переносят отвергнутый S1 в production. Повтор baseline хранится и переиспользуется только для того же model/code/runtime/protocol hash.
- Заранее предложенный фильтр: нет новых crashes/illegal actions; положительная средняя paired delta и положительный результат в минимум 2 из 3 seed-проходов; общий token budget не вырос >10%, либо выросло число пройденных уровней. Пороги — операционная эвристика, не статистическая значимость. После отбора один validation-прогон и один заключительный проход оставшихся игр без подбора параметров.
- Фиксировать per-game score, levels, actions, tokens, latency, max VRAM/RAM, timeout/cancelled. `gave_up`/`cancelled` с числом score не доказывает достаточную глубину проверки: явно считать игры, реально дошедшие до новых уровней, и долю бюджета, ушедшую в очереди.
- На A100 и Kaggle отдельно сравнивать качество при равных action/token budgets и скорость при wall-clock budget. Нельзя умножением скорости A100 предсказать, сколько игр успеет Blackwell за 9 часов.
- Преимущество на proxy не является оценкой Flash. Если перенос Flash не подтверждён, сохранять кандидата как `proxy_validated`, разрешать короткий Kaggle smoke для простой S4-правки с сильными CPU-тестами; для model-sensitive S6/S5 дополнительно получить короткое парное сравнение parent/candidate на Flash в одном ограниченном Kaggle сеансе. Полные public25 на Kaggle выключены по умолчанию.

Старое правило ±0.50 Public LB было страховкой на основе всего двух повторов, не оценкой дисперсии. Для будущих решений оно остаётся сигналом повторной проверки, но не заменяет внешние paired results. Исторические S1/S2 не переоценивать без повторов.

## Очередь: сначала C-track, harness — backlog

По умолчанию: **C1 локальный датасет → C2 локальный черновик → C4/S4 после фразы сабмита → решение о публикации**. C3 LoRA после рабочего FP8. S3/ref 56075811 COMPLETE 2.77, reject. Champion Flash v3. Публичный Kaggle Dataset/writeup — только после COMPLETE S4 > 0.03 и фразы `опубликовать для сообщества`.

| ID | Где готовим | Residual, даже если score плоский | Что измерить перед optional LB |
|---|---|---|---|
| C1 dataset | CPU, `tmp/kernels/s2-output/artifacts` | локальный `pairs.jsonl` + схема + builder | counts vs HUD scan; **не** Kaggle Dataset |
| C2 writeup | `tmp/writeup-draft/` | локальный черновик | не public kernel |
| C4 LB verify | короткий smoke + Phase B | COMPLETE score > 0.03 у этого метода | не публикация |
| C3 LoRA 27B | одна A100 ≤2 ч | адаптер + рецепт | FP8 load честный; public weights только после LB-гейта |
| S4 no-impact | CPU replay; затем C4 | unit tests + HUD labels | не потеряны реальные движения; legal actions |
| S6 compaction | A100 paired; proxy ≠ Flash | тесты compaction | tokens↓, levels не хуже |
| S7 scheduler | CPU + A100 load | симуляция coverage | нет starvation |
| S5 animation | CPU fixtures | frame fixtures | image tokens оправданы |

Провал локального фильтра: `deferred_local`, сохранить причину и перейти к следующей готовой гипотезе; не тратить LB только ради расписания. Нет готового кандидата — `WAITING_VALIDATION`, дневной слот не обязательно использовать. Во время `phase_b_pending` можно делать CPU/внешнюю подготовку следующих вариантов на явно зафиксированном parent, но submit следующего ждёт закрытия предыдущего и повторной сверки parent.

## Paths, budgets, передача результатов

Linux project root: `/home/scientists/gluz_d_s/kaggle/projects/arc-prize-2026-arc-agi-3/`. Windows remote root: `C:\Users\User\kaggle\projects\arc-prize-2026-arc-agi-3`. ML env создаётся отдельно от имеющихся `py3.11-stdlib-v1`/`py3.12-stdlib-v1`; source, models, cache и runs остаются внутри зарегистрированного project root.

Планировать разрешённое дисковое место: CPU fixtures 5–20 GB; 27B pilot с одним checkpoint, средой и логами ориентировочно 80–120 GB; Flash pilot 250–350 GB. Это peak estimates, личная NFS квота неизвестна. Не дублировать веса на двух Linux hosts: NFS общий. До bulk transfer проверить разрешение на конкретные публичные inputs и их лицензии; скрытый gateway остаётся только на Kaggle.

Каждый run: code/model/env hashes, dataset version, seed list, profile (`proxy`/`approximate_flash`/`production`), resource request/lease, GPU UUID/count, durations и gpu_device_hours=count×hours. Для Kaggle дополнительно фактически наблюдённое списание квоты, если доступно; иначе null. Очередь общая для всех соревнований, неизвестный lease не присваивать. После работы забрать проверенные logs/metrics и закрыть свой server; очистить только свои неиспользуемые воспроизводимые файлы согласно RESOURCE_POLICY.

Следующая реализация — локальный черновик C2 (`tmp/writeup-draft/`), без Kaggle publish. LoRA/C3 не стартовать, пока FP8/dequant не честный. C4/S4 на LB — только после terminal S3 и фразы сабмита.
