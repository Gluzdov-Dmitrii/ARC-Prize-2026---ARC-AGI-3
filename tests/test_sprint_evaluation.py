"""Focused coverage and comparability invariants for TAAF sprint exports."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.sprint_evaluation import build_run_summary, compare_summaries, write_run_summary

CONFIG = {"model": "test/model@revision", "seed": 7, "budgets": {"actions": 20, "seconds": 30}}


def _run(game_id="a", score=0.0, state="gave_up", baselines=True):
    return SimpleNamespace(game_id=game_id, state=state, final_score=score,
                           levels_completed=1, number_of_levels=2,
                           actions_per_level=[2, 0], history=[object(), object()],
                           final_wallclock_seconds=3.0,
                           base_actions_per_level=[4, 4] if baselines else None)


def _benchmark(*runs):
    return SimpleNamespace(n_passes=1, end_time="2026-09-22T00:00:00", game_runs=list(runs))


def _summary(scores=(0.0, 50.0), profile="base", mode="panel", config=None):
    ids = [f"g{i}" for i in range(len(scores))]
    return build_run_summary(_benchmark(*[_run(g, s) for g, s in zip(ids, scores)]),
                             profile, mode, ids, 6.0, CONFIG if config is None else config)


class ExportTests(unittest.TestCase):
    def test_zero_score_retained_and_native_scale_not_rescaled(self):
        summary = _summary((0.0, 80.0))
        self.assertEqual([g["final_score"] for g in summary["games"]], [0.0, 80.0])
        self.assertEqual(summary["mean_score"], 40.0)
        self.assertEqual(summary["score_scale"], "framework-native")
        self.assertEqual(summary["games"][0]["action_count"], 2)
        self.assertEqual(summary["games"][0]["runtime_s"], 3.0)

    def test_missing_game_fails(self):
        with self.assertRaisesRegex(ValueError, "missing=.*b"):
            build_run_summary(_benchmark(_run()), "base", "panel", ["a", "b"], 1, CONFIG)

    def test_duplicate_and_unexpected_games_fail(self):
        for runs, expected, error in (([_run(), _run()], ["a"], "Duplicate"),
                                      ([_run(), _run("b")], ["a"], "unexpected")):
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                build_run_summary(_benchmark(*runs), "base", "panel", expected, 1, CONFIG)

    def test_bad_scores_and_states_fail(self):
        for score in (None, float("nan"), float("inf"), True):
            with self.subTest(score=score), self.assertRaises(ValueError):
                build_run_summary(_benchmark(_run(score=score)), "base", "panel", ["a"], 1, CONFIG)
        for state in ("crashed", "playing", "not_started"):
            with self.subTest(state=state), self.assertRaisesRegex(ValueError, "state"):
                build_run_summary(_benchmark(_run(state=state)), "base", "panel", ["a"], 1, CONFIG)

    def test_ended_cancelled_run_is_retained(self):
        summary = build_run_summary(_benchmark(_run(state="cancelled")), "base", "panel", ["a"], 1, CONFIG)
        self.assertEqual(summary["games"][0]["final_score"], 0)
        self.assertEqual(summary["games"][0]["state"], "cancelled")

    def test_unfinished_benchmark_or_multiple_passes_fail(self):
        for field, value in (("end_time", None), ("n_passes", 2)):
            bm = _benchmark(_run())
            setattr(bm, field, value)
            with self.subTest(field=field), self.assertRaises(ValueError):
                build_run_summary(bm, "base", "panel", ["a"], 1, CONFIG)

    def test_action_invariant_is_checked(self):
        run = _run()
        run.actions_per_level = [1, 0]
        with self.assertRaisesRegex(ValueError, "counters disagree"):
            build_run_summary(_benchmark(run), "base", "panel", ["a"], 1, CONFIG)

    def test_export_roundtrip_and_config_snapshot(self):
        config = copy.deepcopy(CONFIG)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "summary.json"
            summary = write_run_summary(_benchmark(_run()), path, profile="base", mode="panel",
                                        expected_game_ids=["a"], elapsed_s=1, config=config)
            self.assertEqual(json.loads(path.read_text()), summary)
            self.assertFalse(path.with_name("summary.json.tmp").exists())
        config["budgets"]["actions"] = 999
        self.assertEqual(summary["config"]["budgets"]["actions"], 20)


class ComparisonTests(unittest.TestCase):
    def test_equivalent_scores_are_ties_with_zero_interval(self):
        comparison = compare_summaries(_summary(), _summary(profile="candidate"), bootstrap_samples=100)
        self.assertEqual((comparison["wins"], comparison["ties"], comparison["losses"]), (0, 2, 0))
        self.assertEqual(comparison["mean_delta"], 0)
        self.assertEqual(comparison["paired_bootstrap_ci"]["lower"], 0)
        self.assertEqual(comparison["paired_bootstrap_ci"]["upper"], 0)

    def test_pairing_by_id_and_deterministic_bootstrap(self):
        base, candidate = _summary((0, 50, 20)), _summary((20, 50, 10), profile="candidate")
        candidate["games"].reverse()
        comparison = compare_summaries(base, candidate, bootstrap_samples=200, bootstrap_seed=11)
        self.assertEqual(comparison, compare_summaries(base, candidate, bootstrap_samples=200, bootstrap_seed=11))
        self.assertEqual((comparison["wins"], comparison["ties"], comparison["losses"]), (1, 1, 1))
        self.assertAlmostEqual(comparison["mean_delta"], 10 / 3)
        self.assertEqual([g["delta"] for g in comparison["games"]], [20, 0, -10])

    def test_mismatched_config_fails(self):
        for key, value in (("model", "different/model"), ("seed", 8),
                           ("budgets", {"actions": 21, "seconds": 30}), ("serving", "different")):
            config = copy.deepcopy(CONFIG)
            config[key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "config mismatch"):
                compare_summaries(_summary(), _summary(config=config))

    def test_config_without_controls_cannot_be_compared(self):
        with self.assertRaisesRegex(ValueError, "requires config"):
            compare_summaries(_summary(config={}), _summary(config={}))

    def test_stochastic_seed_is_accepted_and_explicit(self):
        for seed in (None, -1):
            config = copy.deepcopy(CONFIG)
            config["seed"] = seed
            comparison = compare_summaries(_summary(config=config), _summary(config=config), bootstrap_samples=10)
            self.assertIn("stochastic unpaired sampling", comparison["pairing"])
            self.assertTrue(any("RNG draws" in item for item in comparison["warnings"]))

    def test_smoke_competition_hidden_baselines_and_mode_mismatch_fail(self):
        for mode in ("smoke", "competition"):
            summary = _summary(mode=mode)
            self.assertFalse(summary["quality_comparison_eligible"])
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                compare_summaries(summary, summary)
        with self.assertRaisesRegex(ValueError, "mode mismatch"):
            compare_summaries(_summary(), _summary(mode="public25"))
        hidden = _summary()
        hidden["games"][0]["baselines_available"] = False
        with self.assertRaisesRegex(ValueError, "hidden baselines"):
            compare_summaries(_summary(), hidden)

    def test_tampered_summary_missing_duplicate_and_nonfinite_fail(self):
        for mutation in (lambda s: s["games"].pop(),
                         lambda s: s["games"].append(s["games"][0]),
                         lambda s: s["games"][0].update(final_score=float("nan"))):
            candidate = _summary()
            mutation(candidate)
            with self.assertRaises(ValueError):
                compare_summaries(_summary(), candidate)
        with self.assertRaisesRegex(ValueError, "game IDs differ"):
            compare_summaries(_summary(), _summary((0,)))

    def test_cli_writes_comparison(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / name for name in ("base.json", "candidate.json", "paired.json")]
            for path, summary in zip(paths, (_summary(), _summary(profile="candidate"))):
                path.write_text(json.dumps(summary), encoding="utf-8")
            proc = subprocess.run([sys.executable, "-m", "src.sprint_evaluation", str(paths[0]), str(paths[1]),
                                   "--output", str(paths[2]), "--bootstrap-samples", "10"],
                                  cwd=ROOT, text=True, capture_output=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(json.loads(paths[2].read_text())["ties"], 2)

    def test_notebook_embedding_does_not_start_cli(self):
        namespace = {"__name__": "__main__"}
        exec((ROOT / "src/sprint_evaluation.py").read_text(encoding="utf-8"), namespace)
        self.assertTrue(callable(namespace["write_run_summary"]))


if __name__ == "__main__":
    unittest.main()
