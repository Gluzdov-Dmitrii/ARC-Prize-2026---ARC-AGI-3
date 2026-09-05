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
