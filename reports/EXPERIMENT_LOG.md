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

## Шаблон записи Sx

Скопировать секцию и заполнить после каждого подготовленного/отправленного варианта.

### YYYY-MM-DD — Sx — short_name

- Parent: kernel/version, submission ref, score, git commit/hash
- Single causal change:
- Model/checkpoint/license:
- Inference config: seed, temperature, top_p, context, concurrency, action/time budgets
- Local tests:
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
