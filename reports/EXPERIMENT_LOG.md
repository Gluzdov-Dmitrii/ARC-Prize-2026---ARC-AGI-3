# ARC Prize 2026 — experiment log

Append-only журнал. `experiment_state.json` хранит текущую очередь, этот файл — доказательства и решения. Не переписывать прошлые результаты после появления нового score; исправления добавлять отдельной пометкой.

## Историческая база до спринта

| Дата | Вариант | Submission ref | Status | Public score | Вывод |
|---|---|---:|---|---:|---|
| 2026-09-01 | baseline | 52980802 | COMPLETE | 0.03 | Устаревшая база |
| 2026-09-02 | Roman 27B | 55944286 | COMPLETE | 2.07 | Ниже Flash |
| 2026-09-02 | Flash v3 | 55959595 | COMPLETE | **3.39** | Текущий historical best/champion |
| 2026-09-03 | LCLD v1 | 55974010 | COMPLETE | 0.00 | Отклонён |
| 2026-09-04 | LCLD v2 | 56005599 | ERROR | null | Infrastructure/Phase B failure |
| 2026-09-04 | LCLD v2 retry | 56008249 | ERROR | null | Повторный infrastructure failure |
| 2026-09-04 | Flash v3 repeat | 56011722 | COMPLETE | 2.95 | Тот же вариант: наблюдаемый разброс 0.44 |

Leaderboard snapshot 2026-09-05: team rank ≈92/2803, leader ≈7.51, third ≈6.43, top-15 cutoff ≈4.29. Значения не переносить в будущие записи без повторной проверки.

### 2026-09-05 — S1 — deterministic_control

- Parent: `dmitriigluzdov/duck-qwen3-8-flash-next-nvfp4-mtp` v3, submission ref 55959595, Public 3.39, git parent `cd101e5`
- Single causal change: replace `LOCAL_ANALYZER_SEED=-1` with a stable SHA-256 per-game vLLM seed (`arc-agi-3-s1-v1`) plus read-only `s1_telemetry.json`. PUBLIC25 budget/concurrency/timeout unchanged.
- Model/checkpoint/license: `keithtyser/qwen3-8-flash-next-nvfp4/PyTorch/radixark-modelopt-fp4/1` (Qwen3.8-Flash-Next NVFP4 MTP3)
- Inference config: seed=per-game u32; temperature/top_p/top_k unchanged from Duck defaults (0.6 / 0.95 / 20 unless env overrides); context 32768; concurrency 28; analyzer_timeout 900; max_runtime_s_per_game 7920; notebook budget 32400
- Local tests: `python -m unittest tests.test_s1_deterministic_control -v` — 10/10 OK
- Phase A: kernel v4 COMPLETE; setup+run ~8497 s (~2h 21m) including 2h 12m 2s benchmark; 25/25 public games, 3522 actions, ~1.86M tokens; offline mean 7.19 / median 3.57; 0 won / all `gave_up` (expected); `PUBLIC25_AUDIT` passed; `S1_SEED_MODE namespace=arc-agi-3-s1-v1`; telemetry written twice (install + after `bm.run`); teardown OK; no OOM. Analyzer HTTP read timeouts clustered at ~8489 s during wind-down, not a notebook crash.
- Phase B: submission ref **56034166**, message as in `reports/SUBMIT_2026-09-05_S1.md`, status **PENDING**, Public score **не измерено**
- LB snapshot: not re-fetched after send; pre-submit snapshot remains 2026-09-05 rank ≈92/2803, leader ≈7.51, gold/top-15 ≈4.29
- Delta: vs parent 3.39 = null; vs historical best 3.39 = null
- Classification: pending (Phase B not terminal)
- Decision: pending_score; do not adopt/reject; do not advance queue
- Champion after decision: Flash v3 (3.39) unchanged
- Next experiment ID: **S1** until 56034166 is COMPLETE or ERROR
- Artifact/report links: `tmp/kernels/s1-deterministic/`, `src/s1_deterministic_control.py`, `reports/SUBMIT_2026-09-05_S1.md`
- Notes and anomalies: late-run vLLM read timeouts on several in-flight games; all 25 runs still finalized for the Phase A audit. Offline public mean 7.19 is not a leaderboard score.

