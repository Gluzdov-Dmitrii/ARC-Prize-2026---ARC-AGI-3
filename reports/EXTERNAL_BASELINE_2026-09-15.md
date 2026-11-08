# External Baseline 2026-09-15

Purpose: measure the current top-open public Kaggle notebook against our S4 champion and the local P0d preparation. This is an external baseline, not our method.

## Live LB Snapshot

- Date: 2026-09-15
- Leader: Tufa Labs, 18.81
- Third place: 8.44
- 15th: 5.68
- 16th: 5.66
- Our displayed best: S4, 3.70
- Lag from S4 to leader: 15.11
- Lag from S4 to 15th: 1.98

## Local Lineage

- Working champion: S4 semantic no-impact, ref 56097508, Public 3.70.
- Latest local candidate: S9 consecutive RESET guard, ref 56221692, COMPLETE 2.81, reject.
- P0d local/NSU: Qwen3.8-27B-FP8 load smoke OK through Transformers dequant-to-bf16 on A100; no quality score yet.

## External Baseline

- Source kernel: `wuliao0/duck-qwen3-8-anim-base`
- Source title: Duck Qwen3.8 Anim Base
- Source author: wuliao_0
- Source state at pull/check: RUNNING
- Selection signal: first result from `kaggle kernels list --competition arc-prize-2026-arc-agi-3 --sort-by scoreDescending` on 2026-09-15.
- Private fork: `dmitriigluzdov/arc3-external-baseline-wuliao-duck-anim`
- Fork version: 1
- Visibility: private
- Solver behavior change: none; metadata/private fork only.
- Phase A status: COMPLETE
- Phase B submission: ref 56248712, COMPLETE Public 2.92 (checked 2026-09-16), submitted 2026-09-15 07:23:21.147000.

## Interpretation Rules

- If the external baseline beats S4, treat it as a target and literature signal, not as our champion.
- If it is below S4, keep S4 as displayed best and continue P0d/local causal work.
- Do not publish this fork or C1/C2 without the explicit phrase `опубликовать для сообщества`.

## Phase B Send

- Submit command accepted on 2026-09-15.
- Submission ref: 56248712
- Status at first check: PENDING
- Public score: 2.92 (COMPLETE, checked 2026-09-16).
- Delta vs S4: -0.78; vs S9: +0.11. Gap to September 15 leader: 15.89; to 15th: 2.76.
- Decision: retain S4 as working champion. P0d still has no quality score.
- Message: `EXB1 external Wuliao Duck Anim private fork v1; solver unchanged; compare to S4 3.70`
