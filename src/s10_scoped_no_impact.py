"""S10: bounded, scoped S4 advice with fresh single-primitive attribution.

This file is embedded verbatim in the submission notebook. It uses only the
stdlib until installation imports the harness. No actions are blocked and no
serving, prompt, or runtime budgets are changed.

Harness contract: _run_python_tool returns step_executed and replaces its
summary only when actions execute. Summary counts include every action command;
runtime frame.step and summary action numbers count primitive actions. Runtime
history contains coordinate-specific action displays and explicit RESET entries.
"""

from __future__ import annotations

from collections import OrderedDict
import functools
import hashlib
import inspect
import json
from pathlib import Path
import threading
import time
from typing import Any, Callable

S10_EXPERIMENT_ID = "S10"
S10_PATCH_FLAG = "_arc_s10_patched"
S10_TELEMETRY_NAME = "s10_telemetry.json"
HUD_TOP_ROWS = 2
CONFIRM_REPEATS = 2
MAX_PATHS_PER_AGENT = 8
MAX_PAIRS_PER_PATH = 512
MAX_NOTES_PER_STATE = 8
_S10_AGENT_ATTRIBUTE = "_arc_s10_memory"
_LOCK = threading.Lock()
_COUNTERS = {
    "transitions": 0, "identical": 0, "hud_only": 0, "real_change": 0,
    "confirmed_no_impact": 0, "skipped_no_action": 0,
    "skipped_multiple_actions": 0, "skipped_unverified": 0,
    "scope_resets": 0, "internal_errors": 0,
}


def _count(name: str) -> None:
    with _LOCK:
        _COUNTERS[name] += 1


def parse_grid(value: Any) -> list[list[int]] | None:
    if isinstance(value, dict):
        value = value.get("grid")
    try:
        if isinstance(value, str):
            rows = [[int(c) if c.isdigit() else ord(c) % 16 for c in line.strip()]
                    for line in value.splitlines() if line.strip()]
        else:
            rows = [[int(cell) for cell in row] for row in value]
    except (TypeError, ValueError):
        return None
    if not rows or not rows[0] or any(len(row) != len(rows[0]) for row in rows):
        return None
    return rows


def semantic_key(grid: list[list[int]]) -> str:
    interior = grid[HUD_TOP_ROWS:] if len(grid) > HUD_TOP_ROWS else grid
    return hashlib.sha256(json.dumps(interior, separators=(",", ":")).encode()).hexdigest()


def classify_transition(before: list[list[int]], after: list[list[int]]) -> str:
    if before == after:
        return "identical"
    return "hud_only" if semantic_key(before) == semantic_key(after) else "real_change"


def action_key(action: Any) -> str:
    if isinstance(action, dict):
        name = str(action.get("action") or action.get("action_display") or "").strip()
        if action.get("row") is not None or action.get("col") is not None:
            return f"{name.upper()}(row={action.get('row')}, col={action.get('col')})"
        return name
    return str(action or "").strip()


class NoImpactBook:
    """LRU-bounded state/action counts belonging to one agent/path/level."""

    def __init__(self, *, confirm_repeats: int = CONFIRM_REPEATS,
                 max_pairs: int = MAX_PAIRS_PER_PATH) -> None:
        self.confirm_repeats = max(1, int(confirm_repeats))
        self.max_pairs = max(1, int(max_pairs))
        self._counts: OrderedDict[tuple[str, str], int] = OrderedDict()

    def reset(self) -> None:
        self._counts.clear()

    def observe(self, state_key: str, action: str, kind: str) -> bool:
        pair = (state_key, action)
        if kind == "real_change":
            self._counts.pop(pair, None)
            return False
        if not action or kind not in {"identical", "hud_only"}:
            return False
        previous = self._counts.pop(pair, 0)
        self._counts[pair] = min(self.confirm_repeats, previous + 1)
        while len(self._counts) > self.max_pairs:
            self._counts.popitem(last=False)
        return previous < self.confirm_repeats <= self._counts[pair]

    def is_no_impact(self, state_key: str, action: str) -> bool:
        return self._counts.get((state_key, action), 0) >= self.confirm_repeats

    def notes_for(self, state_key: str) -> list[str]:
        actions = sorted(action for (state, action), count in self._counts.items()
                         if state == state_key and count >= self.confirm_repeats)
        return [f"{action} is confirmed no-impact in this semantic state "
                "(HUD/timer-only or identical interior); try a different action."
                for action in actions[:MAX_NOTES_PER_STATE]]


