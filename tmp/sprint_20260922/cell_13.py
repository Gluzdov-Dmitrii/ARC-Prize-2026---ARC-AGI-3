

# === S4 semantic no-impact + P0a short Phase A ===
# Packaging: competition rerun keeps production budgets. Offline Save & Run is a
# short smoke. Policy change is S4 no-impact memory only. S1/S2/S3 not stacked.
P0_SOURCE = r'''"""P0a: short Kaggle Phase A smoke vs unchanged competition rerun.

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
'''
S4_SOURCE = r'''"""S4 semantic no-impact guard: HUD-insensitive repeats, not a global ban.

Single causal change: compare frames after stripping the top HUD strip, remember
``(semantic_state, action)`` only after a confirmed no-interior-change repeat,
and tell the model. Real interior motion and animations are not banned.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any, Callable

S4_EXPERIMENT_ID = "S4"
S4_TELEMETRY_NAME = "s4_telemetry.json"
S4_PATCH_FLAG = "_arc_s4_patched"
HUD_TOP_ROWS = 2
CONFIRM_REPEATS = 2

Grid = list[list[int]]

_LOCK = threading.Lock()
_COUNTERS = {
    "transitions": 0,
    "identical": 0,
    "hud_only": 0,
    "real_change": 0,
    "confirmed_no_impact": 0,
}


def parse_grid(value: Any) -> Grid | None:
    if value is None:
        return None
    if isinstance(value, dict) and "grid" in value:
        value = value["grid"]
    rows: Grid = []
    if isinstance(value, str):
        for line in value.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            rows.append([int(ch) if ch.isdigit() else ord(ch) % 16 for ch in stripped])
    else:
        try:
            for row in value:
                rows.append([int(cell) for cell in row])
        except (TypeError, ValueError):
            return None
    if not rows or not rows[0]:
        return None
    width = len(rows[0])
    if any(len(row) != width for row in rows):
        return None
    return rows


def strip_hud(grid: Grid, *, top_rows: int = HUD_TOP_ROWS) -> Grid:
    if len(grid) <= top_rows:
        return [list(row) for row in grid]
    return [list(row) for row in grid[top_rows:]]


def semantic_key(grid: Grid, *, top_rows: int = HUD_TOP_ROWS) -> str:
    interior = strip_hud(grid, top_rows=top_rows)
    payload = json.dumps(interior, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def classify_transition(
    before: Grid,
    after: Grid,
    *,
    top_rows: int = HUD_TOP_ROWS,
) -> str:
    if before == after:
        return "identical"
    if semantic_key(before, top_rows=top_rows) == semantic_key(after, top_rows=top_rows):
        return "hud_only"
    return "real_change"


def action_key(action: Any) -> str:
    if isinstance(action, dict):
        name = str(action.get("action") or action.get("action_display") or "").strip()
        row = action.get("row")
        col = action.get("col")
        if row is not None or col is not None:
            return f"{name}:{row}:{col}"
        return name
    return str(action or "").strip()


class NoImpactBook:
    """Per-game memory. Layout-specific; caller must reset on level change."""

    def __init__(self, *, confirm_repeats: int = CONFIRM_REPEATS) -> None:
        self.confirm_repeats = confirm_repeats
        self._counts: dict[tuple[str, str], int] = {}
        self._confirmed: set[tuple[str, str]] = set()

    def reset(self) -> None:
        self._counts.clear()
        self._confirmed.clear()

    def observe(self, state_key: str, action: str, kind: str) -> bool:
        pair = (state_key, action)
        if kind == "real_change":
            self._counts.pop(pair, None)
            self._confirmed.discard(pair)
            return False
        if kind not in {"identical", "hud_only"}:
            return False
        self._counts[pair] = self._counts.get(pair, 0) + 1
        if self._counts[pair] >= self.confirm_repeats:
            self._confirmed.add(pair)
            return True
        return False

    def is_no_impact(self, state_key: str, action: str) -> bool:
        return (state_key, action) in self._confirmed

    def notes_for(self, state_key: str) -> list[str]:
        notes = []
        for stored_state, action in sorted(self._confirmed):
            if stored_state == state_key:
                notes.append(
                    f"{action} is confirmed no-impact in this semantic state "
                    "(HUD/timer-only or identical interior); try a different action."
                )
        return notes


def format_no_impact_note(notes: list[str]) -> str:
    if not notes:
        return ""
    return "No-impact memory: " + " ".join(notes)


def inject_no_impact_notes(knowledge: dict[str, str], notes: list[str]) -> None:
    blob = format_no_impact_note(notes)
    if not blob:
        return
    current = str(knowledge.get("recent_findings") or "").strip()
    if blob in current:
        return
    knowledge["recent_findings"] = f"{blob} {current}".strip()


def wrap_run_python_tool(
    original: Callable[..., Any],
    *,
    book: NoImpactBook,
    load_grid: Callable[[Any], Grid | None],
) -> Callable[..., Any]:
    def wrapped(self: Any, state_path: Any, arguments: dict[str, Any]) -> Any:
        before = load_grid(state_path)
        result = original(self, state_path, arguments)
        after = load_grid(state_path)
        summary = getattr(self, "_last_step_summary", None) or {}
        if summary.get("level_transition") or summary.get("run_complete") or summary.get("game_over"):
            book.reset()
            return result
        action = action_key(
            (summary.get("executed_actions") or [None])[-1]
            if isinstance(summary.get("executed_actions"), list)
            else summary.get("executed_actions")
        )
        if not action:
            last = getattr(self, "_last_action_result", None) or {}
            action = action_key(last.get("action_display") or last.get("action"))
        if before is None or after is None or not action:
            return result
        kind = classify_transition(before, after)
        with _LOCK:
            _COUNTERS["transitions"] += 1
            _COUNTERS[kind] = _COUNTERS.get(kind, 0) + 1
        newly = book.observe(semantic_key(before), action, kind)
        if newly:
            with _LOCK:
                _COUNTERS["confirmed_no_impact"] += 1
            print(
                f"S4_NO_IMPACT confirmed action={action} kind={kind}",
                flush=True,
            )
        knowledge = getattr(self, "_summarized_knowledge", None)
        if isinstance(knowledge, dict):
            inject_no_impact_notes(knowledge, book.notes_for(semantic_key(after)))
        return result

    setattr(wrapped, S4_PATCH_FLAG, True)
    return wrapped


def duck_load_grid(state_path: Any) -> Grid | None:
    from inference.agent import tool_agent as ta

    loader = getattr(ta, "load_runtime_state", None)
    if loader is None:
        from inference.runtime_state import load_runtime_state as loader  # type: ignore
    frame, _history = loader(state_path)
    if frame is None:
        return None
    grid = getattr(frame, "grid", None)
    return parse_grid(grid)


def telemetry_path(working_dir: Path) -> Path:
    return Path(working_dir) / S4_TELEMETRY_NAME


def write_telemetry(working_dir: Path, payload: dict[str, Any]) -> Path | None:
    path = telemetry_path(working_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        print(f"S4 telemetry written: {path}", flush=True)
        return path
    except Exception as exc:
        print(f"S4 telemetry write failed: {exc!r}", flush=True)
        return None


def install_s4_hooks(
    bm: Any,
    *,
    target: Any | None = None,
    working_dir: Path,
    bundle_dir: Path | None = None,
    extra: dict[str, Any] | None = None,
    source_text: str | None = None,
) -> dict[str, Any]:
    from inference.agent import tool_agent as ta

    book = NoImpactBook()
    if not getattr(ta.ToolAgent._run_python_tool, S4_PATCH_FLAG, False):
        ta.ToolAgent._run_python_tool = wrap_run_python_tool(  # type: ignore[method-assign]
            ta.ToolAgent._run_python_tool,
            book=book,
            load_grid=duck_load_grid,
        )

    orig_run = bm.run
    if not getattr(orig_run, S4_PATCH_FLAG, False):

        async def wrapped_run(*args: Any, **kwargs: Any) -> Any:
            started = time.perf_counter()
            try:
                return await orig_run(*args, **kwargs)
            finally:
                payload = {}
                path = telemetry_path(Path(working_dir))
                if path.is_file():
                    try:
                        payload = json.loads(path.read_text(encoding="utf-8"))
                    except Exception:
                        payload = {}
                with _LOCK:
                    payload["counters"] = dict(_COUNTERS)
                payload["runtime_seconds"] = time.perf_counter() - started
                payload["finished_at_epoch"] = time.time()
                write_telemetry(Path(working_dir), payload)

        setattr(wrapped_run, S4_PATCH_FLAG, True)
        bm.run = wrapped_run

    payload = {
        "experiment_id": S4_EXPERIMENT_ID,
        "single_change": (
            "HUD-insensitive semantic diff and confirmed state-action no-impact memory"
        ),
        "hud_top_rows": HUD_TOP_ROWS,
        "confirm_repeats": CONFIRM_REPEATS,
        "global_ban": False,
        "s1_not_stacked": True,
        "s2_not_stacked": True,
        "s3_not_stacked": True,
        "installed_at_epoch": time.time(),
        "source_sha256": (
            hashlib.sha256(source_text.encode("utf-8")).hexdigest()
            if source_text is not None
            else None
        ),
        "working_dir": str(working_dir),
        "counters": dict(_COUNTERS),
    }
    if extra:
        payload["extra"] = extra
    if target is not None:
        payload["target_max_runtime_s"] = getattr(target, "max_runtime_s", None)
    if bundle_dir is not None:
        payload["bundle_dir"] = str(bundle_dir)
    write_telemetry(Path(working_dir), payload)
    print("S4 no-impact guard installed: HUD-insensitive confirmed repeats only", flush=True)
    return payload
'''
_p0_ns = {"__name__": "p0_phase_a_modes"}
_s4_ns = {"__name__": "s4_semantic_no_impact"}
exec(P0_SOURCE, _p0_ns)
exec(S4_SOURCE, _s4_ns)
PHASE_A_MODE = _p0_ns["apply_solver_settings"](
    bm, target, true_submission=TRUE_SUBMISSION
)
S4_TELEMETRY = _s4_ns["install_s4_hooks"](
    bm,
    target=target,
    working_dir=WORKING_DIR,
    bundle_dir=BUNDLE_DIR,
    extra={
        "parent_kernel": "dmitriigluzdov/duck-qwen3-8-flash-next-nvfp4-mtp",
        "parent_kernel_version": 3,
        "parent_submission_ref": 55959595,
        "parent_public_score": 3.39,
        "phase_a_mode": PHASE_A_MODE,
        "true_submission": TRUE_SUBMISSION,
        "vllm_profile": PUBLIC25_VLLM_PROFILE_NAME,
        "vllm_profile_env": PUBLIC25_VLLM_PROFILE_ENV,
    },
    source_text=S4_SOURCE,
)
print(
    "S4_NO_IMPACT hud-insensitive telemetry="
    + str(_s4_ns["telemetry_path"](WORKING_DIR)),
    flush=True,
)