### 2026-09-06 — S1 score closeout

- Phase B terminal: submission ref **56034166** COMPLETE, Public **2.71**
- Delta: vs parent 3.39 = **-0.68**; vs historical best 3.39 = **-0.68**; vs Flash v3 unlucky repeat 2.95 = **-0.24**
- LB snapshot 2026-09-06: leader 7.51, third 6.43, 15th 4.33, 16th 4.29. Our best Public remains 3.39 (Flash v3). Team rank not re-fetched as a precise row.
- Classification: algorithmic (Phase A COMPLETE, no proven infra failure on Phase B)
- Decision: **reject**. Do not adopt. Do not stack S1 seed into S2.
- Champion after decision: Flash v3 (kernel v3, ref 55959595, 3.39)
- Next experiment ID: **S2** (memory capture on champion v3, not on rejected v4)

### 2026-09-06 — S2 — memory_capture_fix

- Parent: `dmitriigluzdov/duck-qwen3-8-flash-next-nvfp4-mtp` v3, submission ref 55959595, Public 3.39, git parent `51856a8`. Not stacked on rejected S1 (kernel v4 / ref 56034166 / 2.71).
- Single causal change: extract Duck labeled knowledge blocks from assistant reasoning and content; content wins on conflict; identical normalized text kept once; labeled-block length policy remains `max_chars=None`. Prompts, seed, scheduler, temperature, concurrency unchanged.
- Model/checkpoint/license: `keithtyser/qwen3-8-flash-next-nvfp4/PyTorch/radixark-modelopt-fp4/1` (Qwen3.8-Flash-Next NVFP4 MTP3)
- Inference config: seed=stochastic (`LOCAL_ANALYZER_SEED=-1`); temperature/top_p/top_k unchanged from Duck defaults (0.6 / 0.95 / 20 unless env overrides); context 32768; concurrency 28; analyzer_timeout 900; max_runtime_s_per_game 7920; notebook budget 32400
- Local tests: `python -m unittest tests.test_s2_memory_capture tests.test_s1_deterministic_control -v` — 17/17 OK
- Phase A: kernel v5 COMPLETE; setup+run ~8476 s (~2h 21m) including 2h 12m 2s benchmark; 25/25 public games, 4120 actions, 1,910,303 tokens; offline mean 6.32 / median 2.90; 0 won / all `gave_up` (expected); `PUBLIC25_AUDIT` passed; `S2_MEMORY_CAPTURE reasoning+content`; telemetry written (install + after `bm.run`); no OOM / no Traceback. Analyzer HTTP read timeouts clustered at ~8468 s during wind-down, not a notebook crash.
- Phase B: submission ref **56051525**, message as in `reports/SUBMIT_2026-09-06_S2.md`, status **PENDING**, Public score **не измерено**
- LB snapshot: not re-fetched after send; pre-submit snapshot remains 2026-09-06 leader 7.51, third 6.43, 15th 4.33, 16th 4.29
- Delta: vs parent 3.39 = null; vs historical best 3.39 = null
- Classification: pending (Phase B not terminal)
- Decision: pending_score; do not adopt/reject; do not advance queue
- Champion after decision: Flash v3 (3.39) unchanged
- Next experiment ID: **S2** until 56051525 is COMPLETE or ERROR
- Artifact/report links: `tmp/kernels/s2-memory-capture/`, `src/s2_memory_capture.py`, `reports/SUBMIT_2026-09-06_S2.md`
- Notes and anomalies: late-run vLLM read timeouts on several in-flight games; all 25 runs still finalized for the Phase A audit. Offline public mean 6.32 is not a leaderboard score.

### 2026-09-07 — S2 score closeout

