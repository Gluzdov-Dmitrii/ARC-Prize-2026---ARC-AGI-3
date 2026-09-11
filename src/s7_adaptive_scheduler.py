"""S7 adaptive compute scheduler: coverage-first budgets, stuck early-stop.

Duck caps each game at 7920s with concurrency 28. Stuck games can occupy
workers until that cap or the notebook soft deadline, so later hidden games
never start. This module is the single causal change for experiment S7 on
the S4 parent:

- coverage-first wall budget by remaining waves (leftover games / concurrency);
- stop a game after STUCK_STREAK actions with no interior progress and no
  level completion (HUD-only ticks do not count as progress when S4
  classify_transition is supplied);
- if a game is progressing or on a later level, spend leftover time after
  reserving a first-pass slice for unstarted games;
- do not change prompts, memory, HUD policy, seed, or serving flags.

S1/S2/S3/S4b/S6 are not stacked. S4 top-HUD no-impact stays as the retained
champion policy. Short Phase A smoke keeps max_actions=4, so stuck cuts are
disabled when the action cap is below the streak.
"""

from __future__ import annotations

import hashlib
import json
import math
import threading
import time
from pathlib import Path
from typing import Any, Callable

S7_EXPERIMENT_ID = "S7"
S7_TELEMETRY_NAME = "s7_telemetry.json"
S7_PATCH_FLAG = "_arc_s7_patched"
MIN_FIRST_PASS_S = 120.0
STUCK_STREAK = 8
LATE_LEVEL_MIN = 2
PROGRESS_MULTIPLIER = 2.5
LATE_LEVEL_MULTIPLIER = 3.0
PROGRESS_KINDS = ("real_change", "progress", "level_completed")

_LOCK = threading.Lock()
_BOOK: "CoverageBook | None" = None
_CLASSIFY: Callable[..., str] | None = None
_WORKING_DIR: Path | None = None
_INSTALLED = False


def game_id_from(game: Any, index: int = 0) -> str:
    run = getattr(game, "game_run", None)
    if run is not None and getattr(run, "game_id", None):
        return str(run.game_id)
    for attr in ("env_name", "game_id", "name"):
        value = getattr(game, attr, None)
        if value:
            return str(value)
    return str(index)


def grid_from_game(game: Any) -> list[list[int]] | None:
    state = getattr(game, "current_state", None)
    if state is None:
        return None
    frame = getattr(state, "frame", None)
    data = getattr(frame, "data", None) if frame is not None else None
    if data is None:
        data = getattr(state, "grid", None)
    if data is None:
        return None
    rows = data.tolist() if hasattr(data, "tolist") else data
    try:
        return [[int(cell) for cell in row] for row in rows]
    except (TypeError, ValueError):
        return None


def wave_coverage_cap(
    remaining_s: float,
    leftover_games: int,
    concurrency: int,
    *,
    default_max_s: float | None,
    min_first_pass_s: float = MIN_FIRST_PASS_S,
) -> float:
    leftover = max(1, int(leftover_games))
    conc = max(1, int(concurrency))
    remaining = max(0.0, float(remaining_s))
    waves = max(1, math.ceil(leftover / conc))
    cap = remaining / waves
    if default_max_s is not None:
        cap = min(float(default_max_s), cap)
    if remaining >= min_first_pass_s:
        cap = max(min_first_pass_s, cap)
    return cap


def game_cap_seconds(
    *,
    elapsed_s: float,
    remaining_s: float,
    leftover_games: int,
    unstarted_games: int,
    concurrency: int,
    default_max_s: float | None,
    stuck: bool,
    progressing: bool,
    late_level: bool,
    min_first_pass_s: float = MIN_FIRST_PASS_S,
    progress_multiplier: float = PROGRESS_MULTIPLIER,
    late_multiplier: float = LATE_LEVEL_MULTIPLIER,
) -> tuple[float, str]:
    elapsed = max(0.0, float(elapsed_s))
    if stuck:
        return elapsed, "stuck"
    remaining = max(0.0, float(remaining_s))
    base = wave_coverage_cap(
        remaining,
        leftover_games,
        concurrency,
        default_max_s=default_max_s,
        min_first_pass_s=min_first_pass_s,
    )
    if not (progressing or late_level):
        return base, "coverage"
    conc = max(1, int(concurrency))
    unstarted = max(0, int(unstarted_games))
    unstarted_waves = math.ceil(unstarted / conc) if unstarted else 0
    reserve = unstarted_waves * min(base, min_first_pass_s)
    available = max(base, remaining - reserve)
    boosted = base * (late_multiplier if late_level else progress_multiplier)
    cap = max(base, min(available, boosted))
    if default_max_s is not None:
        cap = min(float(default_max_s), cap)
    reason = "late_level" if late_level else "progressing"
    return cap, reason


