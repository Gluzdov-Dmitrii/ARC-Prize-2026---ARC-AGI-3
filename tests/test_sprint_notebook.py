"""Execute generated notebook branches with stdlib fakes, without Kaggle/GPU."""

import ast
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from src import sprint_runtime


NOTEBOOK = Path(__file__).resolve().parents[1] / "output/notebooks/arc3_s10_scoped_memory.ipynb"


def notebook_cell(marker):
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    matches = ["".join(cell["source"]) for cell in notebook["cells"]
               if cell["cell_type"] == "code" and marker in "".join(cell["source"])]
    if len(matches) != 1:
        raise AssertionError(f"Expected one generated cell containing {marker!r}, found {len(matches)}")
    return matches[0]


class NotebookGatewaySelectionTests(unittest.TestCase):
    def selection_scope(self, *, hidden):
        ids = [f"public-{i:02d}" for i in range(25)]
        offline_games = [SimpleNamespace(env_name=game_id) for game_id in reversed(ids)]
        gateway_games = [SimpleNamespace(env_name=f"hidden-{i:02d}") for i in range(55)]
        scope = {
            "TRUE_SUBMISSION": hidden,
            "bm": SimpleNamespace(games=[]),
            "os": os,
            "datetime": datetime,
            "timedelta": timedelta,
            "target": SimpleNamespace(max_runtime_s=32400),
            "NOTEBOOK_START_EPOCH": time.time(),
            "COMPETITION_ROOT": Path("/unused-competition-input"),
            "PUBLIC_GAME_IDS": ids,
            "EVAL_PANELS": {"development": ids[:8], "validation": ids[8:16], "held_public": ids[16:]},
            "RUN_CONFIG": sprint_runtime.resolve_run_config(
                true_submission=hidden, profile="s10_scoped", offline_mode="smoke", eval_seed=101),
            "_wait_for_gateway": Mock(),
            "_competition_games": Mock(return_value=gateway_games),
            "_offline_games": Mock(return_value=offline_games),
        }
        return scope, ids, gateway_games

    def execute_selection(self, scope):
        with patch.dict(sys.modules, {"arc3_runtime": sprint_runtime}), \
                patch.dict(os.environ, {}, clear=False), patch("builtins.print"):
            exec(compile(notebook_cell("EXPECTED_GAME_IDS ="), "game-selection-cell", "exec"), scope)

    def test_hidden_run_uses_every_gateway_game_even_with_invalid_public_panel(self):
        scope, _, gateway_games = self.selection_scope(hidden=True)
        # These invalid offline controls must be irrelevant to a competition rerun.
        scope["PUBLIC_GAME_IDS"] = ["smoke-only-1", "smoke-only-2"]
        scope["EVAL_PANELS"] = {}
        scope["_offline_games"].side_effect = AssertionError("Hidden run accessed offline games")
        self.execute_selection(scope)
        self.assertEqual(scope["EXPECTED_GAME_IDS"], [game.env_name for game in gateway_games])
        self.assertEqual(len(scope["bm"].games), 55)
        scope["_competition_games"].assert_called_once_with()
        scope["_wait_for_gateway"].assert_called_once()
        scope["_offline_games"].assert_not_called()

    def test_offline_smoke_keeps_two_pinned_games_and_never_contacts_gateway(self):
        scope, ids, _ = self.selection_scope(hidden=False)
        scope["_competition_games"].side_effect = AssertionError("Smoke contacted gateway")
        self.execute_selection(scope)
        self.assertEqual(scope["EXPECTED_GAME_IDS"], ids[:2])
        scope["_competition_games"].assert_not_called()
        scope["_wait_for_gateway"].assert_not_called()
        scope["_offline_games"].assert_called_once()


class NotebookDiagnosticFailureTests(unittest.TestCase):
    def run_scope(self, directory, *, hidden, manifest_write_fails=False):
        directory = Path(directory)
        (directory / "teardown_commands.json").write_text('["cleanup-owned-server"]', encoding="utf-8")
        events = []

        async def run(**kwargs):
            events.append("played")

        watchdog = ModuleType("vllm_server_watchdog")
        watchdog.load_setup = Mock(return_value=object())
        watchdog.WatchdogConfig = Mock(return_value=object())
        watchdog.start_background = Mock()
        watchdog.stop_background = Mock()
        scope = {
            "BUNDLE_DIR": directory,
            "WORKING_DIR": directory,
            "sys": sys,
            "time": time,
            "json": json,
            "bm": SimpleNamespace(run=run, _save_json=Mock(), game_runs=[]),
            "soft_end": datetime.now() + timedelta(hours=8),
            "target": SimpleNamespace(max_runtime_s=32400),
            "TRUE_SUBMISSION": hidden,
            "PROFILE": "s10_scoped",
            "RUN_CONFIG": {"mode": "competition" if hidden else "smoke"},
            "EXPECTED_GAME_IDS": ["hidden-game" if hidden else "public-game"],
            "EVALUATION_CONFIG": {},
            "write_run_summary": Mock(side_effect=ValueError("invalid final state 'crashed'")),
            "write_manifest": Mock(side_effect=OSError("diagnostic disk failure") if manifest_write_fails else None),
            "subprocess": SimpleNamespace(run=Mock(), TimeoutExpired=subprocess.TimeoutExpired),
            "_command_env": lambda: {},
        }
        return scope, watchdog, events

    def execute_run(self, scope, watchdog):
        source = notebook_cell("run_started = time.monotonic()")
        compiled = compile(source, "run-cell", "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
        with patch.dict(sys.modules, {"vllm_server_watchdog": watchdog}), \
                patch.object(sys, "path", list(sys.path)), patch("builtins.print"):
            asyncio.run(eval(compiled, scope))

    def assert_cleanup(self, scope, watchdog, events):
        self.assertEqual(events, ["played"])
        scope["bm"]._save_json.assert_called_once_with()
        watchdog.stop_background.assert_called_once_with(timeout_seconds=15.0)
        scope["subprocess"].run.assert_called_once()
        self.assertFalse((scope["WORKING_DIR"] / "submission.parquet").exists())

    def test_hidden_diagnostic_schema_failure_preserves_played_result(self):
        with tempfile.TemporaryDirectory() as directory:
            scope, watchdog, events = self.run_scope(directory, hidden=True)
            self.execute_run(scope, watchdog)
            self.assertFalse(scope["summary"]["valid"])
            self.assertIn("crashed", scope["summary"]["diagnostic_error"])
            self.assertEqual(scope["summary"]["games"], [])
            scope["write_manifest"].assert_called_once()
            self.assert_cleanup(scope, watchdog, events)

    def test_hidden_fallback_write_failure_remains_nonfatal(self):
        with tempfile.TemporaryDirectory() as directory:
            scope, watchdog, events = self.run_scope(directory, hidden=True, manifest_write_fails=True)
            self.execute_run(scope, watchdog)
            self.assertFalse(scope["summary"]["valid"])
            self.assert_cleanup(scope, watchdog, events)

    def test_offline_diagnostic_failure_still_fails_validation_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as directory:
            scope, watchdog, events = self.run_scope(directory, hidden=False)
            with self.assertRaisesRegex(ValueError, "invalid final state"):
                self.execute_run(scope, watchdog)
            scope["write_manifest"].assert_not_called()
            self.assert_cleanup(scope, watchdog, events)


if __name__ == "__main__":
    unittest.main()
