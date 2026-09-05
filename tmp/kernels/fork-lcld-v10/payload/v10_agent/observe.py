"""Observation ingestion and normalization for ARC-AGI-3 environments."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from v10_agent.types import Grid2D


def collapse_frame_axes(grid: Any) -> Grid2D:
    """Collapse temporal/batch axes to return the active 2D integer grid.

    ARC's FrameData.frame may be a temporal list of 2D grids (depth 3) or a
    bare 2D grid (depth 2) or a numpy array. This function guarantees a
    normalized list[list[int]] representation with values clamped to 0..9.
    """
    if grid is None:
        return []

    # Handle numpy ndarray
    ndim = getattr(grid, "ndim", None)
    if ndim is not None:
        try:
            curr = grid
            while int(ndim) > 2:
                if len(curr) == 0:
                    return []
                curr = curr[-1]
                ndim = getattr(curr, "ndim", 0)
            if hasattr(curr, "tolist"):
                curr = curr.tolist()
            grid = curr
        except (TypeError, ValueError):
            pass

    if not isinstance(grid, (list, tuple)) or not grid:
        return []

    # Check temporal depth: if first element is a list of lists, take the last time frame
    first = grid[0]
    if isinstance(first, (list, tuple)) and first:
        sub = first[0]
        if isinstance(sub, (list, tuple)):
            # Depth 3: [time_step, row, col]
            grid = grid[-1]

    # Convert to pure list[list[int]]
    out: Grid2D = []
    for row in grid:
        if hasattr(row, "tolist"):
            row = row.tolist()
        if not isinstance(row, (list, tuple)):
            continue
        int_row: list[int] = []
        for cell in row:
            try:
                val = int(cell)
                # ARC colors are 0-9
                val = max(0, min(9, val))
                int_row.append(val)
            except (ValueError, TypeError):
                int_row.append(0)
        out.append(int_row)

    return out


def grid_to_hex_rows(grid: Grid2D) -> list[str]:
    """Convert each grid row to a string of single-digit color values."""
    return ["".join(str(c) for c in row) for row in grid]


def compute_grid_hash(grid: Grid2D) -> str:
    """Compute deterministic SHA-256 hash of grid contents."""
    canonical_repr = "\n".join(grid_to_hex_rows(grid))
    return hashlib.sha256(canonical_repr.encode("utf-8")).hexdigest()


def normalize_state_name(state: Any) -> str:
    """Normalize game state enum or string to canonical uppercase string."""
    if hasattr(state, "name"):
        return str(getattr(state, "name")).split(".")[-1].upper()
    value = getattr(state, "value", None)
    if value is not None:
        return str(value).split(".")[-1].upper()
    text = str(state or "").split(".")[-1].strip().upper()
    return text or "IN_PROGRESS"


def normalize_action_name(action: Any) -> str:
    """Normalize action enum or string to canonical uppercase string."""
    if hasattr(action, "name"):
        return str(getattr(action, "name")).split(".")[-1].upper()
    value = getattr(action, "value", action)
    if isinstance(value, int):
        if value == 0:
            return "RESET"
        if 1 <= value <= 7:
            return f"ACTION{value}"
    text = str(value).split(".")[-1].strip().upper()
    if text.isdigit():
        return normalize_action_name(int(text))
    return text or "ACTION1"


def normalize_observation(
    raw_obs: Mapping[str, Any],
    frame_index: int = 0,
    game_id: str = "",
) -> dict[str, Any]:
    """Normalize arbitrary environment observation into canonical dictionary."""
    obs_dict = dict(raw_obs)
    raw_grid = obs_dict.get("frame", obs_dict.get("grid"))
    grid = collapse_frame_axes(raw_grid)

    available_actions_raw = obs_dict.get("available_actions", ()) or ()
    available_actions = [normalize_action_name(a) for a in available_actions_raw]
    if not available_actions:
        # Default full action space if unspecified
        available_actions = ["RESET", "ACTION1", "ACTION2", "ACTION3", "ACTION4", "ACTION5", "ACTION6", "ACTION7"]

    state_raw = obs_dict.get("state")
    if state_raw is None:
        metadata = dict(obs_dict.get("metadata", {}) or {})
        state_raw = metadata.get("state", "IN_PROGRESS")
    state = normalize_state_name(state_raw)

    levels_completed = obs_dict.get("levels_completed")
    if levels_completed is None:
        levels_completed = obs_dict.get("score", 0)
    try:
        levels_completed = int(levels_completed or 0)
    except (ValueError, TypeError):
        levels_completed = 0

    win_levels = obs_dict.get("win_levels", obs_dict.get("win_score"))
    if win_levels is not None:
        try:
            win_levels = int(win_levels)
        except (ValueError, TypeError):
            win_levels = None

    gid = str(obs_dict.get("game_id") or game_id or "anonymous_game")
    guid = getattr(raw_obs, "guid", obs_dict.get("guid"))

    return {
        "grid": grid,
        "grid_hash": compute_grid_hash(grid),
        "available_actions": available_actions,
        "game_id": gid,
        "guid": guid,
        "state": state,
        "levels_completed": levels_completed,
        "win_levels": win_levels,
        "full_reset": bool(obs_dict.get("full_reset", False)),
        "frame_index": frame_index,
    }