class CoverageBook:
    def __init__(
        self,
        *,
        notebook_budget_s: float = 32400.0,
        default_max_s: float | None = 7920.0,
        concurrency: int = 28,
        stuck_streak: int = STUCK_STREAK,
        stuck_enabled: bool = True,
        min_first_pass_s: float = MIN_FIRST_PASS_S,
        progress_multiplier: float = PROGRESS_MULTIPLIER,
        late_multiplier: float = LATE_LEVEL_MULTIPLIER,
    ) -> None:
        self.notebook_budget_s = float(notebook_budget_s)
        self.default_max_s = default_max_s
        self.concurrency = max(1, int(concurrency))
        self.stuck_streak = int(stuck_streak)
        self.stuck_enabled = bool(stuck_enabled)
        self.min_first_pass_s = float(min_first_pass_s)
        self.progress_multiplier = float(progress_multiplier)
        self.late_multiplier = float(late_multiplier)
        self.total_games = 0
        self.games: dict[str, dict[str, Any]] = {}
        self.stuck_cuts = 0
        self.coverage_cuts = 0

    def bind_total(self, n: int) -> None:
        self.total_games = max(0, int(n))

    def _record(self, game_id: str) -> dict[str, Any]:
        rec = self.games.get(game_id)
        if rec is None:
            rec = {
                "game_id": game_id,
                "started": False,
                "finished": False,
                "started_monotonic": None,
                "levels_completed": 0,
                "progressing": False,
                "late_level": False,
                "no_progress_streak": 0,
                "stuck": False,
                "steps": 0,
                "last_kind": "",
                "last_reason": "coverage",
                "last_cap_s": None,
                "cut_reason": None,
            }
            self.games[game_id] = rec
        return rec

    @property
    def started_count(self) -> int:
        return sum(1 for rec in self.games.values() if rec["started"])

    @property
    def finished_count(self) -> int:
        return sum(1 for rec in self.games.values() if rec["finished"])

    def leftover_unstarted(self) -> tuple[int, int, int]:
        started = self.started_count
        finished = self.finished_count
        total = self.total_games if self.total_games else max(started, 1)
        leftover = max(1, total - finished)
        unstarted = max(0, total - started)
        return leftover, unstarted, total

    def start_game(self, game_id: str) -> dict[str, Any]:
        rec = self._record(game_id)
        rec["started"] = True
        rec["finished"] = False
        rec["started_monotonic"] = time.monotonic()
        rec["cut_reason"] = None
        return rec

    def finish_game(self, game_id: str) -> dict[str, Any]:
        rec = self._record(game_id)
        rec["finished"] = True
        return rec

    def observe_step(
        self,
        game_id: str,
        *,
        kind: str,
        level_completed: bool = False,
        levels_completed: int = 0,
    ) -> dict[str, Any]:
        rec = self._record(game_id)
        rec["steps"] = int(rec["steps"]) + 1
        rec["last_kind"] = str(kind or "")
        levels = int(levels_completed or 0)
        if levels > int(rec["levels_completed"]):
            rec["levels_completed"] = levels
        if level_completed or kind == "level_completed":
            rec["progressing"] = True
            rec["no_progress_streak"] = 0
            rec["stuck"] = False
            rec["last_kind"] = "level_completed"
            if int(rec["levels_completed"]) < 1:
                rec["levels_completed"] = 1
            if int(rec["levels_completed"]) >= LATE_LEVEL_MIN:
                rec["late_level"] = True
            return rec
        if kind in PROGRESS_KINDS:
            rec["progressing"] = True
            rec["no_progress_streak"] = 0
            rec["stuck"] = False
            if int(rec["levels_completed"]) >= LATE_LEVEL_MIN:
                rec["late_level"] = True
            return rec
        rec["no_progress_streak"] = int(rec["no_progress_streak"]) + 1
        if self.stuck_enabled and int(rec["no_progress_streak"]) >= self.stuck_streak:
            rec["stuck"] = True
        return rec

    def cap_for(
        self,
        game_id: str,
        *,
        elapsed_s: float,
        remaining_s: float,
        default_max_s: float | None = None,
    ) -> tuple[float, str]:
        rec = self._record(game_id)
        leftover, unstarted, _total = self.leftover_unstarted()
        cap, reason = game_cap_seconds(
            elapsed_s=elapsed_s,
            remaining_s=remaining_s,
            leftover_games=leftover,
            unstarted_games=unstarted,
            concurrency=self.concurrency,
            default_max_s=self.default_max_s if default_max_s is None else default_max_s,
            stuck=bool(rec["stuck"]),
            progressing=bool(rec["progressing"]),
            late_level=bool(rec["late_level"]),
            min_first_pass_s=self.min_first_pass_s,
            progress_multiplier=self.progress_multiplier,
            late_multiplier=self.late_multiplier,
        )
        rec["last_cap_s"] = cap
        rec["last_reason"] = reason
        return cap, reason

    def limit_reached(
        self,
        game_id: str,
        *,
        elapsed_s: float,
        remaining_s: float,
        default_max_s: float | None = None,
    ) -> bool:
        cap, reason = self.cap_for(
            game_id,
            elapsed_s=elapsed_s,
            remaining_s=remaining_s,
            default_max_s=default_max_s,
        )
        if elapsed_s < cap:
            return False
        rec = self._record(game_id)
        if rec["cut_reason"] is None:
            rec["cut_reason"] = reason
            if reason == "stuck":
                self.stuck_cuts += 1
            elif reason == "coverage":
                self.coverage_cuts += 1
            print(
                f"S7_SCHEDULER_CUT game={game_id} reason={reason} "
                f"elapsed={elapsed_s:.1f} cap={cap:.1f}",
                flush=True,
            )
        return True

    def snapshot(self) -> dict[str, Any]:
        leftover, unstarted, total = self.leftover_unstarted()
        return {
            "total_games": total,
            "bound_total": self.total_games,
            "started": self.started_count,
            "finished": self.finished_count,
            "leftover": leftover,
            "unstarted": unstarted,
            "concurrency": self.concurrency,
            "stuck_streak": self.stuck_streak,
            "stuck_enabled": self.stuck_enabled,
            "min_first_pass_s": self.min_first_pass_s,
            "stuck_cuts": self.stuck_cuts,
            "coverage_cuts": self.coverage_cuts,
            "progress_extensions": sum(
                1 for rec in self.games.values() if rec["last_reason"] == "progressing"
            ),
            "late_level_extensions": sum(
                1 for rec in self.games.values() if rec["last_reason"] == "late_level"
            ),
            "games": dict(self.games),
        }


