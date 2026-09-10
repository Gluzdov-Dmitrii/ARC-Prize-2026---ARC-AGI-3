"""Tests for S6 scheduled simplification: 8-turn history and dropped-transcript fold-in."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.notebook_prose import (
    FORBIDDEN_FOREIGN_FIRST_PERSON,
    assert_our_prose,
    joined_markdown,
)
from src.s6_scheduled_simplification import (
    KEEP_ASSISTANT_TURNS,
    compact_transcript,
    count_assistant_turns,
    extract_labeled_blocks,
    keep_recent_assistant_turns,
    merge_dropped_into_knowledge,
    reset_counters,
    wrap_keep_recent_history_turns,
    wrap_persistent_history_messages,
    wrap_update_summarized_knowledge,
)


def _turn(idx: int, *, world: str | None = None, extra: str = "") -> list[dict]:
    body = f"Turn {idx}."
    if world:
        body += f"\nWorld model: {world}"
    if extra:
        body += f"\n{extra}"
    return [
        {"role": "user", "content": f"observe {idx}"},
        {"role": "assistant", "content": body},
    ]


class HistoryTrimTests(unittest.TestCase):
    def test_keeps_last_eight_assistant_turns(self):
        messages: list[dict] = [{"role": "system", "content": "sys"}]
        for idx in range(12):
            messages.extend(_turn(idx, world=f"fact-{idx}"))
        kept = keep_recent_assistant_turns(messages[1:], KEEP_ASSISTANT_TURNS)
        self.assertEqual(count_assistant_turns(kept), 8)
        self.assertIn("fact-11", kept[-1]["content"])
        self.assertNotIn("fact-0", json.dumps(kept))
        self.assertIn("fact-4", json.dumps(kept))

    def test_drops_leading_tool_messages_after_cut(self):
        messages = [
            {"role": "tool", "content": "stale"},
            {"role": "assistant", "content": "keep me"},
        ]
        kept = keep_recent_assistant_turns(messages, 1)
        self.assertEqual(kept, [{"role": "assistant", "content": "keep me"}])


class CompactionTests(unittest.TestCase):
    def test_labeled_facts_fold_into_empty_memory(self):
        knowledge = {
            "world_model": "",
            "goal_model": "",
            "action_model": "",
            "recent_findings": "",
            "open_questions": "",
            "current_plan": "",
            "cross_level_notes": "",
        }
        dropped = [
            {
                "role": "assistant",
                "content": (
                    "World model: SPACE toggles the crate.\n"
                    "Goal model: Collect all keys.\n"
                    "Action model: ACTION1 moves one step.\n"
                    "Open questions: What does ACTION6 do?\n"
                    "Plan: Try ACTION2 next.\n"
                    "Hypothesis: ACTION6 is a no-op.\n"
                ),
            }
        ]
        merge_dropped_into_knowledge(knowledge, dropped)
        self.assertIn("SPACE toggles the crate.", knowledge["world_model"])
        self.assertIn("Collect all keys.", knowledge["goal_model"])
        self.assertIn("ACTION1 moves one step.", knowledge["action_model"])
        self.assertIn("What does ACTION6 do?", knowledge["open_questions"])
        self.assertIn("Disproved:", knowledge["recent_findings"])
        self.assertIn("ACTION6", knowledge["recent_findings"])
        self.assertEqual(knowledge["current_plan"], "Try ACTION2 next.")

    def test_does_not_overwrite_newer_plan_or_duplicate_facts(self):
        knowledge = {
            "world_model": "SPACE toggles the crate.",
            "goal_model": "",
            "action_model": "",
            "recent_findings": "",
            "open_questions": "",
            "current_plan": "Press ACTION3 now.",
            "cross_level_notes": "",
        }
        dropped = [
            {
                "role": "assistant",
                "content": "World model: SPACE toggles the crate.\nPlan: Sweep left to right.",
            }
        ]
        merge_dropped_into_knowledge(knowledge, dropped)
        self.assertEqual(knowledge["world_model"].count("SPACE toggles the crate."), 1)
        self.assertEqual(knowledge["current_plan"], "Press ACTION3 now.")

    def test_preserves_s4_no_impact_notes(self):
        knowledge = {
            "world_model": "",
            "goal_model": "",
            "action_model": "",
            "recent_findings": (
                "No-impact memory: ACTION1 is confirmed no-impact in this semantic state "
                "(HUD/timer-only or identical interior); try a different action."
            ),
            "open_questions": "",
            "current_plan": "",
            "cross_level_notes": "",
        }
        dropped = [
            {
                "role": "assistant",
                "content": "Recent findings: ACTION7 never changes the interior.",
            }
        ]
        merge_dropped_into_knowledge(knowledge, dropped)
        self.assertIn("No-impact memory:", knowledge["recent_findings"])
        self.assertIn("ACTION1", knowledge["recent_findings"])
        self.assertIn("ACTION7", knowledge["recent_findings"])

    def test_compact_transcript_drops_prefix_and_keeps_eight(self):
        knowledge = {
            "world_model": "",
            "goal_model": "",
            "action_model": "",
            "recent_findings": "",
            "open_questions": "",
            "current_plan": "Live plan.",
            "cross_level_notes": "",
        }
        messages: list[dict] = [{"role": "system", "content": "sys"}]
        for idx in range(12):
            messages.extend(_turn(idx, world=f"fact-{idx}"))
        stats = compact_transcript(knowledge, messages)
        self.assertTrue(stats["compacted"])
        self.assertEqual(stats["kept_assistant_turns"], 8)
        self.assertIn("fact-0", knowledge["world_model"])
        self.assertIn("fact-3", knowledge["world_model"])
        self.assertNotIn("fact-11", knowledge["world_model"])
        self.assertEqual(knowledge["current_plan"], "Live plan.")

    def test_extract_labeled_blocks_reads_multiline(self):
        blocks = extract_labeled_blocks(
            "World model: walls block movement\nOpen questions: How does RESET work?"
        )
        self.assertIn("walls block movement", blocks["World model"])
        self.assertIn("How does RESET work?", blocks["Open questions"])


class WrapperTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_counters()

    def test_keep_wrapper_caps_thirty_to_eight(self):
        seen = {}

        def original(self, messages, *, max_turns):
            seen["max_turns"] = max_turns
            return messages[-max_turns:]

        wrapped = wrap_keep_recent_history_turns(original)
        out = wrapped(SimpleNamespace(), [{"role": "assistant"}] * 12, max_turns=30)
        self.assertEqual(seen["max_turns"], 8)
        self.assertEqual(len(out), 8)

    def test_persistent_wrapper_compacts_then_calls_original(self):
        called = {}

        def original(self, messages, *, tools=None):
            called["n"] = len(messages)
            called["tools"] = tools
            return [{"role": "user", "content": "kept"}]

        agent = SimpleNamespace(
            _summarized_knowledge={
                "world_model": "",
                "goal_model": "",
                "action_model": "",
                "recent_findings": "",
                "open_questions": "",
                "current_plan": "",
                "cross_level_notes": "",
            }
        )
        messages: list[dict] = [{"role": "system", "content": "sys"}]
        for idx in range(10):
            messages.extend(_turn(idx, world=f"old-{idx}"))
        wrapped = wrap_persistent_history_messages(original)
        result = wrapped(agent, messages, tools=["python"])
        self.assertEqual(result, [{"role": "user", "content": "kept"}])
        self.assertEqual(called["n"], len(messages))
        self.assertEqual(called["tools"], ["python"])
        self.assertIn("old-0", agent._summarized_knowledge["world_model"])

    def test_fallback_trims_history_on_the_agent(self):
        def original(self, content):
            return content

        history: list[dict] = []
        for idx in range(10):
            history.extend(_turn(idx, world=f"hist-{idx}"))
        agent = SimpleNamespace(
            _history_messages=history,
            _summarized_knowledge={
                "world_model": "",
                "goal_model": "",
                "action_model": "",
                "recent_findings": "",
                "open_questions": "",
                "current_plan": "Keep me.",
                "cross_level_notes": "",
            },
        )
        wrapped = wrap_update_summarized_knowledge(original)
        wrapped(agent, "World model: ignored live")
        self.assertEqual(count_assistant_turns(agent._history_messages), 8)
        self.assertIn("hist-0", agent._summarized_knowledge["world_model"])
        self.assertEqual(agent._summarized_knowledge["current_plan"], "Keep me.")


class NotebookS6Tests(unittest.TestCase):
    def test_s6_notebook_keeps_s4_adds_s6_skips_rejects(self):
        notebook = (
            ROOT
            / "tmp"
            / "kernels"
            / "s6-simplify"
            / "duck-qwen3-8-flash-next-nvfp4-mtp.ipynb"
        )
        if not notebook.is_file():
            self.skipTest("S6 notebook is not present")
        p0 = (ROOT / "src" / "p0_phase_a_modes.py").read_text(encoding="utf-8")
        s6 = (ROOT / "src" / "s6_scheduled_simplification.py").read_text(encoding="utf-8")
        nb = json.loads(notebook.read_text(encoding="utf-8"))
        joined = "\n".join(
            "".join(cell.get("source") or [])
            if isinstance(cell.get("source"), list)
            else str(cell.get("source") or "")
            for cell in nb["cells"]
        )
        self.assertIn(p0.strip(), joined)
        self.assertIn(s6.strip(), joined)
        self.assertIn("install_s4_hooks", joined)
        self.assertIn("install_s6_hooks", joined)
        self.assertIn("KEEP_ASSISTANT_TURNS", joined)
        self.assertNotIn("hud_bottom_rows=2", joined)
        self.assertNotIn("install_s1_hooks", joined)
        self.assertNotIn("install_s2_hooks", joined)
        self.assertNotIn("install_s3_hooks", joined)
        assert_our_prose(joined_markdown(nb))
        for blob in FORBIDDEN_FOREIGN_FIRST_PERSON:
            self.assertNotIn(blob, joined)
        meta = json.loads(
            (notebook.parent / "kernel-metadata.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            meta.get("id"),
            "dmitriigluzdov/arc-agi-3-s6-scheduled-simplification-flash-nvfp4",
        )
        self.assertTrue(meta.get("is_private"))
        self.assertFalse(meta.get("enable_internet"))
        self.assertEqual(meta.get("machine_shape"), "NvidiaRtxPro6000")
        self.assertIn("S6", meta.get("title", ""))


if __name__ == "__main__":
    unittest.main()