- Phase B terminal: submission ref **56051525** COMPLETE, Public **2.72**
- Delta: vs parent 3.39 = **-0.67**; vs historical best 3.39 = **-0.67**; vs Flash v3 unlucky repeat 2.95 = **-0.23**; vs rejected S1 2.71 = **+0.01**
- LB snapshot 2026-09-07: team rank 138/2847, leader 7.91, third 7.51, 15th 4.34, 16th 4.33. Our best Public remains 3.39 (Flash v3).
- Classification: algorithmic (Phase A COMPLETE, no proven infra failure on Phase B)
- Decision: **reject**. Do not adopt. Do not stack S2 memory capture into S3.
- Champion after decision: Flash v3 (kernel v3, ref 55959595, 3.39)
- Next experiment ID: **S3** (cross-level transfer on champion v3, not on rejected v5)

### 2026-09-07 — S3 — cross_level_transfer

- Parent: `dmitriigluzdov/duck-qwen3-8-flash-next-nvfp4-mtp` v3, submission ref 55959595, Public 3.39, git parent `34e2caf`. Not stacked on rejected S1 (v4 / 56034166 / 2.71) or S2 (v5 / 56051525 / 2.72).
- Single causal change: at Duck `level_completed`, keep confirmed controls/action effects/goal invariants; drop coordinates, layout, and current plan; preserve `cross_level_notes`; keep full wipe on `run_complete`/`game_over`. Prompts, seed, scheduler, temperature, concurrency unchanged.
- Model/checkpoint/license: `keithtyser/qwen3-8-flash-next-nvfp4/PyTorch/radixark-modelopt-fp4/1` (Qwen3.8-Flash-Next NVFP4 MTP3)
- Inference config: seed=stochastic (`LOCAL_ANALYZER_SEED=-1`); temperature/top_p/top_k unchanged from Duck defaults (0.6 / 0.95 / 20 unless env overrides); context 32768; concurrency 28; analyzer_timeout 900; max_runtime_s_per_game 7920; notebook budget 32400
- Local tests: `python -m unittest tests.test_s3_cross_level_transfer tests.test_s2_memory_capture tests.test_s1_deterministic_control -v` — 26/26 OK
- Phase A: kernel v6 COMPLETE; setup+run ~8559 s (~2h 23m) including 2h 12m 2s benchmark; 25/25 public games, 3848 actions, 1,919,190 tokens; offline mean 8.46 / median 4.76; 0 won / all `gave_up` (expected); `PUBLIC25_AUDIT` passed; 42 `S3_LEVEL_TRANSFER` events; telemetry written (install + after `bm.run`); no CUDA OOM. Analyzer HTTP read timeouts clustered at ~8549 s during wind-down; teardown `shutdown_ok=false` after audit, notebook still COMPLETE.
- Phase B: submission ref **56075811**, message as in `reports/SUBMIT_2026-09-07_S3.md`, status **PENDING**, Public score **не измерено**
- LB snapshot: not re-fetched after send; pre-submit snapshot remains 2026-09-07 rank 138/2847, leader 7.91, third 7.51, 15th 4.34, 16th 4.33
- Delta: vs parent 3.39 = null; vs historical best 3.39 = null
- Classification: pending (Phase B not terminal)
- Decision: pending_score; do not adopt/reject; do not advance queue
- Champion after decision: Flash v3 (3.39) unchanged
- Next experiment ID: **S3** until 56075811 is COMPLETE or ERROR
- Artifact/report links: `tmp/kernels/s3-cross-level/`, `src/s3_cross_level_transfer.py`, `reports/SUBMIT_2026-09-07_S3.md`
- Notes and anomalies: late-run vLLM read timeouts on several in-flight games; all 25 runs still finalized for the Phase A audit. Offline public mean 8.46 is not a leaderboard score. Teardown GPU survivor is post-audit and did not prevent COMPLETE.

### 2026-09-07 — досрочная корректировка вычислительного плана

