"""Build C1 labeled public-trace dataset from Duck/Flash events.jsonl.

Does not include transcripts, hidden games, or credentials. Default records
store hashes and actions, not full grids.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.s4_semantic_no_impact import (
    HUD_TOP_ROWS,
    action_key,
    classify_transition,
    parse_grid,
    semantic_key,
)

SCHEMA_NAME = "arc-agi-3-public-trace-labels-v1"
LABEL_MAP = {"identical": "identical", "hud_only": "hud_only", "real_change": "interior_change"}
EXPECTED_S2_FRAMES = 5599
EXPECTED_S2_IDENTICAL = 1808
EXPECTED_S2_HUD_TOP2 = 226
EXPECTED_S2_HUD_OUTER2 = 487
EXPECTED_S2_INTERIOR_TOP2 = 3540
EXPECTED_S2_INTERIOR_OUTER2 = 3279
OUTER_BOTTOM_ROWS = 2


def load_panels(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    mapping: dict[str, str] = {}
    for split in ("development", "validation", "held_public"):
        for game_id in data[split]:
            mapping[game_id] = split
    return mapping


def game_id_from_events_path(path: Path) -> str:
    name = path.name
    for suffix in ("_p0_events.jsonl", "_events.jsonl"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return path.stem


def iter_board_events(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            event = json.loads(line)
            if parse_grid(event.get("board")) is None:
                continue
            yield event


def classify_outer2(before: list, after: list, *, top_rows: int = HUD_TOP_ROWS, bottom_rows: int = OUTER_BOTTOM_ROWS) -> str:
    if before == after:
        return "identical"
    if len(before) <= top_rows + bottom_rows or len(after) <= top_rows + bottom_rows:
        return "interior_change" if before != after else "identical"
    interior_b = before[top_rows : len(before) - bottom_rows]
    interior_a = after[top_rows : len(after) - bottom_rows]
    if interior_b == interior_a:
        return "hud_only"
    return "interior_change"


def pair_records(
    game_id: str,
    split: str,
    events: Iterable[dict[str, Any]],
    *,
    source_run: str,
    source_kernel_version: int,
    include_grids: bool = False,
) -> tuple[list[dict[str, Any]], int]:
    records: list[dict[str, Any]] = []
    prev: dict[str, Any] | None = None
    frames = 0
    for event in events:
        frames += 1
        if prev is None:
            prev = event
            continue
        before = parse_grid(prev.get("board"))
        after = parse_grid(event.get("board"))
        if before is None or after is None:
            prev = event
            continue
        kind = classify_transition(before, after)
        label = LABEL_MAP[kind]
        label_outer2 = classify_outer2(before, after)
        action = action_key(
            {
                "action": event.get("action_name") or event.get("action_display") or prev.get("action_name"),
                "action_display": event.get("action_display"),
            }
        )
        prev_level = prev.get("level")
        level = event.get("level")
        record: dict[str, Any] = {
            "game_id": game_id,
            "split": split,
            "step": int(event.get("action_num") or frames - 1),
            "event_type": event.get("type"),
            "action": action,
            "label": label,
            "label_outer2": label_outer2,
            "before_sha256": semantic_key(before),
            "after_sha256": semantic_key(after),
            "level_id": None if level is None else str(level),
            "level_changed": prev_level != level,
            "source_run": source_run,
            "source_kernel_version": source_kernel_version,
            "hud_top_rows": HUD_TOP_ROWS,
        }
        if include_grids:
            record["before_interior"] = before[HUD_TOP_ROWS:] if len(before) > HUD_TOP_ROWS else before
            record["after_interior"] = after[HUD_TOP_ROWS:] if len(after) > HUD_TOP_ROWS else after
        records.append(record)
        prev = event
    return records, frames


def build_dataset(
    events_dir: Path,
    panels_path: Path,
    *,
    source_run: str = "s2",
    source_kernel_version: int = 5,
    include_grids: bool = False,
) -> dict[str, Any]:
    splits = load_panels(panels_path)
    files = sorted(events_dir.glob("*_events.jsonl"))
    records: list[dict[str, Any]] = []
    frames = 0
    missing: list[str] = []
    for path in files:
        game_id = game_id_from_events_path(path)
        split = splits.get(game_id)
        if split is None:
            missing.append(game_id)
            continue
        game_records, game_frames = pair_records(
            game_id,
            split,
            iter_board_events(path),
            source_run=source_run,
            source_kernel_version=source_kernel_version,
            include_grids=include_grids,
        )
        records.extend(game_records)
        frames += game_frames
    labels = Counter(row["label"] for row in records)
    labels_outer2 = Counter(row["label_outer2"] for row in records)
    return {
        "schema": SCHEMA_NAME,
        "source_run": source_run,
        "source_kernel_version": source_kernel_version,
        "files": len(files),
        "unknown_game_ids": missing,
        "frames": frames,
        "pairs": len(records),
        "labels": dict(labels),
        "labels_outer2": dict(labels_outer2),
        "records": records,
    }


def write_dataset(bundle: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    records = bundle["records"]
    jsonl_path = out_dir / "pairs.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for row in records:
            handle.write(json.dumps(row, ensure_ascii=True, separators=(",", ":")) + "\n")
    summary = {k: v for k, v in bundle.items() if k != "records"}
    summary["pairs_path"] = str(jsonl_path.name)
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    (out_dir / "README.md").write_text(
        "\n".join(
            [
                f"# {SCHEMA_NAME}",
                "",
                "Labeled consecutive public-25 frame pairs from our Duck/Flash traces.",
                "No transcripts, no hidden games, no credentials.",
                "",
                f"- frames: {bundle['frames']}",
                f"- pairs: {bundle['pairs']}",
                f"- labels (S4 top-2 HUD): {json.dumps(bundle['labels'], sort_keys=True)}",
                f"- labels_outer2 (top+bottom 2 rows): {json.dumps(bundle.get('labels_outer2', {}), sort_keys=True)}",
                "",
                "Rebuild: `python -m src.build_community_dataset --events-dir <dir> --out-dir <dir>`.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build C1 public-trace label dataset")
    parser.add_argument(
        "--events-dir",
        type=Path,
        default=Path("tmp/kernels/s2-output/artifacts"),
    )
    parser.add_argument("--panels", type=Path, default=Path("src/eval_panels.json"))
    parser.add_argument("--out-dir", type=Path, default=Path("tmp/community-dataset-v1"))
    parser.add_argument("--source-run", default="s2")
    parser.add_argument("--source-kernel-version", type=int, default=5)
    parser.add_argument("--include-grids", action="store_true")
    parser.add_argument("--expect-s2-counts", action="store_true")
    args = parser.parse_args(argv)

    bundle = build_dataset(
        args.events_dir,
        args.panels,
        source_run=args.source_run,
        source_kernel_version=args.source_kernel_version,
        include_grids=args.include_grids,
    )
    write_dataset(bundle, args.out_dir)
    print(json.dumps({k: v for k, v in bundle.items() if k != "records"}, indent=2))
    if args.expect_s2_counts:
        labels = bundle["labels"]
        outer = bundle["labels_outer2"]
        errors = []
        if bundle["frames"] != EXPECTED_S2_FRAMES:
            errors.append(f"frames {bundle['frames']} != {EXPECTED_S2_FRAMES}")
        if labels.get("identical") != EXPECTED_S2_IDENTICAL:
            errors.append(f"identical {labels.get('identical')} != {EXPECTED_S2_IDENTICAL}")
        if labels.get("hud_only") != EXPECTED_S2_HUD_TOP2:
            errors.append(f"hud_only top2 {labels.get('hud_only')} != {EXPECTED_S2_HUD_TOP2}")
        if labels.get("interior_change") != EXPECTED_S2_INTERIOR_TOP2:
            errors.append(f"interior top2 {labels.get('interior_change')} != {EXPECTED_S2_INTERIOR_TOP2}")
        if outer.get("hud_only") != EXPECTED_S2_HUD_OUTER2:
            errors.append(f"hud_only outer2 {outer.get('hud_only')} != {EXPECTED_S2_HUD_OUTER2}")
        if outer.get("interior_change") != EXPECTED_S2_INTERIOR_OUTER2:
            errors.append(f"interior outer2 {outer.get('interior_change')} != {EXPECTED_S2_INTERIOR_OUTER2}")
        if errors:
            raise SystemExit("; ".join(errors))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
