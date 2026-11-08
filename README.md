# ARC Prize 2026 — ARC-AGI-3

Working repository for the Kaggle competition
[ARC Prize 2026 - ARC-AGI-3](https://www.kaggle.com/competitions/arc-prize-2026-arc-agi-3)
(closed 2026-11-02, results 2026-12-04).

## Outcome

Final selection (public LB):

| Submission | Public LB | What it is |
|---|---:|---|
| 57738630 | 28.94 | Copy of the public lalalia-final notebook: Daniel Franzen's milestone-2 agent + solved-level memory, longer server start-up and retry windows |
| 57610776 | 23.60 | Franzen milestone-2 agent unchanged |

Lessons from the endgame (`reports/SUBMISSIONS_ENDGAME.md`):
- Several 0.00 scores came from the platform (model server start-up in the hidden rerun),
  including an exact rerun of a version that had scored 23.60 — a zero alone does not prove an edit broke the agent.
- Adding the public D′ priority cell on top of solved-level memory lowered the score (21.84).
- Our own agent sprints from September (S1–S10) stayed at ~3 points; all scoring entries are forks of public agents.

The endgame notebook build lives in the ARC-AGI-2 repository under `work/codex-ws/arc3-fork/`.

## Layout

- `src/`, `tests/` — sprint agents, notebook builder, runtime and validation.
- `reports/` — experiment log, sprint evidence, submission tables, hand-off notes.
- `output/notebooks/` — packaged notebook manifests.