- Причина: общая Kaggle GPU-квота быстро расходуется, проекты конкурируют за слоты.
- Измеренный расход Phase A S1–S3: 8497 + 8476 + 8559 = 25532 с, 7.09 часа времени GPU-инстанса. Списанные quota-hours отдельно не измерены.
- Источник ресурсов: external-resources/SETUP_STATUS.md от 2026-09-07; Quadro RTX 6000 24 GB, RTX 3080 10 GB, 2×A100 80 GB. Более поздний setup создал каталоги/stdlib envs; старое сообщение об отсутствующих roots из NSU_STATUS больше не актуально. ML environment, scheduler/coordination и личная bulk-storage квота ещё не подтверждены как готовые.
- Решение: P0a короткая Kaggle Phase A, P0b переносимый harness, P0c внешний runtime/allocation, P0d paired baseline. Цель Phase A 20–30 мин с cold start, это прогноз, не результат запуска.
- Оставшийся порядок: S4 → S6 → S7 → S5 после terminal S3 и P0. IDs и исходные гипотезы сохраняются.
- Protocol change: внешний paired screening вместо обязательного полного Kaggle public25; CPU/proxy/production evidence разделять; ±0.50 LB считать эвристикой, не значимостью. Исторические rejects S1/S2 сохранены.
- Фактически выполнено: анализ кода notebook и документов; обновление плана/инструкций/state. Код миграции, NSU installs/transfers/GPU jobs и Kaggle launches/submissions в этой задаче не выполнялись.
- S3/ref 56075811 остаётся PENDING по сохранённому state, новый terminal API результат в этой ревизии не запрашивался. Champion остаётся Flash v3.
- Документ: EXTERNAL_COMPUTE_PLAN.md. Следующая подготовительная задача: P0a; следующий closeout: S3.

### 2026-09-07 — P0a packaging + старт A100/27B стенда

- S3/ref 56075811 всё ещё PENDING в live CLI; Phase B сегодня не повторяли и S4 не отправляли. Champion остаётся Flash v3 / 3.39.
- P0a: `src/p0_phase_a_modes.py` разделяет `competition` / `kaggle_smoke` / `offline_eval`. Smoke: 2 игры, 4 действия, 180 с/игру, без PUBLIC25_AUDIT. Скрытый rerun по `KAGGLE_IS_COMPETITION_RERUN` сохраняет 7920/900/28/32400.
- S4 notebook собран из champion packaging без S1/S2/S3: `tmp/kernels/s4-no-impact/`. Единственное policy-изменение — HUD-insensitive no-impact memory (`src/s4_semantic_no_impact.py`). Глобального ban нет.
- Локальные тесты: `python -m unittest tests.test_p0_s4 tests.test_s3_cross_level_transfer tests.test_s2_memory_capture tests.test_s1_deterministic_control -v`.
- NSU live check: `resource_queue.py status` → `DIRECT_USER_AUTHORIZED`, очередь пуста; обе A100 0 MiB, driver 550.54.15; NFS home ~7.0T свободно, `quota` отсутствует. Stdlib venv не трогали.
- P0c: на `ngpu01` создаётся `envs/ngpu01/py3.11-cu124-vllm-v1` (torch 2.6.0+cu124). После receipt автоматически качается `Qwen/Qwen3.8-27B-FP8` (~30.9 GB) в `models/Qwen3.8-27B-FP8`. GPU lease на время pip/download не берём. После старта bootstrap SSH к `10.1.0.7`/`10.1.0.8` кратковременно timeout при подключённом NSU-SSTP, затем доступ восстановился. Живой лог: `pip install vllm` тянет CUDA 13 wheels (`humming-kernels[cu13]`, `nvidia-cuda-runtime` 13.3); на driver 550.54.15 это может не завестись. Если так — оставляем transformers fallback на A100. Load-smoke ещё не запускали.
- P0b (portable harness) и P0d (парный baseline/load smoke) ещё pending. 27B proxy не заменяет Flash на Kaggle.
- Артефакты: `src/eval_panels.json` (8/8/9 public split, seeds 101/202/303), `src/nsu_bootstrap_ml_env.py`, `src/nsu_download_qwen38_27b.py`, `src/nsu_a100_27b_smoke.py`.