def current_book() -> CoverageBook:
    global _BOOK
    if _BOOK is None:
        _BOOK = CoverageBook()
    return _BOOK


def reset_book(**kwargs: Any) -> CoverageBook:
    global _BOOK
    _BOOK = CoverageBook(**kwargs)
    return _BOOK


def kind_from_step(
    payload: dict[str, Any] | None,
    before: list[list[int]] | None,
    after: list[list[int]] | None,
) -> str:
    payload = payload or {}
    if payload.get("level_completed"):
        return "level_completed"
    classify = _CLASSIFY
    if classify is not None and before is not None and after is not None:
        try:
            return str(classify(before, after))
        except Exception:
            pass
    if payload.get("board_changed"):
        return "real_change"
    return "identical"


def remaining_seconds(solver: Any, notebook_budget_s: float) -> float:
    getter = getattr(solver, "soft_time_remaining_seconds", None)
    if callable(getter):
        try:
            value = getter()
            if value is not None:
                return max(0.0, float(value))
        except Exception:
            pass
    return max(0.0, float(notebook_budget_s))


def wrap_runtime_limit_reached(original: Callable[..., Any]) -> Callable[..., Any]:
    def wrapped(self: Any) -> bool:
        if original(self):
            return True
        book = current_book()
        gid = game_id_from(self.game, getattr(self, "game_index", 0))
        started = getattr(self, "started_at", None)
        elapsed = max(0.0, time.monotonic() - float(started)) if started else 0.0
        solver = getattr(self, "solver", None)
        remaining = remaining_seconds(solver, book.notebook_budget_s)
        default_max = getattr(solver, "max_runtime_s_per_game", book.default_max_s)
        with _LOCK:
            return book.limit_reached(
                gid,
                elapsed_s=elapsed,
                remaining_s=remaining,
                default_max_s=default_max,
            )

    setattr(wrapped, S7_PATCH_FLAG, True)
    return wrapped


