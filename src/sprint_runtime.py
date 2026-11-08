"""Small, portable runtime contract for the readable ARC3 S10 notebook.

The competition branch always wins over user-facing offline settings. Nothing
here chooses game actions, game order, model sampling, or hidden game IDs.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

PROFILES = ("s10_scoped", "s4_baseline")
OFFLINE_MODES = ("smoke", "panel", "public25")
PRODUCTION = {
    "max_runtime_s_per_game": 7920.0,
    "analyzer_timeout": 900.0,
    "concurrency": 28,
    "max_actions_per_game": None,
}
SMOKE = {
    "max_runtime_s_per_game": 180.0,
    "analyzer_timeout": 120.0,
    "concurrency": 2,
    "max_actions_per_game": 4,
}


def resolve_run_config(*, true_submission: bool, profile: str,
                       offline_mode: str = "smoke", panel: str = "validation",
                       eval_seed: int = -1, panel_seconds: float = 600.0,
                       panel_actions: int = 80, panel_concurrency: int = 4) -> dict:
    if profile not in PROFILES:
        raise ValueError(f"Unknown profile {profile!r}; choose {PROFILES}")
    if true_submission:
        # Offline selection, seeds and tiny smoke caps cannot affect Phase B.
        return {"profile": profile, "mode": "competition", "panel": None,
                "seed": -1, "budgets": dict(PRODUCTION)}
    if offline_mode not in OFFLINE_MODES:
        raise ValueError(f"Unknown offline mode {offline_mode!r}")
    if not isinstance(eval_seed, int) or eval_seed < -1:
        raise ValueError("eval_seed must be -1 (stochastic) or a non-negative int")
    if panel not in {"development", "validation", "held_public"}:
        raise ValueError("Unknown evaluation panel")
    budgets = dict(PRODUCTION if offline_mode == "public25" else SMOKE)
    if offline_mode == "panel":
        if not 30 <= panel_seconds <= 7920 or not 1 <= panel_actions <= 10000:
            raise ValueError("Invalid panel runtime/action cap")
        if not 1 <= panel_concurrency <= 28:
            raise ValueError("panel_concurrency must be between 1 and 28")
        budgets = {"max_runtime_s_per_game": float(panel_seconds),
                   "analyzer_timeout": min(900.0, float(panel_seconds)),
                   "concurrency": int(panel_concurrency),
                   "max_actions_per_game": int(panel_actions)}
    return {"profile": profile, "mode": offline_mode,
            "panel": panel if offline_mode == "panel" else None,
            "seed": eval_seed, "budgets": budgets}


def apply_run_config(bm: Any, target: Any, config: dict) -> None:
    if float(getattr(target, "max_runtime_s", 0) or 0) != 32400.0:
        raise RuntimeError("Source bundle must declare the verified 9-hour budget")
    for key, value in config["budgets"].items():
        if not hasattr(bm.solver, key):
            raise RuntimeError(f"Solver contract changed: missing {key}")
        setattr(bm.solver, key, value)
    bm.solver.save_request_logs = False
    bm.n_passes = 1
    bm.game_weights = None


def select_offline_ids(public_ids: list[str], panels: dict, config: dict) -> list[str]:
    if config["mode"] == "competition":
        raise RuntimeError("Competition must enumerate the live gateway, never public IDs")
    if len(public_ids) != 25 or len(set(public_ids)) != 25:
        raise RuntimeError("Expected 25 distinct pinned public games")
    split = [g for name in ("development", "validation", "held_public") for g in panels[name]]
    if len(split) != 25 or set(split) != set(public_ids):
        raise RuntimeError("Evaluation panels must partition all public games")
    if config["mode"] == "smoke":
        return public_ids[:2]
    if config["mode"] == "panel":
        return list(panels[config["panel"]])
    return list(public_ids)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_fingerprints(paths: dict[str, Path]) -> dict[str, str]:
    """Hash the small executable inputs; never scan model weights or hidden files."""
    return {label: file_sha256(path) for label, path in sorted(paths.items())}


def write_manifest(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
                    encoding="utf-8")