### 2026-09-08 — NSU 27B stand smoke (no LB)

- S3/ref 56075811 всё ещё PENDING. Сабмит не делали. Champion Flash v3 / 3.39.
- После восстановления VPN: bootstrap и download уже были готовы. `Qwen/Qwen3.8-27B-FP8` — 246 файлов, 30.89 GB.
- vLLM 0.28 поставил torch 2.13 / CUDA 13; на driver 550.54.15 `torch.cuda` отказал (found 12040). GPU отпустили, вернули torch 2.6.0+cu124.
- Сняли брошенный Biohub `dispatch.lock/OWNER.json` (нет процесса, Quadro idle) в `_control/diagnostics/`; иначе вся очередь была DISPATCH_BUSY.
- Рабочий путь: одна A100, `Qwen3_5ForConditionalGeneration` + transformers 5.16.1, без vLLM. Native FP8 quantizer падает (`layer_overrides is None` в `quantizer_finegrained_fp8.py`). Загрузка с `quantization_config=None`: веса встали, `weight_scale_inv` UNEXPECTED.
- Smoke receipt: backend `transformers_qwen3_5`, `ok=true`, 74.2 с, GPU A100 80GB, процесс завершился, аренда `arc3-p0d-27b-smoke-bf16` RELEASED, обе карты 0 MiB.
- Это проверка стенда, не quality baseline. Для парного отбора S4 нужно починить FP8/dequant. P0d paired baseline ещё pending.

### 2026-09-08 — смена критерия: residual value, не погоня за золотом

- Пользователь явно сменил цель: не клонировать чужие открытые notebooks и не жечь сабмиты ради Public gold. Вопрос перед работой: «что проверенное останется, даже если score не вырастет?»
- Протокол: `COMMUNITY_TRACK.md`. Очередь по умолчанию **C1 датасет → C2 writeup → C3 LoRA на Qwen3.8-27B-FP8 → C4 optional LB**. S4–S7 остаются harness backlog.
- S3/ref 56075811 не закрывали и не повторяли. Champion Flash v3 / 3.39. Phase B не делали.
- C1: схема `src/community_dataset_schema.json`, builder `src/build_community_dataset.py`, тесты `tests/test_community_dataset.py`. Источник — S2 `tmp/kernels/s2-output/artifacts/*_events.jsonl`. Без transcripts и hidden games.
- HUD finding: 5599 кадров / 5574 пары, identical **1808**. Классификатор S4 (только верхние 2 строки): hud_only **226**, interior **3540**. Исторический scan «outer 2 rows» — это верх **и** низ: hud_only **487**, interior **3279**. Датасет пишет оба поля (`label`, `label_outer2`). S4 harness в этом шаге не меняли.
- C3 заблокирован сломанным Finegrained FP8 load (`weight_scale_inv` UNEXPECTED). Не начинать LoRA на обрезанном bf16 как «наш 27B».
- Следующая задача: прогнать C1 builder (`--expect-s2-counts`) и при желании опубликовать dataset. Дневной слот по умолчанию пропускаем.

### 2026-09-08 — публикация только после LB выше бейзлайна

- Пользователь уточнил: открытые датасет и writeup должны опираться на сабмитящееся решение со скором выше бейзлайна, не обязательно на топ. Сначала черновик, потом LB, потом отдельное решение о публикации.
- До этой правки гейт **не** был обеспечен: C1/C2 можно было выложить без рабочего LB метода. Kaggle Dataset/public kernel мы не создавали.
- Бейзлайн гейта: ref **52980802**, Public **0.03**. Нужен Phase B COMPLETE описываемого метода. Flash v3 / 3.39, S1/2.71 и S2/2.72 этот гейт для C1/C2 не открывают.
- Фраза публикации: `опубликовать для сообщества`. Сабмит её не заменяет. `value_policy.kaggle_public_release.eligible` = false.
- C1 остаётся `local_draft_verified`. C2 — локальный outline в gitignored `tmp/writeup-draft/`. C4 — ждать terminal S3, затем проверять метод (скорее S4) на LB.
- S3/ref 56075811 не закрывали. Champion Flash v3 / 3.39. Phase B и publish не делали.

