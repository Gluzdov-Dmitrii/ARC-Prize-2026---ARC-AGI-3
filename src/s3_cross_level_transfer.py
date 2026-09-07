"""S3 cross-level transfer: keep confirmed mechanics, drop layout at level change.

Duck currently blanks world/goal/action memory on ``level_completed``. Later
levels usually reuse the same controls and win condition but a new layout, so
that wipe throws away transferable facts and still leaves coordinate-heavy
plans if the model stuffed them into ``cross_level_notes``.

This module is the single causal change for experiment S3:

- on a level transition, keep only confirmed controls, action effects, and
  goal invariants in world/goal/action memory;
- drop coordinate, layout, and current-plan text;
- leave ``cross_level_notes`` in place (Duck already preserves that field);
- keep Duck's full wipe on ``run_complete`` / ``game_over``.

Prompts, seed, scheduler, temperature, and serving flags are untouched.
S1 seed and S2 reasoning-capture are not stacked.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable

S3_EXPERIMENT_ID = "S3"
S3_TELEMETRY_NAME = "s3_telemetry.json"
S3_PATCH_FLAG = "_arc_s3_patched"

KNOWLEDGE_KEYS = (
    "world_model",
    "goal_model",
    "action_model",
    "recent_findings",
    "open_questions",
    "current_plan",
    "cross_level_notes",
)
RETAIN_KEYS = ("world_model", "goal_model", "action_model")
CLEAR_KEYS = ("recent_findings", "open_questions", "current_plan")

LAYOUT_RE = re.compile(
    r"(?:"
    r"\(\s*\d+\s*,\s*\d+\s*\)"
    r"|\b(?:row|col(?:umn)?s?|cell|pixel|coord(?:inate)?s?)\s*[=:#]?\s*\d+"
    r"|\b(?:r\d+\s*c\d+|x\s*=\s*\d+|y\s*=\s*\d+)"
    r"|\bat\s+\(\s*\d+"
    r"|\b\d+\s*,\s*\d+\b"
    r"|\b(?:top|bottom|left|right|upper|lower|center|middle)\s+"
    r"(?:row|col(?:umn)?|edge|corner|side|half|third)"
    r"|\b(?:this|current|new)\s+(?:level|map|layout|room|board|grid|scene)\b"
    r"|\b(?:layout|map layout|walls?\s+at|grid position)\b"
    r"|\b(?:click|tap)\s+(?:at|on)\s+(?:the\s+)?(?:cell|tile|pixel|square)"
    r")",
    re.IGNORECASE,
)
CONTROL_RE = re.compile(
    r"\b(?:ACTION[1-7]|SPACE|RESET|hotkeys?|controls?|button|arrow keys?|WASD|"
    r"click(?:s|ing)?|press(?:es|ing)?|key)\b",
    re.IGNORECASE,
)
EFFECT_RE = re.compile(
    r"\b(?:toggl\w*|moves?|moving|picks? up|drops?|rotat\w*|swaps?|teleports?|"
    r"opens?|closes?|paints?|copies?|causes?|results? in|effect|no-?op)\b",
    re.IGNORECASE,
)
GOAL_RE = re.compile(
    r"\b(?:goals?|win(?:s|ning|condition)?|reach(?:es|ing)?|collect(?:s|ing)?|"
    r"match(?:es|ing)?|exit|objectiv\w*|invariant|complet(?:e|es|ing|ion))\b",
    re.IGNORECASE,
)

_CTX_LOCK = threading.Lock()
_COUNTERS = {
    "level_transitions": 0,
    "sentences_kept": 0,
    "sentences_dropped": 0,
    "plans_cleared": 0,
}
_INSTALLED = False


def split_facts(text: str) -> list[str]:
    if not str(text or "").strip():
        return []
    facts: list[str] = []
    for raw_line in str(text).splitlines():
        line = raw_line.strip().lstrip("-*").strip()
        if not line:
            continue
        for part in re.split(r"(?<=[.!;])\s+", line):
            fact = " ".join(part.split())
            if fact:
                facts.append(fact)
    return facts


def join_facts(facts: list[str]) -> str:
    return " ".join(item.rstrip() for item in facts if item and item.strip())


def is_layout_specific(text: str) -> bool:
    return bool(LAYOUT_RE.search(text or ""))


def is_confirmed_mechanic(text: str) -> bool:
    blob = text or ""
    return bool(CONTROL_RE.search(blob) or EFFECT_RE.search(blob) or GOAL_RE.search(blob))


def is_transferable_fact(text: str) -> bool:
    return is_confirmed_mechanic(text) and not is_layout_specific(text)


def filter_transferable_text(text: str) -> dict[str, Any]:
    kept: list[str] = []
    dropped: list[str] = []
    for fact in split_facts(text):
        if is_transferable_fact(fact):
            kept.append(fact)
        else:
            dropped.append(fact)
    return {
        "text": join_facts(kept),
        "kept": kept,
        "dropped": dropped,
    }


def apply_cross_level_transfer(knowledge: dict[str, str]) -> dict[str, Any]:
    """Mutate Duck summarized knowledge at a level boundary. Return stats."""
    kept: list[str] = []
    dropped: list[str] = []
    before_plan = str(knowledge.get("current_plan") or "")
    for key in RETAIN_KEYS:
        filtered = filter_transferable_text(knowledge.get(key, ""))
        knowledge[key] = filtered["text"]
        kept.extend(filtered["kept"])
        dropped.extend(filtered["dropped"])
    for key in CLEAR_KEYS:
        value = str(knowledge.get(key) or "")
        if value.strip():
            dropped.extend(split_facts(value) or [value.strip()])
        knowledge[key] = ""
    # Duck already keeps cross_level_notes; do not rewrite it here.
    stats = {
        "kept": kept,
        "dropped": dropped,
        "kept_count": len(kept),
        "dropped_count": len(dropped),
        "plan_cleared": bool(before_plan.strip()),
        "retained_fields": {
            key: knowledge.get(key, "") for key in (*RETAIN_KEYS, "cross_level_notes")
        },
    }
    with _CTX_LOCK:
        _COUNTERS["level_transitions"] += 1
        _COUNTERS["sentences_kept"] += stats["kept_count"]
        _COUNTERS["sentences_dropped"] += stats["dropped_count"]
        if stats["plan_cleared"]:
            _COUNTERS["plans_cleared"] += 1
        snapshot = dict(_COUNTERS)
    stats["counters"] = snapshot
    return stats


def wrap_update_from_step_summary(original: Callable[..., Any]) -> Callable[..., Any]:
    def wrapped(self: Any) -> None:
        summary = getattr(self, "_last_step_summary", None) or {}
        if (
            summary.get("level_transition")
            and not summary.get("run_complete")
            and not summary.get("game_over")
        ):
            knowledge = getattr(self, "_summarized_knowledge", None)
            if not isinstance(knowledge, dict):
                self._summarized_knowledge = {key: "" for key in KNOWLEDGE_KEYS}
                knowledge = self._summarized_knowledge
            stats = apply_cross_level_transfer(knowledge)
            print(
                "S3_LEVEL_TRANSFER "
                f"kept={stats['kept_count']} dropped={stats['dropped_count']} "
                f"plan_cleared={int(stats['plan_cleared'])}",
                flush=True,
            )
            return
        return original(self)

    setattr(wrapped, S3_PATCH_FLAG, True)
    return wrapped


def file_sha256(path: Path) -> str | None:
    try:
        if not path.is_file():
            return None
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def telemetry_path(working_dir: Path) -> Path:
    return Path(working_dir) / S3_TELEMETRY_NAME


def write_telemetry(working_dir: Path, payload: dict[str, Any]) -> Path | None:
    path = telemetry_path(working_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        print(f"S3 telemetry written: {path}", flush=True)
        return path
    except Exception as exc:
        print(f"S3 telemetry write failed: {exc!r}", flush=True)
        return None


def update_telemetry(working_dir: Path, **fields: Any) -> dict[str, Any] | None:
    path = telemetry_path(working_dir)
    payload: dict[str, Any] = {}
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
    payload.update(fields)
    with _CTX_LOCK:
        payload["counters"] = dict(_COUNTERS)
    write_telemetry(working_dir, payload)
    return payload


def reset_counters() -> None:
    with _CTX_LOCK:
        for key in _COUNTERS:
            _COUNTERS[key] = 0


def install_s3_hooks(
    bm: Any,
    *,
    target: Any | None = None,
    working_dir: Path,
    bundle_dir: Path | None = None,
    extra: dict[str, Any] | None = None,
    source_text: str | None = None,
) -> dict[str, Any]:
    """Patch Duck level-transition memory to keep mechanics and drop layout."""
    global _INSTALLED

    from inference.agent import tool_agent as ta

    if not getattr(
        ta.ToolAgent._update_summarized_knowledge_from_step_summary, S3_PATCH_FLAG, False
    ):
        ta.ToolAgent._update_summarized_knowledge_from_step_summary = (  # type: ignore[method-assign]
            wrap_update_from_step_summary(
                ta.ToolAgent._update_summarized_knowledge_from_step_summary
            )
        )

    orig_run = bm.run
    if not getattr(orig_run, S3_PATCH_FLAG, False):

        async def wrapped_run(*args: Any, **kwargs: Any) -> Any:
            started = time.perf_counter()
            try:
                return await orig_run(*args, **kwargs)
            finally:
                update_telemetry(
                    Path(working_dir),
                    runtime_seconds=time.perf_counter() - started,
                    finished_at_epoch=time.time(),
                )

        setattr(wrapped_run, S3_PATCH_FLAG, True)
        bm.run = wrapped_run

    _INSTALLED = True
    reset_counters()
    hashes = {}
    if bundle_dir is not None:
        bundle = Path(bundle_dir)
        for name in (
            "setup_commands.json",
            "teardown_commands.json",
            "serving_setup.py",
            "vllm_server_watchdog.py",
            "taaf-kaggle-bundle.json",
            "SOURCE_IDENTITY.json",
        ):
            hashes[name] = file_sha256(bundle / name)
    payload = {
        "experiment_id": S3_EXPERIMENT_ID,
        "single_change": (
            "keep confirmed controls/effects/goal invariants at level "
            "transition; clear coordinates, layout, and current plan"
        ),
        "read_only_telemetry": True,
        "policy_except_level_transfer_unchanged": True,
        "seed_unchanged": True,
        "s1_not_stacked": True,
        "s2_not_stacked": True,
        "installed_at_epoch": time.time(),
        "source_sha256": (
            hashlib.sha256(source_text.encode("utf-8")).hexdigest()
            if source_text is not None
            else None
        ),
        "bundle_hashes": hashes,
        "working_dir": str(working_dir),
        "runtime_seconds": None,
        "counters": dict(_COUNTERS),
    }
    if extra:
        payload["extra"] = extra
    if target is not None:
        payload["target_max_runtime_s"] = getattr(target, "max_runtime_s", None)
    write_telemetry(Path(working_dir), payload)
    print(
        "S3 cross-level transfer installed: keep mechanics, drop layout/plan",
        flush=True,
    )
    return payload