def wrap_timing_payload(original: Callable[..., Any]) -> Callable[..., Any]:
    def wrapped(self: Any) -> dict[str, Any]:
        payload = original(self)
        if not isinstance(payload, dict):
            return payload
        book = current_book()
        gid = game_id_from(self.game, getattr(self, "game_index", 0))
        elapsed = float(payload.get("run_elapsed_seconds") or 0.0)
        solver = getattr(self, "solver", None)
        remaining = remaining_seconds(solver, book.notebook_budget_s)
        default_max = getattr(solver, "max_runtime_s_per_game", book.default_max_s)
        with _LOCK:
            cap, _reason = book.cap_for(
                gid,
                elapsed_s=elapsed,
                remaining_s=remaining,
                default_max_s=default_max,
            )
        payload["time_remaining_seconds"] = max(0.0, cap - elapsed)
        return payload

    setattr(wrapped, S7_PATCH_FLAG, True)
    return wrapped


def wrap_execute_action(original: Callable[..., Any]) -> Callable[..., Any]:
    def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
        before = grid_from_game(getattr(self, "game", None))
        payload = original(self, *args, **kwargs)
        after = grid_from_game(getattr(self, "game", None))
        if isinstance(payload, dict):
            gid = game_id_from(self.game, getattr(self, "game_index", 0))
            kind = kind_from_step(payload, before, after)
            levels = payload.get("score")
            with _LOCK:
                current_book().observe_step(
                    gid,
                    kind=kind,
                    level_completed=bool(payload.get("level_completed")),
                    levels_completed=int(levels or 0),
                )
        return payload

    setattr(wrapped, S7_PATCH_FLAG, True)
    return wrapped


def wrap_play_one(original: Callable[..., Any]) -> Callable[..., Any]:
    def wrapped(
        self: Any,
        game: Any,
        index: int,
        pass_index: int,
        local_server: Any = None,
    ) -> Any:
        gid = game_id_from(game, index)
        with _LOCK:
            current_book().start_game(gid)
        print(f"S7_SCHEDULER_START game={gid} index={index}", flush=True)
        try:
            return original(self, game, index, pass_index, local_server)
        finally:
            with _LOCK:
                current_book().finish_game(gid)
            if _WORKING_DIR is not None:
                flush_runtime_telemetry(_WORKING_DIR)

    setattr(wrapped, S7_PATCH_FLAG, True)
    return wrapped


def harness_session_class() -> type | None:
    from inference.framework import solver as hs

    cls = getattr(hs, "_HarnessGameSession", None)
    if isinstance(cls, type):
        return cls
    for name in dir(hs):
        obj = getattr(hs, name)
        if not isinstance(obj, type):
            continue
        if (
            hasattr(obj, "runtime_limit_reached")
            and hasattr(obj, "should_stop")
            and (hasattr(obj, "_execute_action") or hasattr(obj, "step_env"))
        ):
            return obj
    return None


def telemetry_path(working_dir: Path) -> Path:
    return Path(working_dir) / S7_TELEMETRY_NAME