### 2026-09-08 — S3 score closeout

- Phase B terminal: submission ref **56075811** COMPLETE, Public **2.77** (read-only `kaggle competitions submissions` 2026-09-08). No new send.
- Delta: vs parent 3.39 = **-0.62**; vs historical best 3.39 = **-0.62**; vs Flash v3 unlucky repeat 2.95 = **-0.18**; vs rejected S2 2.72 = **+0.05**; vs rejected S1 2.71 = **+0.06**; vs own baseline 0.03 = **+2.74**
- LB snapshot 2026-09-08: rank **165/2879**, leader **11.04**, third **7.63**, 15th **4.74**, 16th **4.71**. Displayed team score remains **3.39** (Flash v3).
- Classification: algorithmic (Phase A COMPLETE, Phase B COMPLETE, no proven infra failure)
- Decision: **reject**. Do not adopt. Do not stack S3 into S4.
- Champion after decision: Flash v3 (kernel v3, ref 55959595, 3.39)
- Next experiment ID: **S4** (semantic no-impact on champion v3). C4 LB verify waits for `засабмить следующее решение`. Dataset/writeup stay private.
- Artifact/report links: `reports/SUBMIT_2026-09-07_S3.md`

### 2026-09-08 — S4 / C4 — semantic_no_impact_guard

- Parent: `dmitriigluzdov/duck-qwen3-8-flash-next-nvfp4-mtp` v3, submission ref 55959595, Public 3.39. Not stacked on rejected S1/S2/S3.
- Single causal change: HUD-insensitive semantic diff (top 2 rows) and confirmed `(semantic_state, action)` no-impact memory; no global ban.
- Model/checkpoint/license: `keithtyser/qwen3-8-flash-next-nvfp4/PyTorch/radixark-modelopt-fp4/1`
- Local tests: `python -m unittest tests.test_p0_s4 tests.test_community_dataset tests.test_s1_deterministic_control tests.test_s2_memory_capture tests.test_s3_cross_level_transfer -v` — 40/40 OK
- Phase A: kernel **v7** COMPLETE; smoke `kaggle_smoke` 2 games / 8 actions / 53s benchmark (~635 s notebook including setup); tokens 9162; `SMOKE_AUDIT` passed; S4 telemetry written; teardown `shutdown_ok=false` after audit, notebook COMPLETE. Not a public-25.
- Phase B: submission ref **56097508**, message as in `reports/SUBMIT_2026-09-08_S4.md`, status **PENDING**, Public score **не измерено**. One send; CLI `0 submissions remaining today.`
- Decision: pending_score; do not adopt/reject; do not publish C1/C2; do not send again.
- Champion after send: Flash v3 (3.39) unchanged
- Next experiment ID: **S4** until 56097508 is COMPLETE or ERROR

### 2026-09-09 — S4 score closeout

- Phase B terminal: submission ref **56097508** COMPLETE, Public **3.70** (read-only `kaggle competitions submissions` 2026-09-09). No new send.
- Delta: vs parent Flash v3 3.39 = **+0.31**; vs historical serving-only best 3.39 = **+0.31**; vs Flash v3 unlucky repeat 2.95 = **+0.75**; vs rejected S3 2.77 = **+0.93**; vs own baseline 0.03 = **+3.67**
- LB snapshot 2026-09-09 (CSV `2026-09-09T03:43:01Z`): rank **105/2900**, leader **11.04**, third **7.63**, 15th **4.90**, 16th **4.82**. Displayed team score is **3.70**.
- Classification: algorithmic (Phase A COMPLETE, Phase B COMPLETE). Effect size **below** the +0.50 heuristic, so not a proven lift; still the new historical best.
- Decision: **provisional_adopt** as working champion on user direction 2026-09-09 («по LB не плохо»). Do not stack S1–S3. Parent for the next notebook is S4, not Flash v3-only.
- Publication: `value_policy.kaggle_public_release.eligible=true` because S4 COMPLETE 3.70 > 0.03. `published=false`. Do not open C1/C2 without `опубликовать для сообщества`.
- Champion after decision: S4 (kernel v7, ref 56097508, 3.70)
- Next experiment ID: **S4b** (outer HUD strip on S4 parent)

