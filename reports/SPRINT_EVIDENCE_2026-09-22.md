# Evidence audit for the 2026-09-22 notebook sprint

Scope: selected local source/reports and the guide's September 22 verified-source briefs. No notebook changes, submissions or publication performed by this audit. Fresh Kaggle result below was supplied by the parent agent after its successful live read.

## Decision

Use exact S4 v7 as the baseline, preserving its model, serving configuration, prompts, budgets and top-only HUD setting. Build the candidate around narrow no-impact-memory correctness repairs, with baseline/candidate toggles and targeted regression tests. Do not stack the previously rejected policies. This is the strongest evidence-backed one-hour direction; a higher private score remains unverified until an actual hidden evaluation.

## Strongest credible baseline

| Method | Recorded Public score | Evidence |
|---|---:|---|
| S4 original v7, ref 56097508 | 3.70 | `reports/SUBMIT_2026-09-08_S4.md`, `experiment_state.json` |
| Exact S4 repeat S4R1, ref 56275704 | **3.38 COMPLETE** | Parent's fresh Kaggle read 2026-09-22; previous local PENDING is stale |
| Flash v3 parent | 3.39 and 2.95 | `experiment_state.json:repeat_observations` |
| External Wuliao Duck Qwen3.8 Anim Base, ref 56248712 | 2.92 COMPLETE | `reports/EXTERNAL_BASELINE_2026-09-15.md` |

S4 pair mean is 3.54; Flash pair mean is 3.17. Difference is +0.37 points, but two stochastic runs per method cannot establish significance or private generalization. The external notebook's selection as a high-scoring open kernel did not reproduce a stronger result in the stored private-fork run. It is not a stronger local champion.

The current kernel id is **132850984**, renamed to `dmitriigluzdov/arc-agi-3-s7-adaptive-scheduler-flash-nvfp4`; historical **version 7** is S4. Its older S4 slug returns 404. Never infer the solver from the current title or submit latest v14 thinking it is S4. Source: `reports/EXPERIMENT_LOG.md`, lines 370–376.

## Rejected changes and meaningful failure evidence

| Variant | Public score | What should not be silently restored |
|---|---:|---|
| S1 | 2.71 | Deterministic-control policy |
| S2 | 2.72 | Added memory capture |
| S3 | 2.77 | Cross-level transfer |
| S4b | 2.77 | Also cropping the bottom two rows |
| S6 | 2.82 | History cap of 8 assistant turns and compaction |
| S7 | 2.82 | Adaptive scheduler with early stuck cuts |
| S5 | 3.13 | Up to three added animation images |
| S8 | 3.10 | ACTION7/UNDO prompt/mapping implementation |
| S9 | 2.81 | Consecutive RESET guard |

Source: `experiment_state.json:experiments`; interpretation and smoke details in `reports/EXPERIMENT_LOG.md`. These observations reject the tested implementations, not the general concepts. Valid action support remains a correctness concern even though S8 did not improve Public score.

S4b smoke had `real_change=0` versus S4's `real_change=3`. The replay dataset has 226 top-only HUD changes but 487 when also dropping two bottom rows: 261 transitions change category. Extra cropping can erase gameplay motion. Keep `hud_bottom_rows=0`; do not interpret top-row masking as a universal truth about unseen games.

`tmp/community-dataset-v1/summary.json`: 25 S2 games, 5,599 frames, 5,574 transitions; 1,808 identical, 226 top-only HUD changes, 3,540 interior changes. This is S2 evidence, not an S4 rollout or a counterfactual score. `tmp/kernels/s2-output/artifacts/*_viewer_data.json` records all 25 runs as `gave_up`; six games scored zero, including tn36 with 370 actions and wa30 with 416 actions. The full run consumed 1,910,303 tokens, mean 6.32 and median 2.90 on public development games (`reports/SUBMIT_2026-09-06_S2.md`). Repetition and shallow progress are real diagnostic targets, but replay cannot predict the trajectory after changing an action.

Phase A of S4 was only 2 games × 4 actions: 53 seconds benchmark, about 635 seconds including setup, score zero, 9,162 tokens. It verifies packaging and a functioning model, not solution quality. Its `shutdown_ok=false` occurred after the successful smoke audit; do not mistake that alone for a solver failure. Source: `reports/SUBMIT_2026-09-08_S4.md`.

## Narrow candidate with the best justification

`src/s4_semantic_no_impact.py` currently creates one `NoImpactBook` in `install_s4_hooks` and closes over it in the class-wide ToolAgent wrapper, despite the class docstring promising per-game memory. Consequently another agent/game can clear or supply memory. Fix ownership by agent and active game/state path; verify a level reset affects only its owner.

The wrapper compares grids before and after the whole Python tool call, reads `_last_step_summary`, and attributes that net transition to `executed_actions[-1]`. A multi-action round trip can therefore falsely mark the final action as ineffective. No-action tools can also expose an old summary. Count only newly executed, causally attributable actions. For multi-action batches, use actual per-action transitions if reliable data exists; otherwise skip attribution. Do not guess which step caused the net change.

