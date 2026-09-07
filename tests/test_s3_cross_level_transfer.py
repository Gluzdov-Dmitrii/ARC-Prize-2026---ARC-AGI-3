"""Unit tests for S3 cross-level transfer: keep mechanics, drop layout."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.s3_cross_level_transfer import (
    apply_cross_level_transfer,
    filter_transferable_text,
    is_layout_specific,
    is_transferable_fact,
    reset_counters,
    wrap_update_from_step_summary,
)


class FactFilterTests(unittest.TestCase):
    def test_controls_and_effects_are_kept(self):
        self.assertTrue(is_transferable_fact("SPACE toggles the held object."))
        self.assertTrue(is_transferable_fact("ACTION1 moves the player one step."))
        text = filter_transferable_text(
            "SPACE toggles the held object. ACTION1 moves the player one step."
        )["text"]
        self.assertIn("SPACE", text)
        self.assertIn("ACTION1", text)

    def test_goal_invariants_are_kept(self):
        self.assertTrue(is_transferable_fact("Collect all keys to exit."))
        self.assertTrue(is_transferable_fact("Goal: match the displayed pattern."))
        self.assertIn("exit", filter_transferable_text("Collect all keys to exit.")["text"])

    def test_coordinates_are_dropped(self):
        self.assertTrue(is_layout_specific("Player starts at (4, 7)."))
        self.assertTrue(is_layout_specific("The door is at row 2 col 9."))
        self.assertFalse(is_transferable_fact("Player starts at (4, 7)."))
        self.assertEqual(filter_transferable_text("The door is at row 2 col 9.")["text"], "")

    def test_layout_sentences_are_dropped(self):
        self.assertTrue(is_layout_specific("This level's maze walls form a spiral."))
        self.assertFalse(
            is_transferable_fact("The layout has a corridor along the top row.")
        )

    def test_mixed_paragraph_keeps_mechanics_only(self):
        blob = (
            "SPACE toggles the crate. The crate sits at (3, 4). "
            "Collect all keys to exit."
        )
        filtered = filter_transferable_text(blob)
        self.assertIn("SPACE toggles the crate.", filtered["text"])
        self.assertIn("Collect all keys to exit.", filtered["text"])
        self.assertNotIn("(3, 4)", filtered["text"])
        self.assertEqual(len(filtered["kept"]), 2)


class LevelTransitionTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_counters()

    def test_keeps_mechanics_clears_plan_and_layout(self):
        knowledge = {
            "world_model": "SPACE toggles the held object. Player starts at (4, 7).",
            "goal_model": "Collect all keys to exit. The exit door is at row 1 col 12.",
            "action_model": "ACTION1 moves the player. Click remaining cells on the top row.",
            "recent_findings": "The timer ticked after a no-op.",
            "open_questions": "What does the blue tile at (2, 2) do?",
            "current_plan": "Sweep left-to-right from cell 0,0.",
            "cross_level_notes": "Same mechanic family as previous levels.",
        }
        stats = apply_cross_level_transfer(knowledge)
        self.assertIn("SPACE toggles the held object.", knowledge["world_model"])
        self.assertNotIn("(4, 7)", knowledge["world_model"])
        self.assertIn("Collect all keys to exit.", knowledge["goal_model"])
        self.assertNotIn("row 1", knowledge["goal_model"])
        self.assertIn("ACTION1 moves the player.", knowledge["action_model"])
        self.assertNotIn("top row", knowledge["action_model"])
        self.assertEqual(knowledge["recent_findings"], "")
        self.assertEqual(knowledge["open_questions"], "")
        self.assertEqual(knowledge["current_plan"], "")
        self.assertEqual(
            knowledge["cross_level_notes"],
            "Same mechanic family as previous levels.",
        )
        self.assertTrue(stats["plan_cleared"])
        self.assertGreaterEqual(stats["kept_count"], 3)
        self.assertGreaterEqual(stats["dropped_count"], 3)

    def test_wrapper_filters_on_level_transition_not_original_wipe(self):
        wiped = {"called": False}

        def original(self) -> None:
            wiped["called"] = True
            for key in (
                "world_model",
                "goal_model",
                "action_model",
                "recent_findings",
                "open_questions",
                "current_plan",
            ):
                self._summarized_knowledge[key] = ""

        wrapped = wrap_update_from_step_summary(original)
        agent = SimpleNamespace(
            _last_step_summary={"level_transition": True, "level": 2},
            _summarized_knowledge={
                "world_model": "ACTION6 RESET returns to the spawn without changing the rule.",
                "goal_model": "Reach the exit.",
                "action_model": "SPACE toggles the held object.",
                "recent_findings": "Saw a timer-only flash.",
                "open_questions": "Is color 4 always a wall?",
                "current_plan": "Click (5, 5) next.",
                "cross_level_notes": "Carry controls forward.",
            },
        )
        wrapped(agent)
        self.assertFalse(wiped["called"])
        self.assertIn("SPACE", agent._summarized_knowledge["action_model"])
        self.assertIn("Reach the exit.", agent._summarized_knowledge["goal_model"])
        self.assertEqual(agent._summarized_knowledge["current_plan"], "")
        self.assertEqual(
            agent._summarized_knowledge["cross_level_notes"],
            "Carry controls forward.",
        )

    def test_wrapper_defers_to_original_on_game_over(self):
        def original(self) -> None:
            for key in (
                "world_model",
                "goal_model",
                "action_model",
                "recent_findings",
                "open_questions",
                "current_plan",
            ):
                self._summarized_knowledge[key] = ""

        wrapped = wrap_update_from_step_summary(original)
        agent = SimpleNamespace(
            _last_step_summary={"game_over": True, "level_transition": False},
            _summarized_knowledge={
                "world_model": "SPACE toggles the held object.",
                "goal_model": "Reach the exit.",
                "action_model": "ACTION1 moves the player.",
                "recent_findings": "x",
                "open_questions": "y",
                "current_plan": "z",
                "cross_level_notes": "keep me",
            },
        )
        wrapped(agent)
        self.assertEqual(agent._summarized_knowledge["world_model"], "")
        self.assertEqual(agent._summarized_knowledge["action_model"], "")
        self.assertEqual(agent._summarized_knowledge["cross_level_notes"], "keep me")


class NotebookSyncTests(unittest.TestCase):
    def test_notebook_embeds_current_s3_source_without_s1_or_s2(self):
        source = (ROOT / "src" / "s3_cross_level_transfer.py").read_text(encoding="utf-8")
        notebook = (
            ROOT
            / "tmp"
            / "kernels"
            / "s3-cross-level"
            / "duck-qwen3-8-flash-next-nvfp4-mtp.ipynb"
        )
        if not notebook.is_file():
            self.skipTest("S3 notebook is not present")
        nb = json.loads(notebook.read_text(encoding="utf-8"))
        joined = "\n".join(
            "".join(cell.get("source") or [])
            if isinstance(cell.get("source"), list)
            else str(cell.get("source") or "")
            for cell in nb["cells"]
        )
        self.assertIn("S3 cross-level transfer", joined)
        self.assertIn(source.strip(), joined)
        self.assertNotIn("install_s1_hooks", joined)
        self.assertNotIn("install_s2_hooks", joined)
        self.assertNotIn("arc-agi-3-s1-v1", joined)
        self.assertGreaterEqual(joined.count("bm.solver.concurrency = 28"), 1)


if __name__ == "__main__":
    unittest.main()
