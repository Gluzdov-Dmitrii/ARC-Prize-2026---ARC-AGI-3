"""Tests for S9 consecutive-RESET wipe guard on the S4 parent."""

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
from src.s9_reset_guard import (
    SKIP_ERROR,
    filter_consecutive_resets,
    is_reset_action,
    reset_counters,
    wrap_normalize_actions,
)


def _act(name: str) -> SimpleNamespace:
    return SimpleNamespace(id=SimpleNamespace(name=name))


class FilterTests(unittest.TestCase):
    def test_keeps_first_reset_after_a_move(self):
        kept, dropped = filter_consecutive_resets([_act("RESET")], "UP")
        self.assertEqual([is_reset_action(item) for item in kept], [True])
        self.assertEqual(dropped, 0)

    def test_drops_reset_after_engine_reset(self):
        kept, dropped = filter_consecutive_resets([_act("RESET")], "RESET")
        self.assertEqual(kept, [])
        self.assertEqual(dropped, 1)

    def test_drops_second_reset_in_batch_keeps_following_move(self):
        kept, dropped = filter_consecutive_resets(
            [_act("RESET"), _act("RESET"), _act("UP")],
            "LEFT",
        )
        self.assertEqual([item.id.name for item in kept], ["RESET", "UP"])
        self.assertEqual(dropped, 1)

    def test_allows_reset_after_intervening_action(self):
        kept, dropped = filter_consecutive_resets(
            [_act("RESET"), _act("UP"), _act("RESET")],
            "SPACE",
        )
        self.assertEqual([item.id.name for item in kept], ["RESET", "UP", "RESET"])
        self.assertEqual(dropped, 0)


class WrapperTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_counters()

    def test_wrapper_skips_entire_consecutive_reset_batch(self):
        def original(self, arguments):
            return [_act("RESET"), _act("RESET")], None

        wrapped = wrap_normalize_actions(original)
        session = SimpleNamespace(last_engine_action="RESET")
        actions, error = wrapped(session, {"actions": [{"action": "RESET"}]})
        self.assertIsNone(actions)
        self.assertEqual(error, SKIP_ERROR)
        from src.s9_reset_guard import _COUNTERS

        self.assertEqual(_COUNTERS["resets_dropped"], 2)

    def test_wrapper_keeps_non_reset_after_auto_reset(self):
        def original(self, arguments):
            return [_act("UP")], None

        wrapped = wrap_normalize_actions(original)
        session = SimpleNamespace(last_engine_action="RESET")
        actions, error = wrapped(session, {"action": "UP"})
        self.assertIsNone(error)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].id.name, "UP")


class NotebookS9Tests(unittest.TestCase):
    def test_s9_notebook_keeps_s4_adds_s9_skips_rejects(self):
        notebook = (
            ROOT
            / "tmp"
            / "kernels"
            / "s9-reset-guard"
            / "duck-qwen3-8-flash-next-nvfp4-mtp.ipynb"
        )
        if not notebook.is_file():
            self.skipTest("S9 notebook is not present")
        p0 = (ROOT / "src" / "p0_phase_a_modes.py").read_text(encoding="utf-8")
        s9 = (ROOT / "src" / "s9_reset_guard.py").read_text(encoding="utf-8")
        nb = json.loads(notebook.read_text(encoding="utf-8"))
        joined = "\n".join(
            "".join(cell.get("source") or [])
            if isinstance(cell.get("source"), list)
            else str(cell.get("source") or "")
            for cell in nb["cells"]
        )
        self.assertIn(p0.strip(), joined)
        self.assertIn(s9.strip(), joined)
        self.assertIn("install_s4_hooks", joined)
        self.assertIn("install_s9_hooks", joined)
        self.assertIn("S9_RESET_GUARD", joined)
        self.assertNotIn("hud_bottom_rows=2", joined)
        self.assertNotIn("install_s1_hooks", joined)
        self.assertNotIn("install_s5_hooks", joined)
        self.assertNotIn("install_s6_hooks", joined)
        self.assertNotIn("install_s7_hooks", joined)
        self.assertNotIn("install_s8_hooks", joined)
        assert_our_prose(joined_markdown(nb))
        for blob in FORBIDDEN_FOREIGN_FIRST_PERSON:
            self.assertNotIn(blob, joined)
        meta = json.loads(
            (notebook.parent / "kernel-metadata.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            meta.get("id"),
            "dmitriigluzdov/arc-agi-3-s7-adaptive-scheduler-flash-nvfp4",
        )
        self.assertTrue(meta.get("is_private"))
        self.assertFalse(meta.get("enable_internet"))
        self.assertEqual(meta.get("machine_shape"), "NvidiaRtxPro6000")
        self.assertIn("S9", meta.get("title", ""))
        self.assertEqual(meta.get("id_no"), 132850984)