Keep user-facing no-impact notes scoped to the current state and discard stale notes when that state or level changes. Preserve the original soft hint and two-repeat threshold; do not add action bans, early cutoffs, new prompts or a second policy change in the same sprint.

Acceptance tests should cover independent concurrent agents, no-action/stale-summary calls, net-zero multi-action batches, ordinary single-action repeats, genuine interior movement, level changes and GAME_OVER. Packaging tests should prove the competition branch still uses the live gateway, full dynamic game list and original budgets. Unit/replay success is correctness evidence only; a short production-model smoke verifies runtime, not Public or Private gains.

## Newest analysis and restrictions

The September 22 guide explicitly recommends: refresh S4R1, freeze a reproducible baseline, diagnose ten representative failures, change one observed cause, then test on other games (`tmp/arc_guide/content.py`, lines 301–312). The first item is now resolved by the live S4R1 result above. `tmp/arc_guide/current_state.md` is the completed Word-guide state, not the current notebook-sprint state.

Verified on September 22 in `tmp/arc_guide/rules_brief.md` and `metric_sdk_brief.md`:

- Evaluation has no internet; notebook runtime limit is 9 hours; local model assets must be available in Kaggle inputs. One daily competition submission; Phase A completion and Phase B competition evaluation are separate events.
- There are 25 public development games and 110 hidden games split into 55 Public-LB and 55 Private-LB games. Hardcoded public game selection must never replace hidden gateway discovery.
- RHAE penalizes unsuccessful exploration and extra actions; RESET does not erase the action cost. Later completed levels carry greater weights. A score of 3.70 does not mean 3.70% of games were won.
- Competition Mode restricts resets to the current level, allows each environment once, disallows intermediate scorecards, and includes skipped games as zero. S9's motivation should not be carried forward using ordinary-mode double-RESET semantics.
- Do not read hidden game source or encode manual validation/test answers. Generic memory correctness fixes offer a plausible transfer argument; public-game-specific coordinates, IDs or rules do not.
- Existing model/checkpoint is Qwen3.8-Flash-Next NVFP4 MTP3 from `keithtyser/qwen3-8-flash-next-nvfp4/PyTorch/radixark-modelopt-fp4/1`. The NSU 27B FP8-to-bf16 load smoke establishes only loading/inference compatibility, not a scored baseline or a stronger solver.

`src/eval_panels.json` already defines 8 development / 8 validation / 9 held-public games and seeds [101,202,303]. These are previously available public games, not a genuinely unseen private holdout. Reuse them rather than tuning a new split to the candidate. `EXTERNAL_COMPUTE_PLAN.md` distinguishes CPU replay, proxy-model rollouts and production-model rollouts; do not present one as another.

Existing local policy keeps publication private until explicit authorization. User authorization in the active session takes precedence over an older required phrase; this audit makes no decision to send or publish. Clear attribution to Tufa/Duck, Keith Tyser and upstream components should remain in the comprehensible notebook.

## Fresh open notebook delta: Duck Qwen3.8 (Tuned)

Read-only comparison of the parent's newly pulled `tmp/kernels/sprint-tuned/duck-qwen3-8-tuned.ipynb` and metadata (`chiakazirim/duck-qwen3-8-tuned`, kernel id 133157788) against stored `tmp/kernels/wuliao-anim-base/duck-qwen3-8-anim-base.ipynb` found **exactly three code-line changes**:

1. `bm.solver.analyzer_timeout`: 900 → 1,200 seconds.
2. `_wait_for_gateway` default timeout: 600 → 300 seconds.
3. Gateway readiness condition: HTTP status `<500` → `<250`.

All markdown cells are identical; all other code is identical. Both notebooks have 18 cells and zero saved cell outputs. There is **no measured score evidence in the downloaded notebook** and no new reasoning, memory, perception, action policy, model or animation mechanism in its source. Increasing analyzer timeout changes tolerance for long model requests; it is not established as a quality improvement. Shortening gateway startup tolerance potentially reduces robustness. Neither warrants replacing S4 or adding a policy in this sprint.

Metadata confirms identical dataset slugs, pinned model version, competition source, Docker image digest, RTX Pro 6000 machine shape and internet-disabled setting across tuned, Wuliao and S4. Dataset entries are slugs without version suffixes, so identical metadata does not prove identical historical dataset contents. Notebook code differences are exact; dependency *content* identity is unverified. Installation/source-discovery/setup/benchmark-load cells (5/7/9/11) are byte-identical between tuned and Wuliao. S4 uses the same source/setup/load cells and a dynamic competition-root path for wheel installation.

Conclusion: this fresh public notebook provides no evidence for a better baseline than S4. Preserve the narrow correctness-fix plan.
