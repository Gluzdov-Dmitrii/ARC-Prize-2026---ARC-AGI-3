"""S2 memory capture: read labeled world-model facts from reasoning and content.

Duck currently updates structured memory only from assistant ``content``.
Qwen3 thinking often puts ``World model:`` / ``Goal model:`` / ``Action model:``
lines in ``reasoning``, so those facts are dropped.

This module is the single causal change for experiment S2:

- extract the same labeled blocks from reasoning and from content;
- fill empty fields from reasoning; content wins on conflict;
- dedup identical normalized text; keep Duck's labeled-block length policy
  (``max_chars=None``, i.e. no extra truncation).

Prompts, seed, scheduler, temperature, and serving flags are untouched.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any, Callable

S2_EXPERIMENT_ID = "S2"
S2_TELEMETRY_NAME = "s2_telemetry.json"
S2_PATCH_FLAG = "_arc_s2_patched"
S2_FIELD_MAX_CHARS = None  # Duck labeled-block extract uses max_chars=None
KNOWLEDGE_KEYS = (
    "world_model",
    "goal_model",
    "action_model",
    "recent_findings",
    "open_questions",
    "current_plan",
    "cross_level_notes",
)
LABELS = [
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
]

_CTX = threading.local()
_INSTALLED = False


def normalize_summary_text(value: Any, *, max_chars: int | None = 280) -> str:
    text = " ".join(str(value or "").split())
    if max_chars is None or max_chars <= 0 or len(text) <= max_chars:
        return text
    omitted = len(text) - max_chars
    return f"{text[:max_chars].rstrip()}... [{omitted} chars omitted]"


def extract_labeled_blocks(content: str, labels: list[str] | None = None) -> dict[str, str]:
    labels = labels or LABELS
    normalized_labels = {label.lower(): label for label in labels}
    targets = tuple(f"{label.lower()}:" for label in labels)
    extracted: dict[str, list[str]] = {label: [] for label in labels}
    current_label: str | None = None

    for raw_line in content.splitlines():
        stripped = raw_line.strip()
        candidate = stripped
        while candidate.startswith(("-", "*")):
            candidate = candidate[1:].lstrip()
        lowered = candidate.lower()

        matched_label: str | None = None
        inline_value = ""
        for target in targets:
            if lowered.startswith(target):
                matched_label = normalized_labels[target[:-1]]
                inline_value = candidate[len(target) :].strip()
                break

        if matched_label is not None:
            current_label = matched_label
            if inline_value:
                extracted[current_label].append(inline_value)
            continue

        if current_label is not None and stripped:
            extracted[current_label].append(stripped)

    return {
        label: normalize_summary_text("\n".join(lines).strip(), max_chars=S2_FIELD_MAX_CHARS)
        for label, lines in extracted.items()
        if "\n".join(lines).strip()
    }


def extract_scientist_note(content: str) -> dict[str, str]:
    if not str(content or "").strip():
        return {key: "" for key in KNOWLEDGE_KEYS}
    extracted = extract_labeled_blocks(content)
    result = {
        "world_model": extracted.get("World model", ""),
        "goal_model": extracted.get("Goal model", ""),
        "action_model": extracted.get("Action model", ""),
        "recent_findings": extracted.get("Recent findings", ""),
        "open_questions": extracted.get("Open questions", ""),
        "current_plan": extracted.get("Plan", ""),
        "cross_level_notes": extracted.get("Cross-level notes", ""),
    }
    if not result["world_model"]:
        result["world_model"] = extracted.get("Hypothesis", "")
    if not result["recent_findings"]:
        result["recent_findings"] = extracted.get("History check", "")
    if not result["current_plan"]:
        result["current_plan"] = extracted.get("Next test", "")
    return result


def merge_scientist_notes(
    reasoning: str,
    content: str,
    *,
    extract_fn: Callable[[str], dict[str, str]] | None = None,
) -> dict[str, str]:
    """Content fills a field when present; reasoning fills gaps; identical text is kept once."""
    extract = extract_fn or extract_scientist_note
    from_reasoning = extract(reasoning or "")
    from_content = extract(content or "")
    merged: dict[str, str] = {}
    for key in KNOWLEDGE_KEYS:
        reason_value = normalize_summary_text(
            from_reasoning.get(key, ""), max_chars=S2_FIELD_MAX_CHARS
        )
        content_value = normalize_summary_text(
            from_content.get(key, ""), max_chars=S2_FIELD_MAX_CHARS
        )
        if content_value and reason_value and content_value == reason_value:
            merged[key] = content_value
        elif content_value:
            merged[key] = content_value
        elif reason_value:
            merged[key] = reason_value
        else:
            merged[key] = ""
    return merged


def wrap_format_model_response_meta(original: Callable[..., Any]) -> Callable[..., Any]:
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        reasoning = kwargs.get("reasoning")
        if reasoning is None and len(args) >= 2:
            reasoning = args[1]
        _CTX.reasoning = reasoning or ""
        return original(*args, **kwargs)

    setattr(wrapped, S2_PATCH_FLAG, True)
    return wrapped


def wrap_update_summarized_knowledge(
    original: Callable[..., Any],
    *,
    extract_fn: Callable[[str], dict[str, str]] | None = None,
) -> Callable[..., Any]:
    def wrapped(self: Any, content: str) -> None:
        reasoning = getattr(_CTX, "reasoning", "") or ""
        note = merge_scientist_notes(reasoning, content or "", extract_fn=extract_fn)
        if not any(note.values()):
            return
        for key, value in note.items():
            if value:
                self._summarized_knowledge[key] = value

    setattr(wrapped, S2_PATCH_FLAG, True)
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
    return Path(working_dir) / S2_TELEMETRY_NAME


def write_telemetry(working_dir: Path, payload: dict[str, Any]) -> Path | None:
    path = telemetry_path(working_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        print(f"S2 telemetry written: {path}", flush=True)
        return path
    except Exception as exc:
        print(f"S2 telemetry write failed: {exc!r}", flush=True)
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
    write_telemetry(working_dir, payload)
    return payload


def install_s2_hooks(
    bm: Any,
    *,
    target: Any | None = None,
    working_dir: Path,
    bundle_dir: Path | None = None,
    extra: dict[str, Any] | None = None,
    source_text: str | None = None,
) -> dict[str, Any]:
    """Patch Duck memory capture to read reasoning and content."""
    global _INSTALLED

    from inference.agent import tool_agent as ta

    extract_fn = ta._extract_scientist_note
    if not getattr(ta._format_model_response_meta, S2_PATCH_FLAG, False):
        ta._format_model_response_meta = wrap_format_model_response_meta(
            ta._format_model_response_meta
        )
    if not getattr(
        ta.ToolAgent._update_summarized_knowledge_from_assistant, S2_PATCH_FLAG, False
    ):
        ta.ToolAgent._update_summarized_knowledge_from_assistant = (  # type: ignore[method-assign]
            wrap_update_summarized_knowledge(
                ta.ToolAgent._update_summarized_knowledge_from_assistant,
                extract_fn=extract_fn,
            )
        )

    orig_run = bm.run
    if not getattr(orig_run, S2_PATCH_FLAG, False):

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

        setattr(wrapped_run, S2_PATCH_FLAG, True)
        bm.run = wrapped_run

    _INSTALLED = True
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
        "experiment_id": S2_EXPERIMENT_ID,
        "single_change": "structured memory from reasoning and content",
        "read_only_telemetry": True,
        "policy_except_memory_capture_unchanged": True,
        "seed_unchanged": True,
        "field_max_chars": S2_FIELD_MAX_CHARS,
        "installed_at_epoch": time.time(),
        "source_sha256": (
            hashlib.sha256(source_text.encode("utf-8")).hexdigest()
            if source_text is not None
            else None
        ),
        "bundle_hashes": hashes,
        "working_dir": str(working_dir),
        "runtime_seconds": None,
    }
    if extra:
        payload["extra"] = extra
    if target is not None:
        payload["target_max_runtime_s"] = getattr(target, "max_runtime_s", None)
    write_telemetry(Path(working_dir), payload)
    print(
        "S2 memory capture installed: extract labeled facts from reasoning and content",
        flush=True,
    )
    return payload
