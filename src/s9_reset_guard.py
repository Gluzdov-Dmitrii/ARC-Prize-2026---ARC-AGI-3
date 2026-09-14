"""S9 consecutive-RESET wipe guard.

Official RESET: if no ACTION has been taken since the last level
transition, RESET restarts the whole game. Two RESETs in a row therefore
wipe completed levels. Duck already auto-RESET on GAME_OVER; a model
RESET immediately after that (or a RESET,RESET batch) is the wipe.

This module is the single causal change for experiment S9 on the S4 parent:

- drop a parsed RESET when the previous executed engine action was RESET;
- drop extra RESETs inside one batch after the first;
- leave Duck auto-RESET on GAME_OVER untouched;
- do not change memory, HUD, animation, scheduler, or UNDO.

S1/S2/S3/S4b/S5/S6/S7/S8 are not stacked. S4 top-HUD no-impact stays.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any, Callable

S9_EXPERIMENT_ID = "S9"
S9_TELEMETRY_NAME = "s9_telemetry.json"
S9_PATCH_FLAG = "_arc_s9_patched"
RESET_NAME = "RESET"
SKIP_ERROR = (
    "Consecutive RESET skipped; a second RESET restarts the whole game "
    "from level 1 and wipes completed levels."
)

_LOCK = threading.Lock()
_WORKING_DIR: Path | None = None
_INSTALLED = False
_COUNTERS = {
    "batches_seen": 0,
    "resets_seen": 0,
    "resets_dropped": 0,
    "batches_filtered": 0,
}


def reset_counters() -> None:
    with _LOCK:
        for key in _COUNTERS:
            _COUNTERS[key] = 0


def bump(name: str, amount: int = 1) -> None:
    with _LOCK:
        _COUNTERS[name] = int(_COUNTERS.get(name, 0)) + int(amount)


def action_name(action: Any) -> str:
    ident = getattr(action, "id", action)
    name = getattr(ident, "name", ident)
    return str(name or "").strip().upper()


def is_reset_action(action: Any) -> bool:
    return action_name(action) == RESET_NAME


def last_engine_reset(session: Any) -> bool:
    last = getattr(session, "last_engine_action", None)
    return str(last or "").strip().upper() == RESET_NAME


def filter_consecutive_resets(
    actions: list[Any] | None,
    last_engine_action: str | None,
) -> tuple[list[Any], int]:
    items = list(actions or [])
    dropped = 0
    kept: list[Any] = []
    prev = str(last_engine_action or "").strip().upper()
    for action in items:
        if is_reset_action(action) and prev == RESET_NAME:
            dropped += 1
            continue
        kept.append(action)
        prev = action_name(action) if action_name(action) else prev
    return kept, dropped


def wrap_normalize_actions(original: Callable[..., Any]) -> Callable[..., Any]:
    def wrapped(self: Any, arguments: dict[str, Any]) -> Any:
        actions, error = original(self, arguments)
        bump("batches_seen")
        if error or not actions:
            return actions, error
        resets = sum(1 for item in actions if is_reset_action(item))
        if resets:
            bump("resets_seen", resets)
        kept, dropped = filter_consecutive_resets(
            list(actions),
            getattr(self, "last_engine_action", None),
        )
        if dropped:
            bump("resets_dropped", dropped)
            bump("batches_filtered")
            print(
                "S9_RESET_GUARD "
                f"dropped={dropped} kept={len(kept)} "
                f"last={getattr(self, 'last_engine_action', None)!r}",
                flush=True,
            )
        if not kept:
            return None, SKIP_ERROR
        return kept, None

    setattr(wrapped, S9_PATCH_FLAG, True)
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
    return Path(working_dir) / S9_TELEMETRY_NAME


def write_telemetry(working_dir: Path, payload: dict[str, Any]) -> Path | None:
    path = telemetry_path(working_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        print(f"S9 telemetry written: {path}", flush=True)
        return path
    except Exception as exc:
        print(f"S9 telemetry write failed: {exc!r}", flush=True)
        return None


def install_s9_hooks(
    bm: Any,
    *,
    target: Any | None = None,
    working_dir: Path,
    bundle_dir: Path | None = None,
    extra: dict[str, Any] | None = None,
    source_text: str | None = None,
) -> dict[str, Any]:
    global _INSTALLED, _WORKING_DIR

    _WORKING_DIR = Path(working_dir)
    reset_counters()

    session_cls = harness_session_class()
    session_wrapped = False
    if session_cls is not None:
        norm_fn = getattr(session_cls, "_normalize_actions", None)
        if callable(norm_fn) and not getattr(norm_fn, S9_PATCH_FLAG, False):
            session_cls._normalize_actions = wrap_normalize_actions(  # type: ignore[method-assign]
                norm_fn
            )
            session_wrapped = True

    orig_run = bm.run
    if not getattr(orig_run, S9_PATCH_FLAG, False):

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

        setattr(wrapped_run, S9_PATCH_FLAG, True)
        bm.run = wrapped_run

    _INSTALLED = True
    payload = {
        "experiment_id": S9_EXPERIMENT_ID,
        "single_change": (
            "drop consecutive RESET so a second RESET cannot wipe completed levels"
        ),
        "session_class_found": session_cls is not None,
        "session_wrapped": session_wrapped,
        "s1_not_stacked": True,
        "s2_not_stacked": True,
        "s3_not_stacked": True,
        "s4b_not_stacked": True,
        "s5_not_stacked": True,
        "s6_not_stacked": True,
        "s7_not_stacked": True,
        "s8_not_stacked": True,
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
        "S9_RESET_GUARD "
        f"session_wrapped={session_wrapped} "
        "telemetry=" + str(telemetry_path(Path(working_dir))),
        flush=True,
    )
    return payload