### 2026-09-09 — S4b — outer_hud_no_impact (packaged, not submitted)

- Parent: kernel v7, submission ref 56097508, Public 3.70
- Single causal change: same S4 no-impact guard with **top and bottom two** HUD rows stripped (`hud_bottom_rows=2`). S1/S2/S3 not stacked.
- Local residual: C1 already counted outer2 `hud_only` **487** vs S4 top-only **226** (+261). Unit tests cover bottom-strip classification. Notebook markdown rewritten: keep Tufa/Keith credits; drop Tufa first-person including the milestone-1.21 note.
- Model/checkpoint: same Flash NVFP4. A100 27B LoRA still blocked (native FP8). Live NSU 2026-09-09: both A100 **0 MiB / 0%**, queue empty. A 27B finetune does not enter this Flash kernel.
- Local tests: `python -m unittest tests.test_p0_s4 tests.test_community_dataset tests.test_s1_deterministic_control tests.test_s2_memory_capture tests.test_s3_cross_level_transfer` — 43/43 OK
- Phase A: kernel **v8** ERROR (shadowed `hud_bottom_rows()`). **v9** COMPLETE 2026-09-09: `PHASE_A_MODE kaggle_smoke`; `S4B_OUTER_HUD hud_bottom_rows=2`; `OFFLINE_SELECTION games=2`; `SMOKE_AUDIT runs=2 actions=8`; benchmark 46s (tn36+lf52); tokens 7895; telemetry transitions=10 identical=4 hud_only=6 real_change=0 confirmed_no_impact=4; placeholder `submission.parquet` 2648 B. Teardown `shutdown_ok=false` / `vllm_gpu_survivors=1` after audit (same class as S4); notebook still COMPLETE, no TypeError. Phase B: **not sent**.
- Decision: `ready_not_submitted`. Phase A gate passed. Wait for `засабмить следующее решение`.
- Artifact/report links: `tmp/kernels/s4b-outer2/`, `src/s4_semantic_no_impact.py`, `src/notebook_prose.py`, `src/patch_s4b_notebook.py`

### 2026-09-09 — S4b Phase B send

- Phase B: submission ref **56122822**, message as in `reports/SUBMIT_2026-09-09_S4b.md`, status **PENDING**, Public score **не измерено**. One send; CLI `0 submissions remaining today.`
- Decision: pending_score; do not adopt/reject; do not publish C1/C2; do not send again.
- Champion after send: S4 (3.70) unchanged
- Next experiment ID: **S4b** until 56122822 is COMPLETE or ERROR

## Шаблон записи Sx

Скопировать секцию и заполнить после каждого подготовленного/отправленного варианта.

### YYYY-MM-DD — Sx — short_name

- Parent: kernel/version, submission ref, score, git commit/hash
- Single causal change:
- Model/checkpoint/license:
- Inference config: seed, temperature, top_p, context, concurrency, action/time budgets
- Local tests:
- External validation: host/lease, proxy/approximate_flash/production, model/env hashes, panels/seeds, paired deltas, gpu_device_hours
- Kaggle quota: observed debit if available (else null); Phase A and Phase B runtimes separately
- Phase A: kernel/version, status, runtime, games/levels/actions, failures, memory/OOM margin
- Phase B: submission ref, message, terminal status, Public score
- LB snapshot: rank/teams, leader, gold/top-15 cutoff
- Delta: vs parent; vs historical best
- Classification: algorithmic / infrastructure / inconclusive
- Decision: adopt / reject / repeat / ready_not_submitted
- Champion after decision:
- Next experiment ID:
- Artifact/report links:
- Notes and anomalies:
