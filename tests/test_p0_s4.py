"""Tests for P0a Phase A modes and S4 HUD-insensitive no-impact memory."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.p0_phase_a_modes import (
    MODE_COMPETITION,
    MODE_KAGGLE_SMOKE,
    MODE_OFFLINE_EVAL,
    PRODUCTION_CONCURRENCY,
    PRODUCTION_MAX_RUNTIME_S_PER_GAME,
    PRODUCTION_NOTEBOOK_BUDGET_S,
    SMOKE_GAME_COUNT,
    SMOKE_MAX_ACTIONS_PER_GAME,
    apply_solver_settings,
    phase_a_mode,
    require_model_actions,
    select_offline_game_ids,
    should_run_public25_audit,
)
from src.notebook_prose import (
    FORBIDDEN_FOREIGN_FIRST_PERSON,
    assert_our_prose,
    joined_markdown,
)
from src.s4_semantic_no_impact import (
    NoImpactBook,
    classify_transition,
    inject_no_impact_notes,
    semantic_key,
    set_hud_bottom_rows,
    wrap_run_python_tool,
)


PUBLIC_IDS = tuple(f"game-{i:02d}" for i in range(25))


class PhaseAModeTests(unittest.TestCase):
    def test_rerun_keeps_production_budgets(self):
        self.assertEqual(phase_a_mode(true_submission=True), MODE_COMPETITION)
        bm = SimpleNamespace(
            solver=SimpleNamespace(
                max_runtime_s_per_game=0,
                analyzer_timeout=0,
                concurrency=0,
                max_actions_per_game=1,
                save_request_logs=True,
            )
        )
        target = SimpleNamespace(max_runtime_s=PRODUCTION_NOTEBOOK_BUDGET_S)
        mode = apply_solver_settings(bm, target, true_submission=True)
        self.assertEqual(mode, MODE_COMPETITION)
        self.assertEqual(bm.solver.max_runtime_s_per_game, PRODUCTION_MAX_RUNTIME_S_PER_GAME)
        self.assertEqual(bm.solver.concurrency, PRODUCTION_CONCURRENCY)
        self.assertIsNone(bm.solver.max_actions_per_game)
        self.assertFalse(should_run_public25_audit(mode))
        self.assertEqual(select_offline_game_ids(PUBLIC_IDS, mode=mode), list(PUBLIC_IDS))

    def test_smoke_uses_short_caps_and_two_games(self):
        bm = SimpleNamespace(
            solver=SimpleNamespace(
                max_runtime_s_per_game=7920,
                analyzer_timeout=900,
                concurrency=28,
                max_actions_per_game=None,
                save_request_logs=False,
            )
        )
        target = SimpleNamespace(max_runtime_s=PRODUCTION_NOTEBOOK_BUDGET_S)
        mode = apply_solver_settings(bm, target, true_submission=False)
        self.assertEqual(mode, MODE_KAGGLE_SMOKE)
        self.assertLess(bm.solver.max_runtime_s_per_game, 300)
        self.assertEqual(bm.solver.max_actions_per_game, SMOKE_MAX_ACTIONS_PER_GAME)
        self.assertEqual(bm.solver.concurrency, 2)
        ids = select_offline_game_ids(PUBLIC_IDS, mode=mode)
        self.assertEqual(len(ids), SMOKE_GAME_COUNT)
        self.assertEqual(ids, list(PUBLIC_IDS[:2]))
        self.assertFalse(should_run_public25_audit(mode))

    def test_offline_eval_keeps_full_audit(self):
        mode = phase_a_mode(true_submission=False, offline_eval=True)
        self.assertEqual(mode, MODE_OFFLINE_EVAL)
        self.assertTrue(should_run_public25_audit(mode))
        bm = SimpleNamespace(
            solver=SimpleNamespace(
                max_runtime_s_per_game=0,
                analyzer_timeout=0,
                concurrency=0,
                max_actions_per_game=1,
                save_request_logs=True,
            )
        )
        target = SimpleNamespace(max_runtime_s=PRODUCTION_NOTEBOOK_BUDGET_S)
        apply_solver_settings(bm, target, true_submission=False, offline_eval=True)
        self.assertEqual(bm.solver.concurrency, PRODUCTION_CONCURRENCY)

    def test_empty_actions_are_rejected(self):
        with self.assertRaises(RuntimeError):
            require_model_actions(0, mode=MODE_KAGGLE_SMOKE)


def _board(interior: int, hud: int = 9, rows: int = 6, cols: int = 4) -> list[list[int]]:
    grid = [[hud] * cols for _ in range(2)]
    grid.extend([[interior] * cols for _ in range(rows - 2)])
    return grid


class SemanticNoImpactTests(unittest.TestCase):
    def setUp(self):
        set_hud_bottom_rows(0)

    def tearDown(self):
        set_hud_bottom_rows(0)

    def test_identical_and_hud_only_and_real_change(self):
        base = _board(1, hud=1)
        hud = _board(1, hud=7)
        moved = _board(2, hud=1)
        self.assertEqual(classify_transition(base, base), "identical")
        self.assertEqual(classify_transition(base, hud), "hud_only")
        self.assertEqual(classify_transition(base, moved), "real_change")
        self.assertEqual(semantic_key(base), semantic_key(hud))
        self.assertNotEqual(semantic_key(base), semantic_key(moved))

    def test_confirms_after_repeat_and_does_not_globally_ban(self):
        book = NoImpactBook(confirm_repeats=2)
        state = semantic_key(_board(1))
        other = semantic_key(_board(3))
        self.assertFalse(book.observe(state, "ACTION1", "hud_only"))
        self.assertTrue(book.observe(state, "ACTION1", "identical"))
        self.assertTrue(book.is_no_impact(state, "ACTION1"))
        self.assertFalse(book.is_no_impact(state, "ACTION2"))
        self.assertFalse(book.is_no_impact(other, "ACTION1"))

    def test_real_change_clears_the_pair(self):
        book = NoImpactBook(confirm_repeats=2)
        state = semantic_key(_board(1))
        book.observe(state, "ACTION1", "hud_only")
        book.observe(state, "ACTION1", "real_change")
        self.assertFalse(book.is_no_impact(state, "ACTION1"))
        self.assertFalse(book.observe(state, "ACTION1", "hud_only"))

    def test_wrapper_injects_note_and_skips_original_ban(self):
        book = NoImpactBook(confirm_repeats=2)
        grids = [
            _board(1, hud=1),
            _board(1, hud=2),
            _board(1, hud=3),
            _board(1, hud=4),
        ]

        def load(_path):
            return grids.pop(0)

        def original(self, state_path, arguments):
            self._last_step_summary = {
                "executed_actions": ["ACTION1"],
                "level_transition": False,
            }
            return "ok"

        wrapped = wrap_run_python_tool(original, book=book, load_grid=load)
        agent = SimpleNamespace(_summarized_knowledge={}, _last_step_summary={})
        wrapped(agent, "state", {"code": "action(['ACTION1'])"})
        wrapped(agent, "state", {"code": "action(['ACTION1'])"})
        note = agent._summarized_knowledge.get("recent_findings", "")
        self.assertIn("No-impact memory", note)
        self.assertIn("ACTION1", note)
        self.assertNotIn("ban all", note.lower())

    def test_inject_does_not_duplicate(self):
        knowledge = {"recent_findings": ""}
        notes = ["ACTION1 is confirmed no-impact in this semantic state (HUD/timer-only or identical interior); try a different action."]
        inject_no_impact_notes(knowledge, notes)
        inject_no_impact_notes(knowledge, notes)
        self.assertEqual(knowledge["recent_findings"].count("No-impact memory"), 1)

    def test_outer_hud_treats_bottom_strip_as_hud_only(self):
        def board(*, interior: int, top: int = 1, bottom: int = 8) -> list[list[int]]:
            grid = [[top] * 4 for _ in range(2)]
            grid.extend([[interior] * 4 for _ in range(4)])
            grid.extend([[bottom] * 4 for _ in range(2)])
            return grid

        base = board(interior=1, bottom=8)
        bottom_only = board(interior=1, bottom=3)
        moved = board(interior=2, bottom=8)
        self.assertEqual(classify_transition(base, bottom_only), "real_change")
        set_hud_bottom_rows(2)
        self.assertEqual(classify_transition(base, bottom_only), "hud_only")
        self.assertEqual(classify_transition(base, moved), "real_change")
        self.assertEqual(semantic_key(base), semantic_key(bottom_only))
        self.assertNotEqual(semantic_key(base), semantic_key(moved))

    def test_install_kwarg_does_not_shadow_bottom_getter(self):
        from src.s4_semantic_no_impact import current_hud_bottom_rows

        def install_like(*, hud_bottom_rows: int = 0) -> int:
            set_hud_bottom_rows(hud_bottom_rows)
            return current_hud_bottom_rows()

        self.assertEqual(install_like(hud_bottom_rows=2), 2)
        self.assertEqual(current_hud_bottom_rows(), 2)


class EvalPanelTests(unittest.TestCase):
    def test_panels_partition_the_public_set(self):
        panels = json.loads((ROOT / "src" / "eval_panels.json").read_text(encoding="utf-8"))
        public = (
            panels["development"] + panels["validation"] + panels["held_public"]
        )
        self.assertEqual(len(panels["development"]), 8)
        self.assertEqual(len(panels["validation"]), 8)
        self.assertEqual(len(panels["held_public"]), 9)
        self.assertEqual(len(public), 25)
        self.assertEqual(len(set(public)), 25)
        self.assertEqual(panels["seeds"], [101, 202, 303])


class NotebookProseTests(unittest.TestCase):
    def test_rewrite_replaces_tufa_first_person(self):
        from src.notebook_prose import rewrite_markdown_cells

        nb = {
            "cells": [
                {
                    "cell_type": "markdown",
                    "source": [
                        "## About this fork\n",
                        "\n",
                        "My changes are limited to model serving and performance:\n",
                    ],
                },
                {
                    "cell_type": "markdown",
                    "source": [
                        "# Tufa Labs ARC3 submission\n",
                        "\n",
                        "Note: this notebook is a more readable version of the notebook that scored our milestone-winning 1.21; unfortunately, we haven't had the same lucky result with this one.\n",
                    ],
                },
            ]
        }
        rewrite_markdown_cells(nb)
        text = joined_markdown(nb)
        assert_our_prose(text)
        for blob in FORBIDDEN_FOREIGN_FIRST_PERSON:
            self.assertNotIn(blob, text)


class NotebookSyncTests(unittest.TestCase):
    def test_s4_notebook_has_smoke_and_s4_without_s1_s2_s3(self):
        notebook = (
            ROOT
            / "tmp"
            / "kernels"
            / "s4-no-impact"
            / "duck-qwen3-8-flash-next-nvfp4-mtp.ipynb"
        )
        if not notebook.is_file():
            self.skipTest("S4 notebook is not present")
        p0 = (ROOT / "src" / "p0_phase_a_modes.py").read_text(encoding="utf-8")
        nb = json.loads(notebook.read_text(encoding="utf-8"))
        joined = "\n".join(
            "".join(cell.get("source") or [])
            if isinstance(cell.get("source"), list)
            else str(cell.get("source") or "")
            for cell in nb["cells"]
        )
        self.assertIn(p0.strip(), joined)
        self.assertIn("PHASE_A_MODE", joined)
        self.assertIn("install_s4_hooks", joined)
        self.assertNotIn("install_s1_hooks", joined)
        self.assertNotIn("install_s2_hooks", joined)
        self.assertNotIn("install_s3_hooks", joined)
        meta = json.loads(
            (notebook.parent / "kernel-metadata.json").read_text(encoding="utf-8")
        )
        self.assertFalse(meta.get("enable_internet"))
        self.assertEqual(meta.get("machine_shape"), "NvidiaRtxPro6000")


class NotebookS4bTests(unittest.TestCase):
    def test_s4b_notebook_has_outer_hud_and_our_prose(self):
        notebook = (
            ROOT
            / "tmp"
            / "kernels"
            / "s4b-outer2"
            / "duck-qwen3-8-flash-next-nvfp4-mtp.ipynb"
        )
        if not notebook.is_file():
            self.skipTest("S4b notebook is not present")
        p0 = (ROOT / "src" / "p0_phase_a_modes.py").read_text(encoding="utf-8")
        s4 = (ROOT / "src" / "s4_semantic_no_impact.py").read_text(encoding="utf-8")
        nb = json.loads(notebook.read_text(encoding="utf-8"))
        joined = "\n".join(
            "".join(cell.get("source") or [])
            if isinstance(cell.get("source"), list)
            else str(cell.get("source") or "")
            for cell in nb["cells"]
        )
        self.assertIn(p0.strip(), joined)
        self.assertIn(s4.strip(), joined)
        self.assertIn("hud_bottom_rows=2", joined)
        self.assertIn("S4B_OUTER_HUD", joined)
        self.assertIn("install_s4_hooks", joined)
        self.assertNotIn("install_s1_hooks", joined)
        self.assertNotIn("install_s2_hooks", joined)
        self.assertNotIn("install_s3_hooks", joined)
        assert_our_prose(joined_markdown(nb))
        for blob in FORBIDDEN_FOREIGN_FIRST_PERSON:
            self.assertNotIn(blob, joined)
        meta = json.loads(
            (notebook.parent / "kernel-metadata.json").read_text(encoding="utf-8")
        )
        self.assertEqual(meta.get("id"), "dmitriigluzdov/arc-agi-3-s4b-outer-hud-no-impact-flash-nvfp4")
        self.assertTrue(meta.get("is_private"))
        self.assertFalse(meta.get("enable_internet"))
        self.assertEqual(meta.get("machine_shape"), "NvidiaRtxPro6000")
        self.assertIn("S4b", meta.get("title", ""))


if __name__ == "__main__":
    unittest.main()
