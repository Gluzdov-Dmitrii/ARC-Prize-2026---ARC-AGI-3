"""Tests for S8 ACTION7/UNDO completeness on the S4 parent."""

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
from src.s8_action7_undo import (
    ENGINE_UNDO,
    MODEL_UNDO,
    UNDO_HINT,
    apply_action7_map,
    count_undo_labels,
    duck_to_engine_action,
    duck_to_model_action,
    duck_to_model_actions,
    format_valid_action_line,
    reset_counters,
    wrap_format_valid_action_line,
    wrap_normalize_actions,
)


def _duck_maps() -> tuple[dict[str, str], dict[str, str]]:
    engine = {
        "ACTION1": "UP",
        "ACTION2": "DOWN",
        "ACTION3": "LEFT",
        "ACTION4": "RIGHT",
        "ACTION5": "SPACE",
        "ACTION6": "MOUSE",
        "RESET": "RESET",
    }
    model = {value: key for key, value in engine.items()}
    return engine, model


class MapTests(unittest.TestCase):
    def test_before_patch_action7_is_not_executable(self):
        engine, model = _duck_maps()
        self.assertIsNone(duck_to_engine_action("UNDO", engine, model))
        self.assertIsNone(duck_to_engine_action("ACTION7", engine, model))
        self.assertEqual(duck_to_model_action("ACTION7", engine), "ACTION7")

    def test_after_patch_undo_roundtrip_and_passthrough(self):
        engine, model = _duck_maps()
        apply_action7_map(engine, model)
        self.assertEqual(duck_to_model_action("ACTION7", engine), MODEL_UNDO)
        self.assertEqual(duck_to_engine_action("UNDO", engine, model), ENGINE_UNDO)
        self.assertEqual(duck_to_engine_action("ACTION7", engine, model), ENGINE_UNDO)
        self.assertEqual(duck_to_engine_action("UP", engine, model), "ACTION1")
        listed = duck_to_model_actions(["ACTION1", "ACTION7", "RESET"], engine)
        self.assertEqual(listed, ["UP", "UNDO", "RESET"])

    def test_does_not_invent_undo_when_gateway_omits_action7(self):
        engine, model = _duck_maps()
        apply_action7_map(engine, model)
        listed = duck_to_model_actions(["ACTION1", "ACTION5"], engine)
        self.assertNotIn("UNDO", listed)
        self.assertNotIn("ACTION7", listed)


class HintAndCountTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_counters()

    def test_hint_appended_only_when_undo_listed(self):
        plain = format_valid_action_line("Valid actions right now: UP, SPACE.", ["UP", "SPACE"])
        self.assertEqual(plain, "Valid actions right now: UP, SPACE.")
        with_undo = format_valid_action_line(
            "Valid actions right now: UP, UNDO.", ["UP", "UNDO"]
        )
        self.assertIn(UNDO_HINT, with_undo)
        self.assertIn("UP", with_undo)

    def test_count_undo_labels_from_batch(self):
        n = count_undo_labels(
            [{"action": "UP"}, {"action": "undo"}, {"action": "ACTION7"}]
        )
        self.assertEqual(n, 2)


class WrapperTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_counters()

    def test_format_wrapper_uses_normalized_names(self):
        def original(valid_actions):
            return "Valid actions right now: " + ", ".join(valid_actions or []) + "."

        def normalize(valid_actions):
            engine, model = _duck_maps()
            apply_action7_map(engine, model)
            return duck_to_model_actions(valid_actions, engine)

        wrapped = wrap_format_valid_action_line(original, normalize)
        out = wrapped(["ACTION1", "ACTION7"])
        self.assertIn("UNDO", out)
        self.assertIn(UNDO_HINT, out)

    def test_normalize_wrapper_counts_requested_and_parsed(self):
        class Action:
            def __init__(self, name: str) -> None:
                self.id = SimpleNamespace(name=name)

        def original(self, arguments):
            return [Action("ACTION7")], None

        wrapped = wrap_normalize_actions(original)
        actions, error = wrapped(
            SimpleNamespace(),
            {"actions": [{"action": "UNDO"}]},
        )
        self.assertIsNone(error)
        self.assertEqual(len(actions), 1)
        from src.s8_action7_undo import _COUNTERS

        self.assertEqual(_COUNTERS["undo_requested"], 1)
        self.assertEqual(_COUNTERS["undo_parsed"], 1)


class NotebookS8Tests(unittest.TestCase):
    def test_s8_notebook_keeps_s4_adds_s8_skips_rejects(self):
        notebook = (
            ROOT
            / "tmp"
            / "kernels"
            / "s8-action7"
            / "duck-qwen3-8-flash-next-nvfp4-mtp.ipynb"
        )
        if not notebook.is_file():
            self.skipTest("S8 notebook is not present")
        p0 = (ROOT / "src" / "p0_phase_a_modes.py").read_text(encoding="utf-8")
        s8 = (ROOT / "src" / "s8_action7_undo.py").read_text(encoding="utf-8")
        nb = json.loads(notebook.read_text(encoding="utf-8"))
        joined = "\n".join(
            "".join(cell.get("source") or [])
            if isinstance(cell.get("source"), list)
            else str(cell.get("source") or "")
            for cell in nb["cells"]
        )
        self.assertIn(p0.strip(), joined)
        self.assertIn(s8.strip(), joined)
        self.assertIn("install_s4_hooks", joined)
        self.assertIn("install_s8_hooks", joined)
        self.assertIn("S8_ACTION7_UNDO", joined)
        self.assertIn("ACTION7", joined)
        self.assertNotIn("hud_bottom_rows=2", joined)
        self.assertNotIn("install_s1_hooks", joined)
        self.assertNotIn("install_s2_hooks", joined)
        self.assertNotIn("install_s3_hooks", joined)
        self.assertNotIn("install_s5_hooks", joined)
        self.assertNotIn("install_s6_hooks", joined)
        self.assertNotIn("install_s7_hooks", joined)
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
        self.assertIn("S8", meta.get("title", ""))
        self.assertEqual(meta.get("id_no"), 132850984)
