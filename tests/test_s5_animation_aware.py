"""Tests for S5 labeled animation stills plus actionable current frame."""

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
from src.s5_animation_aware import (
    ACTIONABLE_CAPTION,
    LABEL_INTRO,
    as_grid,
    bind_animation_grids,
    build_labeled_user_message,
    clear_animation_grids,
    compact_animation_grids,
    current_animation_grids,
    grids_from_state,
    reset_counters,
    wrap_build_user_message,
    wrap_execute_action,
    wrap_play_one,
)


def _grid(value: int) -> list[list[int]]:
    return [[value, value], [value, value]]


class CompactTests(unittest.TestCase):
    def test_keeps_short_sequence_and_drops_duplicates(self):
        grids = [_grid(1), _grid(1), _grid(2), _grid(3)]
        out = compact_animation_grids(grids, max_images=4)
        self.assertEqual(out, [_grid(1), _grid(2), _grid(3)])

    def test_samples_first_and_last_when_capping(self):
        grids = [_grid(i) for i in range(5)]
        out = compact_animation_grids(grids, max_images=3)
        self.assertEqual(len(out), 3)
        self.assertEqual(out[0], _grid(0))
        self.assertEqual(out[-1], _grid(4))

    def test_excludes_settled_current_frame(self):
        grids = [_grid(1), _grid(2), _grid(3)]
        out = compact_animation_grids(grids, max_images=3, exclude=_grid(3))
        self.assertEqual(out, [_grid(1), _grid(2)])

    def test_as_grid_reads_taaf_frame_data(self):
        frame = SimpleNamespace(data=[[1, 2], [3, 4]])
        self.assertEqual(as_grid(frame), [[1, 2], [3, 4]])


class CaptureTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_animation_grids()
        reset_counters()

    def test_execute_wrapper_binds_animation_not_final_frame(self):
        class Frame:
            def __init__(self, data: list[list[int]]) -> None:
                self.data = data

        state = SimpleNamespace(
            animation_frames=[Frame(_grid(1)), Frame(_grid(2))],
            frame=Frame(_grid(9)),
        )
        session = SimpleNamespace(game=SimpleNamespace(current_state=state))

        def original(self, action):
            return {"executed": True, "action": action}

        wrapped = wrap_execute_action(original)
        payload = wrapped(session, "ACTION1")
        self.assertEqual(payload["executed"], True)
        self.assertEqual(current_animation_grids(), [_grid(1), _grid(2)])
        self.assertEqual(grids_from_state(state), [_grid(1), _grid(2)])

    def test_play_one_clears_thread_local(self):
        bind_animation_grids([_grid(4)])
        seen = {}

        def original(self, game, index, pass_index, local_server=None):
            seen["inside"] = [row[0][0] for row in current_animation_grids()]
            bind_animation_grids([_grid(7)])
            return "ok"

        wrapped = wrap_play_one(original)
        self.assertEqual(wrapped(SimpleNamespace(), SimpleNamespace(), 0, 0), "ok")
        self.assertEqual(seen["inside"], [])
        self.assertEqual(current_animation_grids(), [])


class MessageTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_counters()
        clear_animation_grids()

    def test_empty_animation_returns_none_so_duck_path_is_used(self):
        frame = SimpleNamespace(grid=_grid(9), step=1, level=1)
        self.assertIsNone(build_labeled_user_message("prompt", frame, []))

    def test_labeled_parts_keep_actionable_last(self):
        rendered = []

        def render(grid, *, upscale):
            rendered.append((grid[0][0], upscale))
            return {"type": "image_url", "image_url": {"url": f"img-{grid[0][0]}-{upscale}"}}

        import src.s5_animation_aware as s5

        previous = s5.duck_current_image_part
        s5.duck_current_image_part = lambda frame: {
            "type": "image_url",
            "image_url": {"url": "actionable"},
        }
        try:
            frame = SimpleNamespace(grid=_grid(9), step=1, level=1)
            message = build_labeled_user_message(
                "observe now",
                frame,
                [_grid(1), _grid(2), _grid(3)],
                render_part=render,
            )
        finally:
            s5.duck_current_image_part = previous
        self.assertIsNotNone(message)
        content = message["content"]
        texts = [part["text"] for part in content if part.get("type") == "text"]
        images = [part["image_url"]["url"] for part in content if part.get("type") == "image_url"]
        self.assertIn(LABEL_INTRO, texts[0])
        self.assertTrue(any("ANIMATION 1/3" in text for text in texts))
        self.assertEqual(texts[-1], ACTIONABLE_CAPTION)
        self.assertEqual(images[-1], "actionable")
        self.assertEqual(len(images), 4)
        self.assertTrue(all(upscale == 8 for _value, upscale in rendered))

    def test_build_wrapper_falls_back_when_images_disabled(self):
        import src.s5_animation_aware as s5

        bind_animation_grids([_grid(1)])
        previous = s5.images_enabled
        s5.images_enabled = lambda: False

        def original(self, prompt, frame):
            return {"role": "user", "content": prompt}

        try:
            wrapped = wrap_build_user_message(original)
            out = wrapped(SimpleNamespace(), "plain", SimpleNamespace(grid=_grid(9)))
        finally:
            s5.images_enabled = previous
        self.assertEqual(out, {"role": "user", "content": "plain"})


class NotebookS5Tests(unittest.TestCase):
    def test_s5_notebook_keeps_s4_adds_s5_skips_rejects(self):
        notebook = (
            ROOT
            / "tmp"
            / "kernels"
            / "s5-animation"
            / "duck-qwen3-8-flash-next-nvfp4-mtp.ipynb"
        )
        if not notebook.is_file():
            self.skipTest("S5 notebook is not present")
        p0 = (ROOT / "src" / "p0_phase_a_modes.py").read_text(encoding="utf-8")
        s5 = (ROOT / "src" / "s5_animation_aware.py").read_text(encoding="utf-8")
        nb = json.loads(notebook.read_text(encoding="utf-8"))
        joined = "\n".join(
            "".join(cell.get("source") or [])
            if isinstance(cell.get("source"), list)
            else str(cell.get("source") or "")
            for cell in nb["cells"]
        )
        self.assertIn(p0.strip(), joined)
        self.assertIn(s5.strip(), joined)
        self.assertIn("install_s4_hooks", joined)
        self.assertIn("install_s5_hooks", joined)
        self.assertIn("S5_ANIMATION_AWARE", joined)
        self.assertIn("MAX_ANIMATION_IMAGES", joined)
        self.assertNotIn("hud_bottom_rows=2", joined)
        self.assertNotIn("install_s1_hooks", joined)
        self.assertNotIn("install_s2_hooks", joined)
        self.assertNotIn("install_s3_hooks", joined)
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
        self.assertIn("S5", meta.get("title", ""))
        self.assertEqual(meta.get("id_no"), 132850984)
