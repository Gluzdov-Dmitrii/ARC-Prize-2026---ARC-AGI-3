"""Unit tests for S2 reasoning+content memory capture."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.s2_memory_capture import (
    S2_FIELD_MAX_CHARS,
    extract_scientist_note,
    merge_scientist_notes,
    normalize_summary_text,
    wrap_format_model_response_meta,
    wrap_update_summarized_knowledge,
)


REASONING_ONLY = """
I am thinking about the controls.
World model: Red 2x2 cursor is the player; walls are color 4.
Goal model: Reach the green door on the right.
Action model: SPACE toggles the held object.
"""

CONTENT_ONLY = """
World model: The HUD timer sits on the top row.
Plan: Click the remaining untested cells.
"""

BOTH_SAME = """
World model: Player is the red 2x2 block.
"""

CONTENT_OVERRIDE = """
World model: Player is the blue square, not red.
Goal model: Exit through the left portal.
"""


class MemoryCaptureTests(unittest.TestCase):
    def test_reasoning_only_facts_are_captured(self):
        merged = merge_scientist_notes(REASONING_ONLY, "")
        self.assertIn("Red 2x2 cursor", merged["world_model"])
        self.assertIn("green door", merged["goal_model"])
        self.assertIn("SPACE", merged["action_model"])
        self.assertEqual(merged["current_plan"], "")

    def test_content_only_facts_are_captured(self):
        merged = merge_scientist_notes("", CONTENT_ONLY)
        self.assertIn("HUD timer", merged["world_model"])
        self.assertIn("untested cells", merged["current_plan"])

    def test_dedup_keeps_one_copy(self):
        merged = merge_scientist_notes(BOTH_SAME, BOTH_SAME)
        self.assertEqual(merged["world_model"].count("red 2x2"), 1)
        self.assertEqual(
            merged["world_model"],
            extract_scientist_note(BOTH_SAME)["world_model"],
        )

    def test_content_wins_on_conflict(self):
        merged = merge_scientist_notes(REASONING_ONLY, CONTENT_OVERRIDE)
        self.assertIn("blue square", merged["world_model"])
        self.assertNotIn("Red 2x2", merged["world_model"])
        self.assertIn("left portal", merged["goal_model"])
        self.assertIn("SPACE", merged["action_model"])

    def test_default_helper_cap_is_280_and_labeled_fields_stay_uncapped(self):
        self.assertIsNone(S2_FIELD_MAX_CHARS)
        long_fact = "X" * 400
        capped = normalize_summary_text(long_fact)
        self.assertTrue(capped.endswith("chars omitted]"))
        self.assertLessEqual(len(capped), 280 + 40)
        uncapped = normalize_summary_text(long_fact, max_chars=S2_FIELD_MAX_CHARS)
        self.assertEqual(uncapped, long_fact)
        note = extract_scientist_note(f"World model: {long_fact}")
        self.assertEqual(note["world_model"], long_fact)

    def test_update_wrapper_uses_stashed_reasoning(self):
        calls: list[tuple[str, str]] = []

        def fake_extract(text: str) -> dict[str, str]:
            calls.append(("extract", text))
            return extract_scientist_note(text)

        def original_update(self, content: str) -> None:
            raise AssertionError("original content-only updater must not run")

        wrap_format_model_response_meta(
            lambda **kwargs: "meta"
        )(finish_reason="", reasoning=REASONING_ONLY, content="", tools=None)
        wrapped = wrap_update_summarized_knowledge(
            original_update, extract_fn=fake_extract
        )
        agent = SimpleNamespace(_summarized_knowledge={})
        wrapped(agent, "")
        self.assertIn("Red 2x2 cursor", agent._summarized_knowledge["world_model"])
        self.assertTrue(any("Red 2x2" in item[1] for item in calls))


class NotebookSyncTests(unittest.TestCase):
    def test_notebook_embeds_current_s2_source_without_s1_seed_hook(self):
        source = (ROOT / "src" / "s2_memory_capture.py").read_text(encoding="utf-8")
        notebook = (
            ROOT
            / "tmp"
            / "kernels"
            / "s2-memory-capture"
            / "duck-qwen3-8-flash-next-nvfp4-mtp.ipynb"
        )
        if not notebook.is_file():
            self.skipTest("S2 notebook is not present")
        import json

        nb = json.loads(notebook.read_text(encoding="utf-8"))
        joined = "\n".join(
            "".join(cell.get("source") or [])
            if isinstance(cell.get("source"), list)
            else str(cell.get("source") or "")
            for cell in nb["cells"]
        )
        self.assertIn("S2 memory capture", joined)
        self.assertIn(source.strip(), joined)
        self.assertNotIn("install_s1_hooks", joined)
        self.assertNotIn("arc-agi-3-s1-v1", joined)
        self.assertGreaterEqual(joined.count("bm.solver.concurrency = 28"), 1)


if __name__ == "__main__":
    unittest.main()
