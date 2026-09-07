"""P0a: short Kaggle Phase A smoke vs unchanged competition rerun.

Packaging only. Production/TRUE_SUBMISSION budgets stay exactly the Flash v3
values. Offline Save & Run uses a short 1-2 game smoke so Kaggle GPU time is
minutes, not a full public-25. Hidden rerun is selected solely by
``KAGGLE_IS_COMPETITION_RERUN`` and never inherits smoke caps.
"""

from __future__ import annotations

from typing import Any, Sequence

PRODUCTION_MAX_RUNTIME_S_PER_GAME = 7920.0
PRODUCTION_ANALYZER_TIMEOUT_S = 900.0
PRODUCTION_CONCURRENCY = 28
PRODUCTION_MAX_ACTIONS_PER_GAME = None
PRODUCTION_NOTEBOOK_BUDGET_S = 32400.0
PRODUCTION_PUBLIC_GAMES = 25

SMOKE_MAX_RUNTIME_S_PER_GAME = 180.0
SMOKE_ANALYZER_TIMEOUT_S = 120.0
SMOKE_CONCURRENCY = 2
SMOKE_MAX_ACTIONS_PER_GAME = 4
SMOKE_GAME_COUNT = 2

MODE_COMPETITION = "competition"
MODE_KAGGLE_SMOKE = "kaggle_smoke"
MODE_OFFLINE_EVAL = "offline_eval"


def phase_a_mode(*, true_submission: bool, offline_eval: bool = False) -> str:
    if true_submission:
        return MODE_COMPETITION
    if offline_eval:
        return MODE_OFFLINE_EVAL
    return MODE_KAGGLE_SMOKE


def apply_solver_settings(
    bm: Any,
    target: Any,
    *,
    true_submission: bool,
    offline_eval: bool = False,
) -> str:
    mode = phase_a_mode(true_submission=true_submission, offline_eval=offline_eval)
    if float(getattr(target, "max_runtime_s", 0.0) or 0.0) != PRODUCTION_NOTEBOOK_BUDGET_S:
        raise RuntimeError(
            f"Expected the {PRODUCTION_NOTEBOOK_BUDGET_S:.0f}-second notebook budget, "
            f"got {getattr(target, 'max_runtime_s', None)!r}."
        )
    if mode == MODE_KAGGLE_SMOKE:
        bm.solver.max_runtime_s_per_game = SMOKE_MAX_RUNTIME_S_PER_GAME
        bm.solver.analyzer_timeout = SMOKE_ANALYZER_TIMEOUT_S
        bm.solver.concurrency = SMOKE_CONCURRENCY
        bm.solver.max_actions_per_game = SMOKE_MAX_ACTIONS_PER_GAME
    else:
        bm.solver.max_runtime_s_per_game = PRODUCTION_MAX_RUNTIME_S_PER_GAME
        bm.solver.analyzer_timeout = PRODUCTION_ANALYZER_TIMEOUT_S
        bm.solver.concurrency = PRODUCTION_CONCURRENCY
        bm.solver.max_actions_per_game = PRODUCTION_MAX_ACTIONS_PER_GAME
    bm.solver.save_request_logs = False
    print(
        f"PHASE_A_MODE mode={mode} budget_s={bm.solver.max_runtime_s_per_game} "
        f"concurrency={bm.solver.concurrency} analyzer_timeout={bm.solver.analyzer_timeout} "
        f"action_cap={bm.solver.max_actions_per_game}",
        flush=True,
    )
    return mode


def select_offline_game_ids(public_ids: Sequence[str], *, mode: str) -> list[str]:
    ids = list(public_ids)
    if len(ids) != PRODUCTION_PUBLIC_GAMES:
        raise RuntimeError(f"Expected {PRODUCTION_PUBLIC_GAMES} public IDs, got {len(ids)}.")
    if mode == MODE_KAGGLE_SMOKE:
        return ids[:SMOKE_GAME_COUNT]
    return ids


def require_model_actions(total_actions: int, *, mode: str) -> None:
    if total_actions <= 0:
        raise RuntimeError(
            f"Phase A mode={mode} produced no actions; refusing empty smoke/eval placeholder."
        )


def should_run_public25_audit(mode: str) -> bool:
    return mode == MODE_OFFLINE_EVAL