def write_telemetry(working_dir: Path, payload: dict[str, Any]) -> Path | None:
    path = telemetry_path(working_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        print(f"S7 telemetry written: {path}", flush=True)
        return path
    except Exception as exc:
        print(f"S7 telemetry write failed: {exc!r}", flush=True)
        return None


def flush_runtime_telemetry(working_dir: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    path = telemetry_path(working_dir)
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
    with _LOCK:
        payload["book"] = current_book().snapshot()
    payload["finished_at_epoch"] = time.time()
    write_telemetry(working_dir, payload)
    return payload


def install_s7_hooks(
    bm: Any,
    *,
    target: Any | None = None,
    working_dir: Path,
    bundle_dir: Path | None = None,
    extra: dict[str, Any] | None = None,
    source_text: str | None = None,
    classify_transition: Callable[..., str] | None = None,
) -> dict[str, Any]:
    """Patch session runtime caps + play_one coverage book; write telemetry."""
    global _INSTALLED, _CLASSIFY, _WORKING_DIR, _BOOK

    from inference.framework.solver import HarnessSolver

    _WORKING_DIR = Path(working_dir)
    _CLASSIFY = classify_transition
    solver = getattr(bm, "solver", None)
    max_actions = getattr(solver, "max_actions_per_game", None) if solver else None
    try:
        action_cap = int(max_actions) if max_actions is not None else None
    except (TypeError, ValueError):
        action_cap = None
    stuck_enabled = action_cap is None or action_cap >= STUCK_STREAK
    notebook_budget = float(getattr(target, "max_runtime_s", 32400.0) or 32400.0)
    default_max = getattr(solver, "max_runtime_s_per_game", 7920.0) if solver else 7920.0
    concurrency = int(getattr(solver, "concurrency", 28) or 28) if solver else 28
    _BOOK = CoverageBook(
        notebook_budget_s=notebook_budget,
        default_max_s=default_max,
        concurrency=concurrency,
        stuck_streak=STUCK_STREAK,
        stuck_enabled=stuck_enabled,
        min_first_pass_s=MIN_FIRST_PASS_S,
    )
    games = getattr(bm, "games", None)
    if games is not None:
        try:
            _BOOK.bind_total(len(games))
        except TypeError:
            pass

    if not getattr(HarnessSolver._play_one, S7_PATCH_FLAG, False):
        HarnessSolver._play_one = wrap_play_one(HarnessSolver._play_one)  # type: ignore[method-assign]

    session_cls = harness_session_class()
    if session_cls is not None:
        limit_fn = getattr(session_cls, "runtime_limit_reached", None)
        if callable(limit_fn) and not getattr(limit_fn, S7_PATCH_FLAG, False):
            session_cls.runtime_limit_reached = wrap_runtime_limit_reached(  # type: ignore[method-assign]
                limit_fn
            )
        timing_fn = getattr(session_cls, "timing_payload", None)
        if callable(timing_fn) and not getattr(timing_fn, S7_PATCH_FLAG, False):
            session_cls.timing_payload = wrap_timing_payload(  # type: ignore[method-assign]
                timing_fn
            )
        exec_fn = getattr(session_cls, "_execute_action", None)
        if callable(exec_fn) and not getattr(exec_fn, S7_PATCH_FLAG, False):
            session_cls._execute_action = wrap_execute_action(  # type: ignore[method-assign]
                exec_fn
            )

    orig_run = bm.run
    if not getattr(orig_run, S7_PATCH_FLAG, False):

        async def wrapped_run(*args: Any, **kwargs: Any) -> Any:
            started = time.perf_counter()
            games_now = getattr(bm, "games", None)
            if games_now is not None:
                try:
                    with _LOCK:
                        current_book().bind_total(len(games_now))
                except TypeError:
                    pass
            try:
                return await orig_run(*args, **kwargs)
            finally:
                payload: dict[str, Any] = {}
                path = telemetry_path(Path(working_dir))
                if path.is_file():
                    try:
                        payload = json.loads(path.read_text(encoding="utf-8"))
                    except Exception:
                        payload = {}
                with _LOCK:
                    payload["book"] = current_book().snapshot()
                payload["runtime_seconds"] = time.perf_counter() - started
                payload["finished_at_epoch"] = time.time()
                write_telemetry(Path(working_dir), payload)

        setattr(wrapped_run, S7_PATCH_FLAG, True)
        bm.run = wrapped_run

    _INSTALLED = True
    payload = {
        "experiment_id": S7_EXPERIMENT_ID,
        "single_change": (
            "progress-aware game budget allocation with full hidden-set coverage first"
        ),
        "stuck_streak": STUCK_STREAK,
        "stuck_enabled": stuck_enabled,
        "min_first_pass_s": MIN_FIRST_PASS_S,
        "progress_multiplier": PROGRESS_MULTIPLIER,
        "late_level_multiplier": LATE_LEVEL_MULTIPLIER,
        "late_level_min": LATE_LEVEL_MIN,
        "classify_bound": classify_transition is not None,
        "session_class_found": session_cls is not None,
        "s1_not_stacked": True,
        "s2_not_stacked": True,
        "s3_not_stacked": True,
        "s4b_not_stacked": True,
        "s6_not_stacked": True,
        "s4_retained": True,
        "installed_at_epoch": time.time(),
        "source_sha256": (
            hashlib.sha256(source_text.encode("utf-8")).hexdigest()
            if source_text is not None
            else None
        ),
        "working_dir": str(working_dir),
        "book": _BOOK.snapshot(),
    }
    if extra:
        payload["extra"] = extra
    if target is not None:
        payload["target_max_runtime_s"] = getattr(target, "max_runtime_s", None)
    if bundle_dir is not None:
        payload["bundle_dir"] = str(bundle_dir)
    write_telemetry(Path(working_dir), payload)
    print(
        "S7_ADAPTIVE_SCHEDULER "
        f"stuck_streak={STUCK_STREAK} stuck_enabled={stuck_enabled} "
        f"concurrency={concurrency} telemetry="
        + str(telemetry_path(Path(working_dir))),
        flush=True,
    )
    return payload
