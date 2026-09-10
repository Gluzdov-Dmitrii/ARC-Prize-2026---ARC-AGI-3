"""S6 scheduled simplification: compact dropped transcript, keep 8 assistant turns.

Duck persists about 30 assistant turns after token eviction. Long traces then
re-plan from stale tool dumps instead of the structured world model.

This module is the single causal change for experiment S6 on the S4 parent:

- keep the last 8 assistant turns in the persistent chat history;
- when older turns are dropped, fold labeled facts into verified world/goal/action
  memory, disproved hypotheses, open questions, and the current plan;
- do not overwrite newer memory with older dropped text;
- preserve S4 no-impact notes.

S1/S2/S3/S4b are not stacked. Prompts, seed, scheduler, temperature, and serving
flags are untouched. S4 top-HUD no-impact stays as the retained champion policy.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable

S6_EXPERIMENT_ID = "S6"
S6_TELEMETRY_NAME = "s6_telemetry.json"
S6_PATCH_FLAG = "_arc_s6_patched"
KEEP_ASSISTANT_TURNS = 8
FIELD_MAX_CHARS = 800
NO_IMPACT_MARKER = "No-impact memory:"
KNOWLEDGE_KEYS = (
    "world_model",
    "goal_model",
    "action_model",
    "recent_findings",
    "open_questions",
    "current_plan",
    "cross_level_notes",
)
LABELS = (
    "World model",
    "Goal model",
    "Action model",
    "Recent findings",
    "Open questions",
    "Plan",
    "Cross-level notes",
    "Hypothesis",
    "History check",
    "Next test",
)
LABEL_TO_FIELD = {
    "World model": "world_model",
    "Goal model": "goal_model",
    "Action model": "action_model",
    "Recent findings": "recent_findings",
    "Open questions": "open_questions",
    "Plan": "current_plan",
    "Cross-level notes": "cross_level_notes",
    "History check": "recent_findings",
    "Next test": "current_plan",
}

DISPROVED_RE = re.compile(
    r"\b(?:disproved|falsified|does not work|do not work|no-?ops?|no-impact|"
    r"never changes|incorrect|false hypothesis|ruled out|not the case)\b",
    re.IGNORECASE,
)
QUESTION_RE = re.compile(
    r"\?$|^\s*(?:what|why|how|does|is it|unknown|unclear|open question)\b",
    re.IGNORECASE,
)

_LOCK = threading.Lock()
_COUNTERS = {
    "compactions": 0,
    "dropped_messages": 0,
    "dropped_assistant_turns": 0,
    "facts_merged": 0,
    "history_trim_calls": 0,
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
        for part in re.split(r"(?<=[.!;?])\s+", line):
            fact = " ".join(part.split())
            if fact:
                facts.append(fact)
    return facts


def join_facts(facts: list[str], *, max_chars: int = FIELD_MAX_CHARS) -> str:
    kept: list[str] = []
    size = 0
    for item in facts:
        blob = " ".join(str(item or "").split())
        if not blob:
            continue
        extra = len(blob) + (1 if kept else 0)
        if max_chars > 0 and size + extra > max_chars:
            break
        kept.append(blob)
        size += extra
    return " ".join(kept)


def unique_append(existing: list[str], incoming: list[str]) -> list[str]:
    seen = {item.lower() for item in existing}
    out = list(existing)
    for item in incoming:
        blob = " ".join(str(item or "").split())
        if not blob:
            continue
        key = blob.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(blob)
    return out


def message_text(message: dict[str, Any] | None) -> str:
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                text = part.get("text")
                if text:
                    parts.append(str(text))
        return "\n".join(parts)
    return ""


def message_role(message: dict[str, Any] | None) -> str:
    if not isinstance(message, dict):
        return ""
    return str(message.get("role") or "").strip().lower()


def count_assistant_turns(messages: list[dict[str, Any]]) -> int:
    return sum(1 for message in messages if message_role(message) == "assistant")


def keep_recent_assistant_turns(
    messages: list[dict[str, Any]],
    max_turns: int = KEEP_ASSISTANT_TURNS,
) -> list[dict[str, Any]]:
    """Match Duck ToolAgent._keep_recent_history_turns."""
    if max_turns <= 0 or not messages:
        return []
    kept_reversed: list[dict[str, Any]] = []
    assistant_turns = 0
    for message in reversed(messages):
        kept_reversed.append(message)
        if message_role(message) == "assistant":
            assistant_turns += 1
            if assistant_turns >= max_turns:
                break
    kept = list(reversed(kept_reversed))
    while kept and message_role(kept[0]) == "tool":
        kept.pop(0)
    return kept


def history_without_system(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if messages and message_role(messages[0]) == "system":
        return list(messages[1:])
    return list(messages)


def dropped_prefix(
    messages: list[dict[str, Any]],
    *,
    max_turns: int = KEEP_ASSISTANT_TURNS,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    history = history_without_system(messages)
    kept = keep_recent_assistant_turns(history, max_turns)
    drop_n = max(0, len(history) - len(kept))
    return history[:drop_n], kept


def extract_labeled_blocks(content: str) -> dict[str, str]:
    labels = {label.lower(): label for label in LABELS}
    targets = tuple(f"{label.lower()}:" for label in LABELS)
    buckets: dict[str, list[str]] = {label: [] for label in LABELS}
    current: str | None = None
    for raw_line in str(content or "").splitlines():
        stripped = raw_line.strip()
        candidate = stripped
        while candidate.startswith(("-", "*")):
            candidate = candidate[1:].lstrip()
        lowered = candidate.lower()
        matched: str | None = None
        inline = ""
        for target in targets:
            if lowered.startswith(target):
                matched = labels[target[:-1]]
                inline = candidate[len(target) :].strip()
                break
        if matched is not None:
            current = matched
            if inline:
                buckets[current].append(inline)
            continue
        if current is not None and stripped:
            buckets[current].append(stripped)
    return {
        label: " ".join(split_facts("\n".join(lines)))
        for label, lines in buckets.items()
        if any(item.strip() for item in lines)
    }


def _is_disproved(text: str) -> bool:
    return bool(DISPROVED_RE.search(text or ""))


def _is_question(text: str) -> bool:
    return bool(QUESTION_RE.search(text or ""))


def facts_from_dropped_messages(dropped: list[dict[str, Any]]) -> dict[str, list[str]]:
    buckets: dict[str, list[str]] = {key: [] for key in KNOWLEDGE_KEYS}
    buckets["disproved"] = []
    for message in dropped:
        if message_role(message) != "assistant":
            continue
        text = message_text(message)
        if not text.strip():
            continue
        labeled = extract_labeled_blocks(text)
        hypothesis = labeled.pop("Hypothesis", "")
        for label, value in labeled.items():
            field = LABEL_TO_FIELD.get(label)
            if not field or not value:
                continue
            if field == "current_plan":
                buckets[field] = split_facts(value)
            elif field == "recent_findings" and _is_disproved(value):
                buckets["disproved"].extend(
                    item if item.lower().startswith("disproved:") else f"Disproved: {item}"
                    for item in split_facts(value)
                )
            else:
                buckets[field].extend(split_facts(value))
        if hypothesis:
            for item in split_facts(hypothesis):
                if _is_disproved(item):
                    tagged = item if item.lower().startswith("disproved:") else f"Disproved: {item}"
                    buckets["disproved"].append(tagged)
                else:
                    buckets["open_questions"].append(
                        item if item.lower().startswith("hypothesis:") else f"Hypothesis: {item}"
                    )
        unlabeled = text
        for label in LABELS:
            unlabeled = re.sub(
                rf"(?im)^\s*{re.escape(label)}\s*:.*$",
                "",
                unlabeled,
            )
        for item in split_facts(unlabeled):
            if _is_disproved(item):
                tagged = item if item.lower().startswith("disproved:") else f"Disproved: {item}"
                buckets["disproved"].append(tagged)
            elif _is_question(item):
                buckets["open_questions"].append(item)
    return buckets


def _split_no_impact(text: str) -> tuple[list[str], list[str]]:
    notes: list[str] = []
    rest: list[str] = []
    for item in split_facts(text):
        if NO_IMPACT_MARKER in item:
            notes.append(item)
        else:
            rest.append(item)
    return notes, rest


def merge_dropped_into_knowledge(
    knowledge: dict[str, str],
    dropped: list[dict[str, Any]],
) -> dict[str, int]:
    incoming = facts_from_dropped_messages(dropped)
    merged = 0
    for key in KNOWLEDGE_KEYS:
        if key not in knowledge:
            knowledge[key] = ""
    for key in ("world_model", "goal_model", "action_model", "open_questions", "cross_level_notes"):
        before = split_facts(str(knowledge.get(key) or ""))
        after = unique_append(before, incoming.get(key) or [])
        merged += max(0, len(after) - len(before))
        knowledge[key] = join_facts(after)
    notes, findings = _split_no_impact(str(knowledge.get("recent_findings") or ""))
    findings = unique_append(findings, incoming.get("recent_findings") or [])
    findings = unique_append(findings, incoming.get("disproved") or [])
    merged += len(incoming.get("recent_findings") or []) + len(incoming.get("disproved") or [])
    knowledge["recent_findings"] = join_facts(notes + findings)
    if not str(knowledge.get("current_plan") or "").strip():
        plan = incoming.get("current_plan") or []
        if plan:
            knowledge["current_plan"] = plan[-1]
            merged += 1
    return {
        "dropped_messages": len(dropped),
        "dropped_assistant_turns": count_assistant_turns(dropped),
        "facts_merged": merged,
    }


def simplify_knowledge(knowledge: dict[str, str]) -> None:
    notes, findings = _split_no_impact(str(knowledge.get("recent_findings") or ""))
    knowledge["recent_findings"] = join_facts(unique_append(notes, findings))
    for key in ("world_model", "goal_model", "action_model", "open_questions", "cross_level_notes"):
        knowledge[key] = join_facts(unique_append([], split_facts(str(knowledge.get(key) or ""))))
    plan_facts = split_facts(str(knowledge.get("current_plan") or ""))
    knowledge["current_plan"] = plan_facts[-1] if plan_facts else ""


def compact_transcript(
    knowledge: dict[str, str],
    messages: list[dict[str, Any]],
    *,
    max_turns: int = KEEP_ASSISTANT_TURNS,
) -> dict[str, Any]:
    dropped, kept = dropped_prefix(messages, max_turns=max_turns)
    stats = {
        "dropped_messages": 0,
        "dropped_assistant_turns": 0,
        "facts_merged": 0,
        "kept_messages": len(kept),
        "kept_assistant_turns": count_assistant_turns(kept),
        "compacted": False,
    }
    if not dropped:
        simplify_knowledge(knowledge)
        return stats
    merge_stats = merge_dropped_into_knowledge(knowledge, dropped)
    simplify_knowledge(knowledge)
    stats.update(merge_stats)
    stats["compacted"] = True
    return stats


def wrap_keep_recent_history_turns(original: Callable[..., Any]) -> Callable[..., Any]:
    def wrapped(self: Any, messages: list[dict[str, Any]], *, max_turns: int) -> list[dict[str, Any]]:
        cap = KEEP_ASSISTANT_TURNS
        if max_turns > 0:
            cap = min(int(max_turns), KEEP_ASSISTANT_TURNS)
        with _LOCK:
            _COUNTERS["history_trim_calls"] += 1
        return original(self, messages, max_turns=cap)

    setattr(wrapped, S6_PATCH_FLAG, True)
    return wrapped


def wrap_persistent_history_messages(original: Callable[..., Any]) -> Callable[..., Any]:
    def wrapped(
        self: Any,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> Any:
        knowledge = getattr(self, "_summarized_knowledge", None)
        if not isinstance(knowledge, dict):
            self._summarized_knowledge = {key: "" for key in KNOWLEDGE_KEYS}
            knowledge = self._summarized_knowledge
        stats = compact_transcript(knowledge, messages, max_turns=KEEP_ASSISTANT_TURNS)
        if stats["compacted"]:
            with _LOCK:
                _COUNTERS["compactions"] += 1
                _COUNTERS["dropped_messages"] += stats["dropped_messages"]
                _COUNTERS["dropped_assistant_turns"] += stats["dropped_assistant_turns"]
                _COUNTERS["facts_merged"] += stats["facts_merged"]
            print(
                "S6_SIMPLIFY "
                f"dropped={stats['dropped_messages']} "
                f"assistant={stats['dropped_assistant_turns']} "
                f"merged={stats['facts_merged']} "
                f"keep={KEEP_ASSISTANT_TURNS}",
                flush=True,
            )
        return original(self, messages, tools=tools)

    setattr(wrapped, S6_PATCH_FLAG, True)
    return wrapped


def wrap_update_summarized_knowledge(original: Callable[..., Any]) -> Callable[..., Any]:
    """Fallback when Duck has chat history but no persistent-history helper."""

    def wrapped(self: Any, content: str) -> Any:
        result = original(self, content)
        history = getattr(self, "_history_messages", None)
        knowledge = getattr(self, "_summarized_knowledge", None)
        if not isinstance(history, list) or not isinstance(knowledge, dict):
            return result
        dropped, kept = dropped_prefix(history, max_turns=KEEP_ASSISTANT_TURNS)
        if not dropped:
            return result
        stats = merge_dropped_into_knowledge(knowledge, dropped)
        simplify_knowledge(knowledge)
        self._history_messages = kept
        with _LOCK:
            _COUNTERS["compactions"] += 1
            _COUNTERS["dropped_messages"] += stats["dropped_messages"]
            _COUNTERS["dropped_assistant_turns"] += stats["dropped_assistant_turns"]
            _COUNTERS["facts_merged"] += stats["facts_merged"]
            _COUNTERS["history_trim_calls"] += 1
        print(
            "S6_SIMPLIFY_FALLBACK "
            f"dropped={stats['dropped_messages']} keep={KEEP_ASSISTANT_TURNS}",
            flush=True,
        )
        return result

    setattr(wrapped, S6_PATCH_FLAG, True)
    return wrapped


def telemetry_path(working_dir: Path) -> Path:
    return Path(working_dir) / S6_TELEMETRY_NAME


def write_telemetry(working_dir: Path, payload: dict[str, Any]) -> Path | None:
    path = telemetry_path(working_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        print(f"S6 telemetry written: {path}", flush=True)
        return path
    except Exception as exc:
        print(f"S6 telemetry write failed: {exc!r}", flush=True)
        return None


def reset_counters() -> None:
    with _LOCK:
        for key in _COUNTERS:
            _COUNTERS[key] = 0


def install_s6_hooks(
    bm: Any,
    *,
    target: Any | None = None,
    working_dir: Path,
    bundle_dir: Path | None = None,
    extra: dict[str, Any] | None = None,
    source_text: str | None = None,
) -> dict[str, Any]:
    global _INSTALLED
    from inference.agent import tool_agent as ta

    if hasattr(ta, "_PERSISTENT_HISTORY_ASSISTANT_TURNS"):
        ta._PERSISTENT_HISTORY_ASSISTANT_TURNS = KEEP_ASSISTANT_TURNS

    keep_fn = getattr(ta.ToolAgent, "_keep_recent_history_turns", None)
    if callable(keep_fn) and not getattr(keep_fn, S6_PATCH_FLAG, False):
        ta.ToolAgent._keep_recent_history_turns = wrap_keep_recent_history_turns(  # type: ignore[method-assign]
            keep_fn
        )

    persist_fn = getattr(ta.ToolAgent, "_persistent_history_messages", None)
    if callable(persist_fn) and not getattr(persist_fn, S6_PATCH_FLAG, False):
        ta.ToolAgent._persistent_history_messages = wrap_persistent_history_messages(  # type: ignore[method-assign]
            persist_fn
        )
    else:
        update_fn = getattr(ta.ToolAgent, "_update_summarized_knowledge_from_assistant", None)
        if callable(update_fn) and not getattr(update_fn, S6_PATCH_FLAG, False):
            ta.ToolAgent._update_summarized_knowledge_from_assistant = (  # type: ignore[method-assign]
                wrap_update_summarized_knowledge(update_fn)
            )

    orig_run = bm.run
    if not getattr(orig_run, S6_PATCH_FLAG, False):

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

        setattr(wrapped_run, S6_PATCH_FLAG, True)
        bm.run = wrapped_run

    _INSTALLED = True
    reset_counters()
    payload = {
        "experiment_id": S6_EXPERIMENT_ID,
        "single_change": (
            "periodic structured transcript compaction and 8-turn recent history"
        ),
        "keep_assistant_turns": KEEP_ASSISTANT_TURNS,
        "duck_default_assistant_turns": 30,
        "field_max_chars": FIELD_MAX_CHARS,
        "s1_not_stacked": True,
        "s2_not_stacked": True,
        "s3_not_stacked": True,
        "s4b_not_stacked": True,
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
        f"S6 scheduled simplification installed: keep {KEEP_ASSISTANT_TURNS} assistant turns",
        flush=True,
    )
    return payload
