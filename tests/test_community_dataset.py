"""C1 public-trace dataset builder tests."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.build_community_dataset import build_dataset, classify_outer2, game_id_from_events_path, write_dataset
from src.s4_semantic_no_impact import classify_transition


def _grid(top: int, interior: int, bottom: int = 0) -> list[list[int]]:
    return [[top, top], [top, top], [interior, interior], [bottom, bottom], [bottom, bottom]]


class CommunityDatasetTests(unittest.TestCase):
    def test_bottom_strip_is_outer_hud_not_s4(self):
        before = [[1, 1], [1, 1], [9, 9], [2, 2], [2, 2]]
        after = [[1, 1], [1, 1], [9, 9], [3, 3], [3, 3]]
        self.assertEqual(classify_transition(before, after), "real_change")
        self.assertEqual(classify_outer2(before, after), "hud_only")

    def test_game_id_from_filename(self):
        self.assertEqual(
            game_id_from_events_path(Path("tn36-ef4dde99_p0_events.jsonl")),
            "tn36-ef4dde99",
        )

    def test_labels_and_no_transcript_leak(self):
        game_id = "tn36-ef4dde99"
        events = [
            {"type": "initial", "board": _grid(1, 9), "action_num": 0, "level": 1},
            {
                "type": "action",
                "board": _grid(2, 9),
                "action_num": 1,
                "level": 1,
                "action_name": "ACTION1",
                "action_display": "UP",
                "transcript": "SECRET PROMPT",
            },
            {
                "type": "action",
                "board": _grid(2, 8),
                "action_num": 2,
                "level": 2,
                "action_name": "ACTION2",
            },
            {
                "type": "action",
                "board": _grid(2, 8),
                "action_num": 3,
                "level": 2,
                "action_name": "ACTION2",
            },
        ]
        with tempfile.TemporaryDirectory() as raw:
            events_dir = Path(raw) / "events"
            events_dir.mkdir()
            path = events_dir / f"{game_id}_p0_events.jsonl"
            path.write_text(
                "\n".join(json.dumps(row) for row in events) + "\n",
                encoding="utf-8",
            )
            panels = Path(raw) / "panels.json"
            panels.write_text(
                json.dumps(
                    {
                        "development": [game_id],
                        "validation": [],
                        "held_public": [],
                    }
                ),
                encoding="utf-8",
            )
            bundle = build_dataset(events_dir, panels, source_run="s2", source_kernel_version=5)
            labels = [row["label"] for row in bundle["records"]]
            self.assertEqual(labels, ["hud_only", "interior_change", "identical"])
            self.assertEqual(
                [row["label_outer2"] for row in bundle["records"]],
                ["hud_only", "interior_change", "identical"],
            )
            self.assertTrue(bundle["records"][1]["level_changed"])
            blob = json.dumps(bundle["records"])
            self.assertNotIn("SECRET PROMPT", blob)
            self.assertNotIn("transcript", blob)
            out = Path(raw) / "out"
            write_dataset(bundle, out)
            self.assertTrue((out / "pairs.jsonl").exists())
            self.assertTrue((out / "summary.json").exists())


if __name__ == "__main__":
    unittest.main()