def format_no_impact_note(notes: list[str]) -> str:
    return "No-impact memory: " + " ".join(notes) if notes else ""


def load_snapshot(state_path: Any) -> dict[str, Any] | None:
    """Read the documented runtime JSON, including externally executed RESETs."""
    payload = json.loads(Path(state_path).read_text(encoding="utf-8"))
    frame = payload.get("current_frame") or {}
    grid = parse_grid(frame.get("grid"))
    if grid is None:
        return None
    history = payload.get("history") or []
    last = history[-1] if history else {}
    # Both number and last position distinguish repeated RESETs, even if the
    # reset produces an identical frame or resets the engine's action counter.
    resets = [(i, (entry.get("frame") or {}).get("step"))
              for i, entry in enumerate(history)
              if action_key(entry.get("action")).upper() == "RESET"]
    return {
        "grid": grid, "key": semantic_key(grid),
        "step": int(frame["step"]), "level": int(frame["level"]),
        "reset_marker": (len(resets), resets[-1] if resets else None),
        "last_action": action_key(last.get("action")),
        "last_action_step": (last.get("frame") or {}).get("step"),
    }


class ScopedMemory:
    def __init__(self, *, max_paths: int = MAX_PATHS_PER_AGENT,
                 max_pairs: int = MAX_PAIRS_PER_PATH) -> None:
        self.max_paths = max(1, int(max_paths))
        self.max_pairs = max_pairs
        self.paths: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self.note = ""
        self.in_tool = False

    def refresh(self, state_path: Any, *, loader: Callable[[Any], Any] = load_snapshot,
                force: bool = False) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """Reuse only unchanged file snapshots; retain no raw JSON or history.

        The runtime writer atomically replaces the file, so inode/device detect
        replacements even when size and modification time are unchanged. Check
        metadata on both sides of a read, and never cache a racing read. Custom
        loaders retain their original behavior and do not require a real file.
        """
        path = str(Path(state_path).resolve())
        try:
            if loader is not load_snapshot:
                snapshot = loader(state_path)
                scope = self.sync(state_path, snapshot)
                if scope is not None:
                    scope.pop("cache_signature", None)
                return snapshot, scope

            def signature() -> tuple[int, ...]:
                stat = Path(path).stat()
                return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)

            before = signature()
            cached = self.paths.get(path)
            if not force and cached is not None and cached.get("cache_signature") == before:
                snapshot = cached["snapshot"]
                return snapshot, self.sync(state_path, snapshot)
            snapshot = loader(state_path)
            after = signature()
            if before != after:
                # A replacement during the read gets one fresh retry. If the
                # file remains unstable, leave advice empty until a later call.
                snapshot = loader(state_path)
                if after != signature():
                    raise OSError("S10 runtime state changed during snapshot read")
            scope = self.sync(state_path, snapshot)
            if scope is not None:
                scope["cache_signature"] = after
            return snapshot, scope
        except Exception:
            self.paths.pop(path, None)
            self.note = ""
            raise

    def sync(self, state_path: Any, snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
        self.note = ""
        path = str(Path(state_path).resolve())
        if snapshot is None:
            self.paths.pop(path, None)
            return None
        scope = self.paths.pop(path, None)
        if scope is None:
            scope = {"book": NoImpactBook(max_pairs=self.max_pairs), "snapshot": None}
        previous = scope["snapshot"]
        if snapshot is not previous:
            scope.pop("cache_signature", None)
        if previous is not None and (
            snapshot["level"] != previous["level"]
            or snapshot["step"] < previous["step"]
            or snapshot["reset_marker"] != previous["reset_marker"]
        ):
            scope["book"].reset()
            _count("scope_resets")
        scope["snapshot"] = snapshot
        self.paths[path] = scope
        while len(self.paths) > self.max_paths:
            self.paths.popitem(last=False)
        self.note = format_no_impact_note(scope["book"].notes_for(snapshot["key"]))
        return scope


def memory_for(agent: Any) -> ScopedMemory:
    memory = getattr(agent, _S10_AGENT_ATTRIBUTE, None)
    if memory is None:
        memory = ScopedMemory()
        setattr(agent, _S10_AGENT_ATTRIBUTE, memory)
    return memory


def fresh_single_action(result: Any, previous_summary: Any, summary: Any,
                        before: dict[str, Any], after: dict[str, Any]) -> str | None:
    """Reject stale summaries, cancelling batches, and ambiguous attribution."""
    if not getattr(result, "step_executed", False):
        _count("skipped_no_action")
        return None
    if not isinstance(summary, dict) or summary is previous_summary:
        _count("skipped_unverified")
        return None
    if summary.get("executed_count") != 1:
        _count("skipped_multiple_actions")
        return None
    actions = summary.get("executed_actions")
    action = action_key(actions[0]) if isinstance(actions, list) and len(actions) == 1 else ""
    if not action or (
        after["step"] != before["step"] + 1
        or summary.get("start_action_num") != after["step"]
        or summary.get("end_action_num") != after["step"]
        or summary.get("level") != after["level"]
        or after["last_action_step"] != after["step"]
        or after["last_action"] != action
    ):
        _count("skipped_unverified")
        return None
    return action


def wrap_run_python_tool(original: Callable[..., Any], *,
                         loader: Callable[[Any], Any] = load_snapshot) -> Callable[..., Any]:
    @functools.wraps(original)
    def wrapped(self: Any, state_path: Any, arguments: dict[str, Any]) -> Any:
        memory = None
        before = None
        try:
            memory = memory_for(self)
            before, _scope = memory.refresh(state_path, loader=loader)
            memory.in_tool = True
        except Exception:
            _count("internal_errors")
            if memory is not None:
                memory.note = ""
        previous_summary = getattr(self, "_last_step_summary", None)
        # Keep the solver call outside instrumentation exception handling: its
        # original exception and traceback must reach the harness unchanged.
        try:
            result = original(self, state_path, arguments)
        finally:
            if memory is not None:
                memory.in_tool = False
                memory.note = ""
        try:
            if memory is None:
                return result
            after, scope = memory.refresh(state_path, loader=loader,
                                          force=bool(getattr(result, "step_executed", False)))
            if before is None or after is None or scope is None:
                return result
            summary = getattr(self, "_last_step_summary", None)
            fresh_summary = summary if summary is not previous_summary and isinstance(summary, dict) else {}
            reset = before["reset_marker"] != after["reset_marker"]
            terminal = any(fresh_summary.get(k) for k in ("level_transition", "run_complete", "game_over"))
            if reset or terminal or before["level"] != after["level"]:
                scope["book"].reset()
                memory.note = ""
                return result
            action = fresh_single_action(result, previous_summary, summary, before, after)
            if action and action.upper() != "RESET":
                kind = classify_transition(before["grid"], after["grid"])
                _count("transitions")
                _count(kind)
                if scope["book"].observe(before["key"], action, kind):
                    _count("confirmed_no_impact")
            memory.note = format_no_impact_note(scope["book"].notes_for(after["key"]))
        except Exception:
            _count("internal_errors")
            if memory is not None:
                memory.note = ""
        return result
    setattr(wrapped, S10_PATCH_FLAG, True)
    return wrapped


def wrap_ensure_session(original: Callable[..., Any], *,
                        loader: Callable[[Any], Any] = load_snapshot) -> Callable[..., Any]:
    @functools.wraps(original)
    def wrapped(self: Any, state_path: Any) -> Any:
        result = original(self, state_path)
        memory = None
        try:
            memory = memory_for(self)
            if not memory.in_tool:
                memory.refresh(state_path, loader=loader)
        except Exception:
            _count("internal_errors")
            if memory is not None:
                memory.note = ""
        return result
    setattr(wrapped, S10_PATCH_FLAG, True)
    return wrapped


def wrap_knowledge_lines(original: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(original)
    def wrapped(self: Any) -> list[str]:
        lines = original(self)
        try:
            note = memory_for(self).note
            if not note:
                return lines
            rendered = list(lines)
            prefix = "- Recent findings: "
            for index, line in enumerate(rendered):
                if line.startswith(prefix):
                    rendered[index] = prefix + note + " " + line[len(prefix):]
                    return rendered
            if rendered:
                rendered.insert(len(rendered) - 1, prefix + note)
                return rendered
            return ["Working world model carried from earlier turns:", prefix + note,
                    "- Revise any item above immediately if `current_frame` or `history` contradicts it."]
        except Exception:
            _count("internal_errors")
            return lines
    setattr(wrapped, S10_PATCH_FLAG, True)
    return wrapped


def validate_hook_contract(agent_class: Any) -> None:
    for name, arity in (("_run_python_tool", 3), ("_ensure_session", 2),
                        ("_summarized_knowledge_lines", 1), ("_summarize_step_sequence", 2)):
        method = getattr(agent_class, name, None)
        if not callable(method):
            raise RuntimeError(f"S10 harness contract missing callable ToolAgent.{name}")
        try:
            inspect.signature(method).bind(*([None] * arity))
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"S10 incompatible ToolAgent.{name} signature") from exc
    if getattr(agent_class._run_python_tool, "_arc_s4_patched", False):
        raise RuntimeError("S10 replaces S4; do not install the shared S4 hook first.")


def write_telemetry(working_dir: Any, payload: dict[str, Any]) -> Path | None:
    path = Path(working_dir) / S10_TELEMETRY_NAME
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        return path
    except Exception as exc:
        print(f"S10 telemetry write failed: {exc!r}", flush=True)
        return None


def install_s10_hooks(bm: Any, target: Any | None = None, *, working_dir: Path,
                     bundle_dir: Path | None = None, extra: dict[str, Any] | None = None,
                     source_text: str | None = None) -> dict[str, Any]:
    from inference.agent import tool_agent as ta

    validate_hook_contract(ta.ToolAgent)
    if not callable(getattr(bm, "run", None)):
        raise RuntimeError("S10 harness contract missing bm.run")
    if not getattr(ta.ToolAgent._run_python_tool, S10_PATCH_FLAG, False):
        ta.ToolAgent._ensure_session = wrap_ensure_session(ta.ToolAgent._ensure_session)
        ta.ToolAgent._summarized_knowledge_lines = wrap_knowledge_lines(ta.ToolAgent._summarized_knowledge_lines)
        ta.ToolAgent._run_python_tool = wrap_run_python_tool(ta.ToolAgent._run_python_tool)
    payload = {
        "experiment_id": (extra or {}).get("experiment_id", S10_EXPERIMENT_ID),
        "single_change": "Scoped S4 memory with fresh single-primitive attribution",
        "hud_top_rows": HUD_TOP_ROWS, "hud_bottom_rows": 0,
        "confirm_repeats": CONFIRM_REPEATS, "global_ban": False,
        "max_paths_per_agent": MAX_PATHS_PER_AGENT,
        "max_pairs_per_path": MAX_PAIRS_PER_PATH,
        "max_notes_per_state": MAX_NOTES_PER_STATE,
        "knowledge_overlay": True, "s4_replaced": True,
        "installed_at_epoch": time.time(), "working_dir": str(working_dir),
        "bundle_dir": str(bundle_dir) if bundle_dir is not None else None,
        "source_sha256": hashlib.sha256(source_text.encode()).hexdigest() if source_text else None,
        "target_max_runtime_s": getattr(target, "max_runtime_s", None),
        "extra": extra or {}, "counters": dict(_COUNTERS),
    }
    original_run = bm.run
    if not getattr(original_run, S10_PATCH_FLAG, False):
        @functools.wraps(original_run)
        async def wrapped_run(*args: Any, **kwargs: Any) -> Any:
            started = time.perf_counter()
            try:
                return await original_run(*args, **kwargs)
            finally:
                report = dict(payload)
                with _LOCK:
                    report["counters"] = dict(_COUNTERS)
                report["runtime_seconds"] = time.perf_counter() - started
                report["finished_at_epoch"] = time.time()
                write_telemetry(working_dir, report)
        setattr(wrapped_run, S10_PATCH_FLAG, True)
        bm.run = wrapped_run
    write_telemetry(working_dir, payload)
    print("S10 no-impact advice installed: per-agent/path, fresh single primitives, bounded memory", flush=True)
    return payload
