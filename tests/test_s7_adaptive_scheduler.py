"""Tests for S7 coverage-first / stuck-cut adaptive scheduler."""

from __future__ import annotations

import json
import math
import sys
import time
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
from src.s4_semantic_no_impact import classify_transition
from src.s7_adaptive_scheduler import (
    STUCK_STREAK,
    CoverageBook,
    game_cap_seconds,
    kind_from_step,
    reset_book,
    wave_coverage_cap,
    wrap_execute_action,
    wrap_play_one,
    wrap_runtime_limit_reached,
    wrap_timing_payload,
)


class WaveCapTests(unittest.TestCase):
    def test_hidden_set_keeps_duck_cap_when_waves_fit(self):
        cap = wave_coverage_cap(
            31800.0,
            leftover_games=110,
            concurrency=28,
            default_max_s=7920.0,
        )
        self.assertEqual(cap, 7920.0)
        self.assertEqual(math.ceil(110 / 28), 4)

    def test_tight_remaining_splits_by_waves(self):
        cap = wave_coverage_cap(
            4000.0,
            leftover_games=50,
            concurrency=28,
            default_max_s=7920.0,
        )
        self.assertEqual(math.ceil(50 / 28), 2)
        self.assertAlmostEqual(cap, 2000.0)

    def test_smoke_two_games_stay_on_smoke_max(self):
        cap = wave_coverage_cap(
            31800.0,
            leftover_games=2,
            concurrency=2,
            default_max_s=180.0,
        )
        self.assertEqual(cap, 180.0)


class GameCapTests(unittest.TestCase):
    def test_stuck_returns_elapsed(self):
        cap, reason = game_cap_seconds(
            elapsed_s=400.0,
            remaining_s=30000.0,
            leftover_games=110,
            unstarted_games=82,
            concurrency=28,
            default_max_s=7920.0,
            stuck=True,
            progressing=False,
            late_level=False,
        )
        self.assertEqual(cap, 400.0)
        self.assertEqual(reason, "stuck")

    def test_progressing_does_not_exceed_default_when_waves_fit(self):
        cap, reason = game_cap_seconds(
            elapsed_s=10.0,
            remaining_s=31800.0,
            leftover_games=110,
            unstarted_games=82,
            concurrency=28,
            default_max_s=7920.0,
            stuck=False,
            progressing=True,
            late_level=False,
        )
        self.assertEqual(reason, "progressing")
        self.assertEqual(cap, 7920.0)

    def test_late_level_uses_leftover_after_unstarted_reserve_when_tight(self):
        cap, reason = game_cap_seconds(
            elapsed_s=50.0,
            remaining_s=4000.0,
            leftover_games=2,
            unstarted_games=0,
            concurrency=28,
            default_max_s=7920.0,
            stuck=False,
            progressing=True,
            late_level=True,
        )
        self.assertEqual(reason, "late_level")
        self.assertEqual(cap, 4000.0)


class BookTests(unittest.TestCase):
    def test_hud_only_reaches_stuck_after_streak(self):
        book = CoverageBook(stuck_streak=3, stuck_enabled=True)
        book.bind_total(2)
        book.start_game("g1")
        for _ in range(3):
            rec = book.observe_step("g1", kind="hud_only")
        self.assertTrue(rec["stuck"])
        self.assertEqual(rec["no_progress_streak"], 3)
        reached = book.limit_reached(
            "g1", elapsed_s=12.0, remaining_s=30000.0, default_max_s=7920.0
        )
        self.assertTrue(reached)
        self.assertEqual(book.stuck_cuts, 1)

    def test_real_change_and_level_reset_stuck(self):
        book = CoverageBook(stuck_streak=3, stuck_enabled=True)
        book.start_game("g1")
        book.observe_step("g1", kind="identical")
        book.observe_step("g1", kind="hud_only")
        rec = book.observe_step("g1", kind="real_change")
        self.assertFalse(rec["stuck"])
        self.assertTrue(rec["progressing"])
        self.assertEqual(rec["no_progress_streak"], 0)
        rec = book.observe_step(
            "g1", kind="identical", level_completed=True, levels_completed=2
        )
        self.assertTrue(rec["late_level"])
        self.assertEqual(rec["last_kind"], "level_completed")

    def test_smoke_action_cap_disables_stuck(self):
        book = CoverageBook(stuck_streak=8, stuck_enabled=False)
        book.start_game("g1")
        rec = None
        for _ in range(8):
            rec = book.observe_step("g1", kind="identical")
        self.assertFalse(rec["stuck"])


class KindTests(unittest.TestCase):
    def test_kind_uses_s4_classifier_not_raw_pixels(self):
        import src.s7_adaptive_scheduler as s7

        previous = s7._CLASSIFY
        s7._CLASSIFY = classify_transition
        try:
            before = [[1, 1, 1], [2, 0, 2], [2, 0, 2]]
            after = [[9, 9, 9], [2, 0, 2], [2, 0, 2]]
            kind = kind_from_step({"board_changed": True}, before, after)
            self.assertEqual(kind, "hud_only")
        finally:
            s7._CLASSIFY = previous

    def test_kind_falls_back_to_board_changed(self):
        import src.s7_adaptive_scheduler as s7

        previous = s7._CLASSIFY
        s7._CLASSIFY = None
        try:
            kind = kind_from_step({"board_changed": True}, None, None)
            self.assertEqual(kind, "real_change")
            kind = kind_from_step({"board_changed": False}, None, None)
            self.assertEqual(kind, "identical")
            kind = kind_from_step({"level_completed": True}, None, None)
            self.assertEqual(kind, "level_completed")
        finally:
            s7._CLASSIFY = previous


class WrapperTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_book(
            notebook_budget_s=32400.0,
            default_max_s=7920.0,
            concurrency=28,
            stuck_streak=3,
            stuck_enabled=True,
        )

    def test_runtime_wrapper_cuts_stuck_game(self):
        book = reset_book(
            default_max_s=7920.0,
            concurrency=28,
            stuck_streak=2,
            stuck_enabled=True,
        )
        book.bind_total(110)
        book.start_game("g1")
        book.observe_step("g1", kind="identical")
        book.observe_step("g1", kind="identical")

        def original(self):
            return False

        session = SimpleNamespace(
            game=SimpleNamespace(game_run=SimpleNamespace(game_id="g1")),
            game_index=0,
            started_at=time.monotonic() - 50.0,
            solver=SimpleNamespace(
                max_runtime_s_per_game=7920.0,
                soft_time_remaining_seconds=lambda: 30000.0,
            ),
        )
        wrapped = wrap_runtime_limit_reached(original)
        self.assertTrue(wrapped(session))

    def test_timing_payload_shrinks_remaining_to_cap(self):
        book = reset_book(
            default_max_s=180.0,
            concurrency=2,
            stuck_enabled=False,
        )
        book.bind_total(2)
        book.start_game("g1")

        def original(self):
            return {"run_elapsed_seconds": 10.0, "time_remaining_seconds": 170.0}

        session = SimpleNamespace(
            game=SimpleNamespace(game_run=SimpleNamespace(game_id="g1")),
            game_index=0,
            solver=SimpleNamespace(
                max_runtime_s_per_game=180.0,
                soft_time_remaining_seconds=lambda: 31800.0,
            ),
        )
        wrapped = wrap_timing_payload(original)
        payload = wrapped(session)
        self.assertLessEqual(payload["time_remaining_seconds"], 170.0)
        self.assertGreaterEqual(payload["time_remaining_seconds"], 0.0)

    def test_execute_action_observes_hud_only(self):
        import src.s7_adaptive_scheduler as s7

        book = reset_book(stuck_streak=8, stuck_enabled=True)
        book.start_game("g1")
        previous = s7._CLASSIFY
        s7._CLASSIFY = classify_transition

        class Frame:
            def __init__(self, top: int) -> None:
                self.data = [[top, top], [top, top], [4, 5], [6, 7]]

        class Game:
            def __init__(self) -> None:
                self.game_run = SimpleNamespace(game_id="g1")
                self.current_state = SimpleNamespace(frame=Frame(1))

        game = Game()

        def original(self, action):
            self.game.current_state.frame = Frame(9)
            return {"board_changed": True, "level_completed": False, "score": 0}

        session = SimpleNamespace(game=game, game_index=0)
        wrapped = wrap_execute_action(original)
        wrapped(session, "ACTION1")
        rec = book.games["g1"]
        s7._CLASSIFY = previous
        self.assertEqual(rec["last_kind"], "hud_only")
        self.assertEqual(rec["no_progress_streak"], 1)
        self.assertFalse(rec["progressing"])

    def test_play_one_starts_and_finishes(self):
        book = reset_book()
        book.bind_total(2)
        seen = {}

        def original(self, game, index, pass_index, local_server=None):
            seen["id"] = game.game_run.game_id
            return "ok"

        wrapped = wrap_play_one(original)
        game = SimpleNamespace(game_run=SimpleNamespace(game_id="tn36"))
        self.assertEqual(wrapped(SimpleNamespace(), game, 0, 0), "ok")
        rec = book.games["tn36"]
        self.assertTrue(rec["started"])
        self.assertTrue(rec["finished"])
        self.assertEqual(seen["id"], "tn36")


class NotebookS7Tests(unittest.TestCase):
    def test_s7_notebook_keeps_s4_adds_s7_skips_rejects(self):
        notebook = (
            ROOT
            / "tmp"
            / "kernels"
            / "s7-scheduler"
            / "duck-qwen3-8-flash-next-nvfp4-mtp.ipynb"
        )
        if not notebook.is_file():
            self.skipTest("S7 notebook is not present")
        p0 = (ROOT / "src" / "p0_phase_a_modes.py").read_text(encoding="utf-8")
        s7 = (ROOT / "src" / "s7_adaptive_scheduler.py").read_text(encoding="utf-8")
        nb = json.loads(notebook.read_text(encoding="utf-8"))
        joined = "\n".join(
            "".join(cell.get("source") or [])
            if isinstance(cell.get("source"), list)
            else str(cell.get("source") or "")
            for cell in nb["cells"]
        )
        self.assertIn(p0.strip(), joined)
        self.assertIn(s7.strip(), joined)
        self.assertIn("install_s4_hooks", joined)
        self.assertIn("install_s7_hooks", joined)
        self.assertIn("S7_ADAPTIVE_SCHEDULER", joined)
        self.assertNotIn("hud_bottom_rows=2", joined)
        self.assertNotIn("install_s1_hooks", joined)
        self.assertNotIn("install_s2_hooks", joined)
        self.assertNotIn("install_s3_hooks", joined)
        self.assertNotIn("install_s6_hooks", joined)
        assert_our_prose(joined_markdown(nb))
        for blob in FORBIDDEN_FOREIGN_FIRST_PERSON:
            self.assertNotIn(blob, joined)
        meta = json.loads(
            (notebook.parent / "kernel-metadata.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            meta.get("id"),
            "dmitriigluzdov/arc-agi-3-s4b-outer-hud-no-impact-flash-nvfp4",
        )
        self.assertTrue(meta.get("is_private"))
        self.assertFalse(meta.get("enable_internet"))
        self.assertEqual(meta.get("machine_shape"), "NvidiaRtxPro6000")
        self.assertIn("S7", meta.get("title", ""))
        self.assertIn("id_no", meta)
        self.assertEqual(meta.get("id_no"), 132850984)
