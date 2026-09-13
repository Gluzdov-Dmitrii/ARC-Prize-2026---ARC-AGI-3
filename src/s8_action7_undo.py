"""S8 ACTION7/UNDO completeness: map gateway undo into Duck labels.

Duck lists engine available_actions but its ENGINE_TO_MODEL_ACTION table
omits ACTION7, so to_engine_action("ACTION7") and to_engine_action("UNDO")
return None. Official ARC-AGI-3 ACTION7 is undo and is legal only when the
frame lists it. This module is the single causal change for experiment S8
on the S4 parent:

- patch Duck action-name maps: ACTION7 <-> UNDO;
- when UNDO is in the current valid set, add one short description line;
- do not invent ACTION7 when the gateway did not list it;
- do not change memory, seed, HUD, animation, history, or scheduler.

S1/S2/S3/S4b/S5/S6/S7 are not stacked. S4 top-HUD no-impact stays.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any, Callable

S8_EXPERIMENT_ID = "S8"
S8_TELEMETRY_NAME = "s8_telemetry.json"
S8_PATCH_FLAG = "_arc_s8_patched"
ENGINE_UNDO = "ACTION7"
MODEL_UNDO = "UNDO"
UNDO_HINT = (
    "UNDO reverses the last action when listed; prefer one UNDO over RESET "
    "and do not spam it."
)

_LOCK = threading.Lock()
_WORKING_DIR: Path | None = None
_INSTALLED = False
_COUNTERS = {
    "maps_patched": 0,
    "undo_listed": 0,
    "undo_requested": 0,
    "undo_parsed": 0,
}


def reset_counters() -> None:
    with _LOCK:
        for key in _COUNTERS:
            _COUNTERS[key] = 0


def bump(name: str, amount: int = 1) -> None:
    with _LOCK:
        _COUNTERS[name] = int(_COUNTERS.get(name, 0)) + int(amount)


def apply_action7_map(engine_to_model: dict[str, str], model_to_engine: dict[str, str]) -> None:
    engine_to_model[ENGINE_UNDO] = MODEL_UNDO
    model_to_engine[MODEL_UNDO] = ENGINE_UNDO


def duck_to_model_action(name: str | None, engine_to_model: dict[str, str]) -> str:
    raw = str(name or "").strip().upper()
    return engine_to_model.get(raw, raw)


def duck_to_engine_action(
    name: str | None,
    engine_to_model: dict[str, str],
    model_to_engine: dict[str, str],
) -> str | None:
    raw = str(name or "").strip().upper()
    if not raw:
        return None
    if raw in engine_to_model:
        return raw
    return model_to_engine.get(raw)


def duck_to_model_actions(names: list[str] | None, engine_to_model: dict[str, str]) -> list[str]:
    resolved: list[str] = []
    for name in names or []:
        label = duck_to_model_action(name, engine_to_model)
        if label and label not in resolved:
            resolved.append(label)
    return resolved


def format_valid_action_line(base_line: str, model_names: list[str]) -> str:
    line = str(base_line or "").rstrip()
    if MODEL_UNDO not in {str(name).strip().upper() for name in model_names}:
        return str(base_line or "")
    bump("undo_listed")
    if not line:
        return UNDO_HINT
    if line.endswith("."):
        line = line[:-1]
    return f"{line}. {UNDO_HINT}"


def count_undo_labels(raw_actions: Any) -> int:
    if isinstance(raw_actions, dict):
        items = [raw_actions]
    elif isinstance(raw_actions, (list, tuple)):
        items = list(raw_actions)
    else:
        return 0
    n = 0
    for item in items:
        if isinstance(item, str):
            label = item
        elif isinstance(item, dict):
            label = item.get("action")
        else:
            label = getattr(item, "action", None)
        raw = str(label or "").strip().upper()
        if raw in {MODEL_UNDO, ENGINE_UNDO}:
            n += 1
    return n


def action_is_undo(action: Any) -> bool:
    ident = getattr(action, "id", action)
    name = getattr(ident, "name", ident)
    return str(name or "").strip().upper() in {MODEL_UNDO, ENGINE_UNDO}


def wrap_format_valid_action_line(
    original: Callable[..., str],
    normalize: Callable[..., list[str]],
) -> Callable[..., str]:
    def wrapped(valid_actions: list[str] | None) -> str:
        line = original(valid_actions)
        names = list(normalize(valid_actions) or [])
        return format_valid_action_line(line, names)

    setattr(wrapped, S8_PATCH_FLAG, True)
    return wrapped


def wrap_normalize_actions(original: Callable[..., Any]) -> Callable[..., Any]:
    def wrapped(self: Any, arguments: dict[str, Any]) -> Any:
        payload = arguments if isinstance(arguments, dict) else {}
        raw = payload.get("actions")
        if raw is None:
            raw = [{"action": payload.get("action")}]
        requested = count_undo_labels(raw)
        if requested:
            bump("undo_requested", requested)
        actions, error = original(self, arguments)
        if actions:
            parsed = sum(1 for item in actions if action_is_undo(item))
            if parsed:
                bump("undo_parsed", parsed)
        return actions, error

    setattr(wrapped, S8_PATCH_FLAG, True)
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
        if hasattr(obj, "_normalize_actions") and hasattr(obj, "play"):
            return obj
    return None


def telemetry_path(working_dir: Path) -> Path:
    return Path(working_dir) / S8_TELEMETRY_NAME


def write_telemetry(working_dir: Path, payload: dict[str, Any]) -> Path | None:
    path = telemetry_path(working_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        print(f"S8 telemetry written: {path}", flush=True)
        return path
    except Exception as exc:
        print(f"S8 telemetry write failed: {exc!r}", flush=True)
        return None


def install_s8_hooks(
    bm: Any,
    *,
    target: Any | None = None,
    working_dir: Path,
    bundle_dir: Path | None = None,
    extra: dict[str, Any] | None = None,
    source_text: str | None = None,
) -> dict[str, Any]:
    global _INSTALLED, _WORKING_DIR

    from inference.agent import action_names as an
    from inference.agent import tool_agent as ta

    _WORKING_DIR = Path(working_dir)
    reset_counters()

    engine_map = getattr(an, "ENGINE_TO_MODEL_ACTION", None)
    model_map = getattr(an, "MODEL_TO_ENGINE_ACTION", None)
    if not isinstance(engine_map, dict) or not isinstance(model_map, dict):
        raise RuntimeError("Duck action_names maps were not found; refuse silent S8 no-op.")
    apply_action7_map(engine_map, model_map)
    bump("maps_patched")

    format_fn = getattr(ta, "_format_valid_action_line", None)
    normalize_fn = getattr(ta, "_normalize_valid_actions", None)
    format_wrapped = False
    if callable(format_fn) and callable(normalize_fn) and not getattr(format_fn, S8_PATCH_FLAG, False):
        ta._format_valid_action_line = wrap_format_valid_action_line(  # type: ignore[attr-defined]
            format_fn, normalize_fn
        )
        format_wrapped = True

    session_cls = harness_session_class()
    session_wrapped = False
    if session_cls is not None:
        norm_fn = getattr(session_cls, "_normalize_actions", None)
        if callable(norm_fn) and not getattr(norm_fn, S8_PATCH_FLAG, False):
            session_cls._normalize_actions = wrap_normalize_actions(  # type: ignore[method-assign]
                norm_fn
            )
            session_wrapped = True

    orig_run = bm.run
    if not getattr(orig_run, S8_PATCH_FLAG, False):

        async def wrapped_run(*args: Any, **kwargs: Any) -> Any:
            started = time.perf_counter()
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
                    payload["counters"] = dict(_COUNTERS)
                payload["runtime_seconds"] = time.perf_counter() - started
                payload["finished_at_epoch"] = time.time()
                write_telemetry(Path(working_dir), payload)

        setattr(wrapped_run, S8_PATCH_FLAG, True)
        bm.run = wrapped_run

    _INSTALLED = True
    payload = {
        "experiment_id": S8_EXPERIMENT_ID,
        "single_change": (
            "map gateway ACTION7 to model UNDO so listed undo is executable"
        ),
        "engine_undo": ENGINE_UNDO,
        "model_undo": MODEL_UNDO,
        "action_names_found": True,
        "format_wrapped": format_wrapped,
        "session_class_found": session_cls is not None,
        "session_wrapped": session_wrapped,
        "s1_not_stacked": True,
        "s2_not_stacked": True,
        "s3_not_stacked": True,
        "s4b_not_stacked": True,
        "s5_not_stacked": True,
        "s6_not_stacked": True,
        "s7_not_stacked": True,
        "s4_retained": True,
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
    print(
        "S8_ACTION7_UNDO "
        f"engine={ENGINE_UNDO} model={MODEL_UNDO} "
        f"format_wrapped={format_wrapped} session_wrapped={session_wrapped} "
        "telemetry=" + str(telemetry_path(Path(working_dir))),
        flush=True,
    )
    return payload
