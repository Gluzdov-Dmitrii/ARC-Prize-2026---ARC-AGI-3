"""S5 animation-aware observation: labeled animation stills plus settled frame.

Duck attaches one image of the current (final) grid. TAAF already exposes
intra-action animation on ``GameState.animation_frames``, but the harness
drops those stills, so the model often plans on a mid-motion or
post-animation frame without seeing the cause.

This module is the single causal change for experiment S5 on the S4 parent:

- after each executed action, keep the in-between animation grids on the
  worker thread;
- on the next user turn, attach a compact sequence of those stills labeled
  ANIMATION (do not plan on them);
- keep the full current grid image labeled ACTIONABLE / settled;
- bound extra images and downscale animation stills so token cost stays
  limited;
- if there is no animation, fall back to Duck's single current-grid image.

S1/S2/S3/S4b/S6/S7 are not stacked. Prompts, memory, seed, and scheduler
are untouched. S4 top-HUD no-impact stays as the retained champion policy.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any, Callable

S5_EXPERIMENT_ID = "S5"
S5_TELEMETRY_NAME = "s5_telemetry.json"
S5_PATCH_FLAG = "_arc_s5_patched"
MAX_ANIMATION_IMAGES = 3
ANIMATION_UPSCALE = 8
LABEL_INTRO = (
    "Vision labels: ANIMATION images are in-between motion from the last "
    "action and are not the settled state. The last image is the ACTIONABLE "
    "FRAME (settled current_frame) to plan from."
)
ANIMATION_CAPTION = "ANIMATION {idx}/{total} (in-between motion; not the settled state):"
ACTIONABLE_CAPTION = "ACTIONABLE FRAME (settled state to plan from; same as current_frame):"

_LOCK = threading.Lock()
_CTX = threading.local()
_WORKING_DIR: Path | None = None
_INSTALLED = False
_COUNTERS = {
    "actions_observed": 0,
    "animation_sequences": 0,
    "animation_frames_raw": 0,
    "animation_frames_attached": 0,
    "actionable_images": 0,
    "duck_fallback_turns": 0,
}


def reset_counters() -> None:
    with _LOCK:
        for key in _COUNTERS:
            _COUNTERS[key] = 0


def bump(name: str, amount: int = 1) -> None:
    with _LOCK:
        _COUNTERS[name] = int(_COUNTERS.get(name, 0)) + int(amount)


def as_grid(value: Any) -> list[list[int]] | None:
    if value is None:
        return None
    data = getattr(value, "data", value)
    if isinstance(data, dict) and "grid" in data:
        data = data["grid"]
    rows = data.tolist() if hasattr(data, "tolist") else data
    try:
        grid = [[int(cell) for cell in row] for row in rows]
    except (TypeError, ValueError):
        return None
    if not grid or not grid[0]:
        return None
    width = len(grid[0])
    if any(len(row) != width for row in grid):
        return None
    return grid


def grid_key(grid: list[list[int]]) -> tuple[tuple[int, ...], ...]:
    return tuple(tuple(row) for row in grid)


def unique_consecutive(grids: list[list[list[int]]]) -> list[list[list[int]]]:
    out: list[list[list[int]]] = []
    last: tuple[tuple[int, ...], ...] | None = None
    for grid in grids:
        key = grid_key(grid)
        if key == last:
            continue
        out.append(grid)
        last = key
    return out


def compact_animation_grids(
    grids: list[list[list[int]]] | None,
    *,
    max_images: int = MAX_ANIMATION_IMAGES,
    exclude: list[list[int]] | None = None,
) -> list[list[list[int]]]:
    cleaned = unique_consecutive([g for g in (grids or []) if g])
    if exclude is not None:
        skip = grid_key(exclude)
        cleaned = [g for g in cleaned if grid_key(g) != skip]
    if max_images <= 0 or len(cleaned) <= max_images:
        return cleaned
    last_index = len(cleaned) - 1
    picks = sorted(
        {
            int(round(i * last_index / (max_images - 1)))
            for i in range(max_images)
        }
    )
    return [cleaned[idx] for idx in picks]


def bind_animation_grids(grids: list[list[list[int]]]) -> None:
    _CTX.animation_grids = [ [list(row) for row in grid] for grid in grids ]


def current_animation_grids() -> list[list[list[int]]]:
    grids = getattr(_CTX, "animation_grids", None)
    if not grids:
        return []
    return grids


def clear_animation_grids() -> None:
    _CTX.animation_grids = []


def grids_from_state(state: Any) -> list[list[list[int]]]:
    if state is None:
        return []
    frames = getattr(state, "animation_frames", None)
    if frames is None:
        return []
    out: list[list[list[int]]] = []
    try:
        items = list(frames)
    except TypeError:
        return []
    for item in items:
        grid = as_grid(item)
        if grid is not None:
            out.append(grid)
    return out


def grid_from_duck_frame(frame: Any) -> list[list[int]] | None:
    if frame is None:
        return None
    return as_grid(getattr(frame, "grid", frame))


def default_render_image_part(
    grid: list[list[int]],
    *,
    upscale: int,
    step: int = 0,
    level: int = 1,
) -> dict[str, Any] | None:
    try:
        from inference.agent.runtime_state import Frame
        from inference.agent.vision_context import frame_to_png_data_url
    except Exception:
        return None
    rows = tuple(tuple(int(cell) for cell in row) for row in grid)
    frame = Frame(grid=rows, step=step, level=level)
    try:
        url = frame_to_png_data_url(frame, upscale=upscale)
    except Exception:
        return None
    return {"type": "image_url", "image_url": {"url": url}}


def duck_current_image_part(frame: Any) -> dict[str, Any] | None:
    try:
        from inference.agent.vision_context import current_grid_image_part
    except Exception:
        return None
    try:
        return current_grid_image_part(frame)
    except Exception:
        return None


def images_enabled() -> bool:
    try:
        from inference.agent.vision_context import current_grid_image_enabled
    except Exception:
        return False
    try:
        return bool(current_grid_image_enabled())
    except Exception:
        return False


def build_labeled_user_message(
    user_prompt: str,
    current_frame: Any,
    animation_grids: list[list[list[int]]],
    *,
    render_part: Callable[..., dict[str, Any] | None] | None = None,
    max_images: int = MAX_ANIMATION_IMAGES,
    animation_upscale: int = ANIMATION_UPSCALE,
) -> dict[str, Any] | None:
    renderer = render_part or default_render_image_part
    current_grid = grid_from_duck_frame(current_frame)
    compact = compact_animation_grids(
        animation_grids,
        max_images=max_images,
        exclude=current_grid,
    )
    if not compact:
        return None
    parts: list[dict[str, Any]] = [
        {"type": "text", "text": f"{user_prompt}\n\n{LABEL_INTRO}"}
    ]
    attached = 0
    total = len(compact)
    for idx, grid in enumerate(compact, start=1):
        parts.append(
            {
                "type": "text",
                "text": ANIMATION_CAPTION.format(idx=idx, total=total),
            }
        )
        image = renderer(grid, upscale=animation_upscale)
        if image is None:
            return None
        parts.append(image)
        attached += 1
    parts.append({"type": "text", "text": ACTIONABLE_CAPTION})
    current_image = duck_current_image_part(current_frame)
    if current_image is None and current_grid is not None:
        current_image = renderer(current_grid, upscale=16)
    if current_image is None:
        return None
    parts.append(current_image)
    bump("animation_sequences")
    bump("animation_frames_attached", attached)
    bump("actionable_images")
    return {"role": "user", "content": parts}


def wrap_execute_action(original: Callable[..., Any]) -> Callable[..., Any]:
    def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
        payload = original(self, *args, **kwargs)
        state = getattr(getattr(self, "game", None), "current_state", None)
        grids = grids_from_state(state)
        bind_animation_grids(grids)
        bump("actions_observed")
        bump("animation_frames_raw", len(grids))
        if grids:
            print(
                f"S5_ANIMATION captured frames={len(grids)} compact_max={MAX_ANIMATION_IMAGES}",
                flush=True,
            )
        return payload

    setattr(wrapped, S5_PATCH_FLAG, True)
    return wrapped


def wrap_build_user_message(
    original: Callable[..., Any],
    *,
    render_part: Callable[..., dict[str, Any] | None] | None = None,
) -> Callable[..., Any]:
    def wrapped(self: Any, user_prompt: str, current_frame: Any) -> dict[str, Any]:
        if not images_enabled():
            bump("duck_fallback_turns")
            return original(self, user_prompt, current_frame)
        labeled = build_labeled_user_message(
            user_prompt,
            current_frame,
            current_animation_grids(),
            render_part=render_part,
        )
        if labeled is None:
            bump("duck_fallback_turns")
            return original(self, user_prompt, current_frame)
        return labeled

    setattr(wrapped, S5_PATCH_FLAG, True)
    return wrapped


def wrap_play_one(original: Callable[..., Any]) -> Callable[..., Any]:
    def wrapped(
        self: Any,
        game: Any,
        index: int,
        pass_index: int,
        local_server: Any = None,
    ) -> Any:
        clear_animation_grids()
        try:
            return original(self, game, index, pass_index, local_server)
        finally:
            clear_animation_grids()

    setattr(wrapped, S5_PATCH_FLAG, True)
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
        if hasattr(obj, "_execute_action") and hasattr(obj, "play"):
            return obj
    return None


def telemetry_path(working_dir: Path) -> Path:
    return Path(working_dir) / S5_TELEMETRY_NAME


def write_telemetry(working_dir: Path, payload: dict[str, Any]) -> Path | None:
    path = telemetry_path(working_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        print(f"S5 telemetry written: {path}", flush=True)
        return path
    except Exception as exc:
        print(f"S5 telemetry write failed: {exc!r}", flush=True)
        return None


def install_s5_hooks(
    bm: Any,
    *,
    target: Any | None = None,
    working_dir: Path,
    bundle_dir: Path | None = None,
    extra: dict[str, Any] | None = None,
    source_text: str | None = None,
) -> dict[str, Any]:
    global _INSTALLED, _WORKING_DIR

    from inference.agent import tool_agent as ta
    from inference.framework.solver import HarnessSolver

    _WORKING_DIR = Path(working_dir)
    reset_counters()
    clear_animation_grids()

    if not getattr(HarnessSolver._play_one, S5_PATCH_FLAG, False):
        HarnessSolver._play_one = wrap_play_one(HarnessSolver._play_one)  # type: ignore[method-assign]

    session_cls = harness_session_class()
    if session_cls is not None:
        exec_fn = getattr(session_cls, "_execute_action", None)
        if callable(exec_fn) and not getattr(exec_fn, S5_PATCH_FLAG, False):
            session_cls._execute_action = wrap_execute_action(  # type: ignore[method-assign]
                exec_fn
            )

    build_fn = getattr(ta.ToolAgent, "_build_user_message", None)
    if callable(build_fn) and not getattr(build_fn, S5_PATCH_FLAG, False):
        ta.ToolAgent._build_user_message = wrap_build_user_message(  # type: ignore[method-assign]
            build_fn
        )

    orig_run = bm.run
    if not getattr(orig_run, S5_PATCH_FLAG, False):

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

        setattr(wrapped_run, S5_PATCH_FLAG, True)
        bm.run = wrapped_run

    _INSTALLED = True
    payload = {
        "experiment_id": S5_EXPERIMENT_ID,
        "single_change": (
            "bounded labeled animation stills plus full actionable current frame"
        ),
        "max_animation_images": MAX_ANIMATION_IMAGES,
        "animation_upscale": ANIMATION_UPSCALE,
        "session_class_found": session_cls is not None,
        "s1_not_stacked": True,
        "s2_not_stacked": True,
        "s3_not_stacked": True,
        "s4b_not_stacked": True,
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
        "S5_ANIMATION_AWARE "
        f"max_images={MAX_ANIMATION_IMAGES} upscale={ANIMATION_UPSCALE} "
        "telemetry=" + str(telemetry_path(Path(working_dir))),
        flush=True,
    )
    return payload
