"""S1 deterministic control: per-game vLLM seed plus read-only telemetry.

The Duck harness defaults ``LOCAL_ANALYZER_SEED`` to ``-1``. TAAF's
``build_chat_payload`` then omits the seed field, so vLLM samples stochastically
and the same notebook can score 3.39 and 2.95.

This module is the single causal change for experiment S1:

- derive a stable non-negative seed from each ``game_id``;
- bind that seed on the game worker thread so concurrency cannot leak it;
- wrap ``build_chat_payload`` so the seed is actually sent;
- write read-only config/hash/runtime telemetry.

Prompts, temperature, top_p, serving flags, memory, and the scheduler are
untouched.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable

S1_EXPERIMENT_ID = "S1"
S1_SEED_NAMESPACE = "arc-agi-3-s1-v1"
S1_TELEMETRY_NAME = "s1_telemetry.json"
S1_PATCH_FLAG = "_arc_s1_patched"

_CTX = threading.local()
_INSTALLED = False
_ORIG_PLAY_ONE: Callable[..., Any] | None = None
_ORIG_BUILD_CHAT_PAYLOAD: Callable[..., Any] | None = None


def per_game_seed(game_id: str, *, namespace: str = S1_SEED_NAMESPACE) -> int:
    """Return a stable seed in ``[0, 2**32)`` for one game identity."""
    digest = hashlib.sha256(f"{namespace}:{game_id}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


def source_sha256() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def current_game_id() -> str | None:
    return getattr(_CTX, "game_id", None)


def current_game_seed() -> int | None:
    return getattr(_CTX, "seed", None)


def bind_game(game_id: str) -> int:
    seed = per_game_seed(str(game_id))
    _CTX.game_id = str(game_id)
    _CTX.seed = seed
    return seed


def clear_game() -> None:
    _CTX.game_id = None
    _CTX.seed = None


def game_id_from(game: Any, index: int) -> str:
    run = getattr(game, "game_run", None)
    if run is not None and getattr(run, "game_id", None):
        return str(run.game_id)
    for attr in ("env_name", "game_id", "name"):
        value = getattr(game, attr, None)
        if value:
            return str(value)
    return str(index)


def wrap_build_chat_payload(original: Callable[..., Any]) -> Callable[..., Any]:
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        seed = current_game_seed()
        if seed is not None:
            kwargs["seed"] = int(seed)
        return original(*args, **kwargs)

    setattr(wrapped, S1_PATCH_FLAG, True)
    return wrapped


def wrap_play_one(original: Callable[..., Any]) -> Callable[..., Any]:
    def wrapped(
        self: Any,
        game: Any,
        index: int,
        pass_index: int,
        local_server: Any = None,
    ) -> Any:
        bind_game(game_id_from(game, index))
        try:
            return original(self, game, index, pass_index, local_server)
        finally:
            clear_game()

    setattr(wrapped, S1_PATCH_FLAG, True)
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


def solver_config_snapshot(bm: Any, target: Any | None) -> dict[str, Any]:
    solver = getattr(bm, "solver", None)
    keys = (
        "max_runtime_s_per_game",
        "analyzer_timeout",
        "concurrency",
        "max_actions_per_game",
        "save_request_logs",
        "label",
        "model",
    )
    snapshot = {key: getattr(solver, key, None) for key in keys}
    snapshot["n_passes"] = getattr(bm, "n_passes", None)
    snapshot["target_max_runtime_s"] = getattr(target, "max_runtime_s", None)
    snapshot["local_analyzer_seed_env"] = os.environ.get("LOCAL_ANALYZER_SEED", "")
    snapshot["local_analyzer_temperature"] = os.environ.get(
        "LOCAL_ANALYZER_TEMPERATURE", ""
    )
    snapshot["local_analyzer_top_p"] = os.environ.get("LOCAL_ANALYZER_TOP_P", "")
    snapshot["local_analyzer_top_k"] = os.environ.get("LOCAL_ANALYZER_TOP_K", "")
    return snapshot


def telemetry_path(working_dir: Path) -> Path:
    return Path(working_dir) / S1_TELEMETRY_NAME


def write_telemetry(working_dir: Path, payload: dict[str, Any]) -> Path | None:
    path = telemetry_path(working_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        print(f"S1 telemetry written: {path}", flush=True)
        return path
    except Exception as exc:
        print(f"S1 telemetry write failed: {exc!r}", flush=True)
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


def build_initial_telemetry(
    *,
    bm: Any,
    target: Any | None,
    working_dir: Path,
    bundle_dir: Path | None,
    extra: dict[str, Any] | None = None,
    source_text: str | None = None,
) -> dict[str, Any]:
    bundle = Path(bundle_dir) if bundle_dir is not None else None
    hashes = {}
    if bundle is not None:
        for name in (
            "setup_commands.json",
            "teardown_commands.json",
            "serving_setup.py",
            "vllm_server_watchdog.py",
            "taaf-kaggle-bundle.json",
            "SOURCE_IDENTITY.json",
        ):
            hashes[name] = file_sha256(bundle / name)
    source_hash = (
        hashlib.sha256(source_text.encode("utf-8")).hexdigest()
        if source_text is not None
        else None
    )
    payload = {
        "experiment_id": S1_EXPERIMENT_ID,
        "single_change": "stable per-game vLLM seed plus read-only telemetry",
        "seed_namespace": S1_SEED_NAMESPACE,
        "seed_mode": "per-game-sha256-u32",
        "read_only_telemetry": True,
        "policy_unchanged": True,
        "installed_at_epoch": time.time(),
        "source_sha256": source_hash,
        "bundle_hashes": hashes,
        "solver": solver_config_snapshot(bm, target),
        "working_dir": str(working_dir),
        "bundle_dir": str(bundle) if bundle is not None else None,
        "runtime_seconds": None,
    }
    if extra:
        payload["extra"] = extra
    return payload


def install_s1_hooks(
    bm: Any,
    *,
    target: Any | None = None,
    working_dir: Path,
    bundle_dir: Path | None = None,
    extra: dict[str, Any] | None = None,
    source_text: str | None = None,
) -> dict[str, Any]:
    """Patch solver play + chat payload seed injection; write initial telemetry."""
    global _INSTALLED, _ORIG_PLAY_ONE, _ORIG_BUILD_CHAT_PAYLOAD

    from inference.framework.solver import HarnessSolver
    from inference.utils import openai_compat

    if not getattr(HarnessSolver._play_one, S1_PATCH_FLAG, False):
        _ORIG_PLAY_ONE = HarnessSolver._play_one
        HarnessSolver._play_one = wrap_play_one(HarnessSolver._play_one)  # type: ignore[method-assign]
    if not getattr(openai_compat.build_chat_payload, S1_PATCH_FLAG, False):
        _ORIG_BUILD_CHAT_PAYLOAD = openai_compat.build_chat_payload
        openai_compat.build_chat_payload = wrap_build_chat_payload(
            openai_compat.build_chat_payload
        )

    orig_run = bm.run
    if not getattr(orig_run, S1_PATCH_FLAG, False):

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

        setattr(wrapped_run, S1_PATCH_FLAG, True)
        bm.run = wrapped_run

    _INSTALLED = True
    payload = build_initial_telemetry(
        bm=bm,
        target=target,
        working_dir=Path(working_dir),
        bundle_dir=Path(bundle_dir) if bundle_dir is not None else None,
        extra=extra,
        source_text=source_text,
    )
    write_telemetry(Path(working_dir), payload)
    print(
        "S1 deterministic control installed: per-game seed "
        f"namespace={S1_SEED_NAMESPACE}",
        flush=True,
    )
    return payload
