"""S10 regressions through actual harness methods, with a deterministic engine.

AST extraction executes checked-in exact ToolAgent and HarnessGameSession excerpts
without importing remote model/engine dependencies. Only sandbox transport,
rendering/logging, and the game engine are replaced; action normalization,
execution/batch aggregation, compact results, summary freshness, and runtime
serialization are the original harness implementations. Fixtures and source
hashes live in tests/fixtures/duck_s4_contract; core tests need no tmp/ bundle.
"""
from __future__ import annotations

import ast
import asyncio
from enum import IntEnum
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests/fixtures/duck_s4_contract"
OPTIONAL_HARNESS_BUNDLE = ROOT / "tmp/src/duck-harness/ARC3-Inference"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import s10_scoped_no_impact as s10


def extract_class(path, class_name, methods, namespace):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    original = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                    and node.name == class_name)
    selected = [node for node in original.body if isinstance(node, ast.FunctionDef)
                and node.name in methods]
    if {node.name for node in selected} != set(methods):
        raise AssertionError(f"Harness methods missing in {path}")
    node = ast.ClassDef(name=class_name, bases=[], keywords=[], body=selected,
                        decorator_list=[])
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), node], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(path), "exec"), namespace)
    return namespace[class_name]


class Action(IntEnum):
    RESET = 0
    ACTION1 = 1
    ACTION2 = 2
    ACTION3 = 3
    ACTION4 = 4
    ACTION5 = 5
    ACTION6 = 6

    @classmethod
    def from_name(cls, value):
        return cls[value]

    @classmethod
    def from_id(cls, value):
        return cls(value)


class GameState(IntEnum):
    NOT_FINISHED = 0
    WIN = 1
    GAME_OVER = 2


ACTION_NAMES = dict(UP="ACTION1", DOWN="ACTION2", LEFT="ACTION3", RIGHT="ACTION4",
                    SPACE="ACTION5", MOUSE="ACTION6", RESET="RESET")
MODEL_NAMES = {value: key for key, value in ACTION_NAMES.items()}


def display(name, data=None):
    if name == "ACTION6":
        return f"MOUSE(row={(data or {}).get('y', 0)}, col={(data or {}).get('x', 0)})"
    return MODEL_NAMES.get(name, name)


def sandbox(**kwargs):
    """Run tiny local test snippets while honoring the real IPC result shape."""
    results = []

    def action(actions):
        response = kwargs["action_handler"](actions)
        results.append(response["action_result"])
        return response["action_result"]

    error = ""
    try:
        exec(kwargs["code"], {"action": action})
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    return {"action_results": results, "error": error}


def harness_classes():
    runtime = {"__name__": __name__, "format_grid_ascii": lambda grid: str(grid)}
    tree = ast.parse((FIXTURE_ROOT / "runtime_state.py").read_text(encoding="utf-8"))
    tree.body = [node for node in tree.body if not (
        isinstance(node, ast.ImportFrom) and (node.module or "").startswith("inference"))]
    exec(compile(tree, "runtime_state.py", "exec"), runtime)
    Frame, HistoryEntry = runtime["Frame"], runtime["HistoryEntry"]
    namespace = {
        "__name__": __name__, "json": json,
        "load_runtime_state": runtime["load_runtime_state"],
        "_empty_world_model": lambda: {"recent_findings": "model fact", "cross_level_notes": "persistent model fact"},
        "_normalize_valid_actions": lambda values: values,
        "_ascii_frame_view_payload": lambda frame: {} if frame is None else {"step": frame.step, "level": frame.level},
        "_ascii_history_view_payload": lambda history: [],
        "_terminal_action_reason": lambda payload: next((key for key in ("run_complete", "game_over", "level_completed") if payload.get(key)), None),
        "_terminal_action_stop_detail": lambda reason: reason,
        "run_sandboxed_python": sandbox,
        "_ToolDispatchResult": lambda text, step_executed=False: SimpleNamespace(text=text, step_executed=step_executed),
    }
    methods = ["_ensure_session", "_normalize_python_actions", "_compact_action_result",
               "_run_python_tool", "_summarize_step_sequence",
               "_update_summarized_knowledge_from_step_summary", "_summarized_knowledge_lines"]
    Agent = extract_class(FIXTURE_ROOT / "tool_agent_contract.py", "ToolAgent", methods, namespace)
    Agent._render_tool_payload = lambda self, payload, **kwargs: json.dumps(payload)
    engine = SimpleNamespace(GameAction=Action, GameState=GameState,
                             ActionInput=lambda **kwargs: SimpleNamespace(**kwargs))
    session_namespace = {
        "__name__": __name__, "arcengine": engine, "Frame": Frame, "HistoryEntry": HistoryEntry,
        "write_runtime_state": runtime["write_runtime_state"],
        "to_engine_action": lambda value: ACTION_NAMES.get(str(value).upper()),
        "to_model_actions": lambda values: [MODEL_NAMES.get(v, v) for v in values],
        "_format_action_display": display,
        "_engine_action_names": lambda game: [Action(v).name for v in game.current_state.available_actions],
        "_grid_from_state": lambda state: state.frame.data,
        "_level_number": lambda game: game.current_state.levels_completed + 1,
        "_is_engine_game_over": lambda game: game.current_state.raw.state in (GameState.WIN, GameState.GAME_OVER),
        "_analyzer_reported_tokens": lambda agent: 0,
        "_model_mouse_action_data": lambda data: {"row": data["y"], "col": data["x"]},
    }
    Session = extract_class(FIXTURE_ROOT / "harness_session_contract.py", "_HarnessGameSession",
                            ["step_env", "_normalize_actions", "_execute_action", "_error_payload",
                             "_terminal_payload", "current_frame", "write_runtime_state", "action_count"],
                            session_namespace)
    Session.should_stop = lambda self: False
    Session.timing_payload = lambda self: {}
    Session.write_viewer_payload = lambda self: None
    Session._append_action_viewer_event = lambda *args: None
    return Agent, Session, runtime


class FakeGame:
    def __init__(self):
        self.position = 1
        self.hud = 0
        self.movable = False
        self.next_level = False
        self.number_of_levels = 3
        self.game_run = SimpleNamespace(history=[])
        self.current_state = self.state()

    def state(self, level=1):
        grid = ((self.hud, 0, 0, 0), (0, 0, 0, 0),
                tuple(int(i == self.position) for i in range(4)), (0, 0, 0, 0))
        return SimpleNamespace(frame=SimpleNamespace(data=grid), levels_completed=level - 1,
                               just_won_level=False, raw=SimpleNamespace(state=GameState.NOT_FINISHED),
                               available_actions=list(range(7)))

    def execute_action(self, action, **kwargs):
        level = self.current_state.levels_completed + 1
        self.game_run.history.append(action)
        if self.movable and action.id in (Action.ACTION3, Action.ACTION4):
            self.position += -1 if action.id == Action.ACTION3 else 1
            self.position = max(0, min(3, self.position))
        self.hud = 1 - self.hud
        self.current_state = self.state(level + int(self.next_level))
        self.current_state.just_won_level = self.next_level
        self.next_level = False
        return self.current_state


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="s10_")
        self.addCleanup(self.temp.cleanup)
        self.Agent, self.Session, self.runtime = harness_classes()
        s10.validate_hook_contract(self.Agent)
        self.Agent._ensure_session = s10.wrap_ensure_session(self.Agent._ensure_session)
        self.Agent._summarized_knowledge_lines = s10.wrap_knowledge_lines(self.Agent._summarized_knowledge_lines)
        self.Agent._run_python_tool = s10.wrap_run_python_tool(self.Agent._run_python_tool)
        self.agent, self.session = self.make_game("game_a")

    def make_game(self, name, agent=None):
        if agent is None:
            agent = self.Agent()
            agent._session_runtime_dir = None
            agent._last_step_summary = None
            agent._last_action_result = None
            agent._python_timeout = 2
            agent._current_valid_actions = list(ACTION_NAMES)
        session = self.Session()
        session.state_path = Path(self.temp.name) / (name + ".json")
        session.game = FakeGame()
        session.analyzer = agent
        session.token_baseline = 0
        session.history_entries = [self.runtime["HistoryEntry"](action="", frame=session.current_frame())]
        session.write_runtime_state()
        return agent, session

    def run_code(self, code, agent=None, session=None):
        agent = self.agent if agent is None else agent
        session = self.session if session is None else session
        agent._step_env_callback = session.step_env
        return agent._run_python_tool(session.state_path, {"code": code})

    def rendered(self, agent=None):
        return "\n".join((agent or self.agent)._summarized_knowledge_lines())

    def current_book(self, agent=None, session=None):
        agent, session = agent or self.agent, session or self.session
        return s10.memory_for(agent).paths[str(session.state_path.resolve())]["book"]

    def confirm_left(self):
        self.run_code("action('LEFT')")
        self.run_code("action('LEFT')")
        self.assertIn("LEFT is confirmed no-impact", self.rendered())

    def test_single_primitive_hud_repeat_and_no_model_knowledge_pollution(self):
        self.run_code("action('LEFT')")
        self.assertNotIn("No-impact memory:", self.rendered())
        knowledge = dict(self.agent._summarized_knowledge)
        self.run_code("action('LEFT')")
        self.assertIn("LEFT is confirmed no-impact", self.rendered())
        self.assertEqual(self.agent._summarized_knowledge, knowledge)
        self.assertIn("model fact", self.rendered())

    def test_no_action_and_syntax_error_cannot_reuse_stale_summary(self):
        self.run_code("action('LEFT')")
        original_summary = self.agent._last_step_summary
        for code in ("x = 1", "", "for :", "raise ValueError('no action')"):
            self.assertFalse(self.run_code(code).step_executed)
            self.assertIs(self.agent._last_step_summary, original_summary)
            self.assertNotIn("No-impact memory:", self.rendered())
        self.assertEqual(list(self.current_book()._counts.values()), [1])

    def test_net_zero_batch_and_separate_action_commands_do_not_blame_right(self):
        self.session.game.movable = True
        for code in ("action(['LEFT', 'RIGHT'])", "action('LEFT'); action('RIGHT')"):
            for _ in range(3):
                result = self.run_code(code)
                self.assertTrue(result.step_executed)
                self.assertEqual(self.agent._last_step_summary["executed_count"], 2)
                self.assertEqual(self.session.game.position, 1)
            self.assertEqual(len(self.current_book()._counts), 0)
            self.assertNotIn("No-impact memory:", self.rendered())

    def test_stopped_batch_with_one_executed_primitive_is_attributable(self):
        # DOWN is unavailable, so the real step_env loop executes only LEFT.
        self.session.game.current_state.available_actions.remove(Action.ACTION2)
        original_execute = self.session.game.execute_action
        def execute(action, **kwargs):
            state = original_execute(action, **kwargs)
            state.available_actions.remove(Action.ACTION2)
            return state
        self.session.game.execute_action = execute
        self.run_code("action(['LEFT', 'DOWN'])")
        self.run_code("action(['LEFT', 'DOWN'])")
        self.assertEqual(self.agent._last_step_summary["executed_count"], 1)
        self.assertIn("LEFT is confirmed", self.rendered())
        self.assertNotIn("DOWN is confirmed", self.rendered())

    def test_interleaved_agents_and_paths_share_no_counts(self):
        other, other_session = self.make_game("game_b")
        self.run_code("action('LEFT')")
        self.run_code("action('LEFT')", other, other_session)
        self.assertNotIn("No-impact memory:", self.rendered(other))
        self.run_code("action('LEFT')")
        self.assertIn("No-impact memory:", self.rendered())
        self.assertNotIn("No-impact memory:", self.rendered(other))
        _, third = self.make_game("game_c", self.agent)
        self.run_code("action('LEFT')", self.agent, third)
        self.assertNotIn("No-impact memory:", self.rendered())
        self.run_code("x = 1")
        self.assertIn("LEFT is confirmed no-impact", self.rendered())
        self.assertIsNot(self.current_book(), self.current_book(other, other_session))

    def test_mouse_coordinates_do_not_merge(self):
        self.run_code("action({'action': 'MOUSE', 'row': 1, 'col': 2})")
        self.run_code("action({'action': 'MOUSE', 'row': 2, 'col': 1})")
        self.assertNotIn("No-impact memory:", self.rendered())
        self.run_code("action({'action': 'MOUSE', 'row': 1, 'col': 2})")
        self.assertIn("MOUSE(row=1, col=2) is confirmed", self.rendered())
        self.assertNotIn("MOUSE(row=2, col=1) is confirmed", self.rendered())

    def test_real_change_removes_hint_and_invalidates_that_action_pair(self):
        self.confirm_left()
        old_key = s10.load_snapshot(self.session.state_path)["key"]
        self.session.game.movable = True
        self.run_code("action('LEFT')")
        self.assertNotIn("No-impact memory:", self.rendered())
        self.assertFalse(self.current_book().is_no_impact(old_key, "LEFT"))
        self.assertIn("model fact", self.rendered())

    def test_external_state_change_clears_overlay_before_next_prompt(self):
        self.confirm_left()
        self.agent._summarized_knowledge["recent_findings"] = "new model finding"
        self.session.game.position = 3
        self.session.game.current_state = self.session.game.state()
        self.session.write_runtime_state()
        self.agent._ensure_session(self.session.state_path)
        self.assertNotIn("No-impact memory:", self.rendered())
        self.assertIn("new model finding", self.rendered())

    def test_level_transition_resets_even_when_interior_is_identical(self):
        self.confirm_left()
        self.session.game.next_level = True
        self.run_code("action('LEFT')")
        self.assertEqual(len(self.current_book()._counts), 0)
        self.assertNotIn("No-impact memory:", self.rendered())
        self.assertEqual(self.agent._summarized_knowledge["cross_level_notes"], "persistent model fact")
        self.run_code("action('LEFT')")
        self.assertNotIn("No-impact memory:", self.rendered())

    def test_explicit_and_external_reset_clear_memory(self):
        self.confirm_left()
        self.run_code("action('RESET')")
        self.assertEqual(len(self.current_book()._counts), 0)
        self.assertNotIn("No-impact memory:", self.rendered())
        self.confirm_left()
        self.session._execute_action(SimpleNamespace(id=Action.RESET, data={}), batch_index=1, batch_size=1)
        self.agent._ensure_session(self.session.state_path)
        self.assertEqual(len(self.current_book()._counts), 0)
        self.assertNotIn("No-impact memory:", self.rendered())

    def test_step_rewind_and_external_level_change_reset(self):
        self.confirm_left()
        self.session.game.game_run.history.clear()
        self.session.history_entries = []
        self.session.write_runtime_state()
        self.agent._ensure_session(self.session.state_path)
        self.assertEqual(len(self.current_book()._counts), 0)
        self.confirm_left()
        self.session.game.current_state = self.session.game.state(level=2)
        self.session.write_runtime_state()
        self.agent._ensure_session(self.session.state_path)
        self.assertEqual(len(self.current_book()._counts), 0)

    def test_terminal_result_resets(self):
        self.confirm_left()
        execute = self.session.game.execute_action
        def terminal(action, **kwargs):
            state = execute(action, **kwargs)
            state.raw.state = GameState.GAME_OVER
            return state
        self.session.game.execute_action = terminal
        self.run_code("action('LEFT'); action('RIGHT')")
        self.assertEqual(len(self.current_book()._counts), 0)
        self.assertNotIn("No-impact memory:", self.rendered())

    def test_action_then_python_error_preserves_error_and_fresh_action(self):
        for _ in range(2):
            result = self.run_code("action('LEFT'); raise ValueError('original sandbox error')")
            self.assertIn("original sandbox error", result.text)
        self.assertIn("LEFT is confirmed", self.rendered())

    def test_internal_instrumentation_error_does_not_hide_solver_exception(self):
        marker = ValueError("original solver error")
        def broken_loader(path):
            raise OSError("memory reader error")
        def failing_solver(*args):
            raise marker
        wrapped = s10.wrap_run_python_tool(failing_solver, loader=broken_loader)
        with self.assertRaises(ValueError) as raised:
            wrapped(self.agent, self.session.state_path, {})
        self.assertIs(raised.exception, marker)
        self.assertFalse(s10.memory_for(self.agent).in_tool)

    def test_internal_postprocessing_error_preserves_result(self):
        marker = SimpleNamespace(step_executed=False, text="original result")
        wrapped = s10.wrap_run_python_tool(lambda *args: marker,
                                           loader=lambda path: (_ for _ in ()).throw(OSError("bad read")))
        self.assertIs(wrapped(self.agent, self.session.state_path, {}), marker)
        self.assertEqual(s10.memory_for(self.agent).note, "")

    def test_full_imported_tool_agent_with_real_subprocess_sandbox(self):
        bundle = OPTIONAL_HARNESS_BUNDLE
        if not (bundle / "inference/agent/tool_agent.py").is_file():
            self.skipTest("Full extracted harness bundle is not available")
        sys.path.insert(0, str(bundle))
        try:
            from inference.agent.tool_agent import ToolAgent
        finally:
            sys.path.remove(str(bundle))
        class RealAgent(ToolAgent):
            pass
        s10.validate_hook_contract(RealAgent)
        RealAgent._ensure_session = s10.wrap_ensure_session(RealAgent._ensure_session)
        RealAgent._summarized_knowledge_lines = s10.wrap_knowledge_lines(RealAgent._summarized_knowledge_lines)
        RealAgent._run_python_tool = s10.wrap_run_python_tool(RealAgent._run_python_tool)
        self.agent = RealAgent(model="s10-local-contract-test")
        self.session.analyzer = self.agent
        self.assertTrue(self.run_code("action('LEFT')").step_executed)
        prior = self.agent._last_step_summary
        self.assertFalse(self.run_code("x = current_frame.step").step_executed)
        self.assertIs(prior, self.agent._last_step_summary)
        self.assertNotIn("No-impact memory:", self.rendered())
        self.assertTrue(self.run_code("action('LEFT')").step_executed)
        self.assertIn("LEFT is confirmed no-impact", self.rendered())
        self.session.game.movable = True
        before_counts = dict(self.current_book()._counts)
        self.run_code("action(['LEFT', 'RIGHT'])")
        self.run_code("action('LEFT'); action('RIGHT')")
        self.assertEqual(self.agent._last_step_summary["executed_count"], 2)
        self.assertEqual(dict(self.current_book()._counts), before_counts)
        self.run_code("action({'action':'MOUSE', 'row':1, 'col':2})")
        self.run_code("action({'action':'MOUSE', 'row':1, 'col':2})")
        self.assertIn("MOUSE(row=1, col=2) is confirmed", self.rendered())

    def test_memory_and_rendered_advice_are_bounded(self):
        book = s10.NoImpactBook(max_pairs=5)
        for i in range(100):
            for _ in range(3):
                book.observe("state", f"MOUSE(row={i}, col=0)", "identical")
        self.assertEqual(len(book._counts), 5)
        self.assertTrue(all(count == 2 for count in book._counts.values()))
        memory = s10.ScopedMemory(max_paths=2, max_pairs=5)
        snapshot = s10.load_snapshot(self.session.state_path)
        for i in range(100):
            memory.sync(Path(self.temp.name) / f"{i}.json", snapshot)
        self.assertEqual(len(memory.paths), 2)
        big = s10.NoImpactBook()
        for i in range(100):
            big.observe("state", str(i), "identical")
            big.observe("state", str(i), "identical")
        self.assertEqual(len(big.notes_for("state")), s10.MAX_NOTES_PER_STATE)

    def test_unchanged_ensure_calls_read_json_only_once(self):
        original = Path.read_text
        reads = []
        def counted(path, *args, **kwargs):
            if path == self.session.state_path:
                reads.append(path)
            return original(path, *args, **kwargs)
        with patch.object(Path, "read_text", counted):
            for _ in range(10):
                self.agent._ensure_session(self.session.state_path)
        self.assertEqual(len(reads), 1)

    def test_executed_action_forces_read_even_if_file_metadata_is_unchanged(self):
        marker = SimpleNamespace(step_executed=True)
        wrapped = s10.wrap_run_python_tool(lambda *args: marker)
        original = Path.read_text
        reads = []
        def counted(path, *args, **kwargs):
            if path == self.session.state_path:
                reads.append(path)
            return original(path, *args, **kwargs)
        with patch.object(Path, "read_text", counted):
            wrapped(self.agent, self.session.state_path, {})
            self.assertEqual(len(reads), 2)
            wrapped(self.agent, self.session.state_path, {})
            self.assertEqual(len(reads), 3)
            no_action = s10.wrap_run_python_tool(lambda *args: SimpleNamespace(step_executed=False))
            no_action(self.agent, self.session.state_path, {})
            self.assertEqual(len(reads), 3)

    def test_atomic_replacement_refreshes_identical_size_and_mtime(self):
        self.confirm_left()
        path = self.session.state_path
        before = path.stat()
        replacement = path.with_suffix(".replacement")
        replacement.write_text(path.read_text(encoding="utf-8").replace('"level": 1', '"level": 2'),
                               encoding="utf-8")
        os.utime(replacement, ns=(before.st_atime_ns, before.st_mtime_ns))
        replacement.replace(path)
        after = path.stat()
        self.assertEqual(before.st_size, after.st_size)
        self.assertEqual(before.st_mtime_ns, after.st_mtime_ns)
        self.agent._ensure_session(path)
        memory = s10.memory_for(self.agent)
        self.assertEqual(memory.paths[str(path.resolve())]["snapshot"]["level"], 2)
        self.assertEqual(len(self.current_book()._counts), 0)
        self.assertNotIn("No-impact memory:", self.rendered())

    def test_missing_or_invalid_file_evicts_cached_snapshot(self):
        self.confirm_left()
        path = self.session.state_path
        saved = path.read_bytes()
        path.unlink()
        self.agent._ensure_session(path)
        self.assertEqual(len(s10.memory_for(self.agent).paths), 0)
        self.assertNotIn("No-impact memory:", self.rendered())
        path.write_bytes(saved)
        self.agent._ensure_session(path)
        self.assertEqual(len(s10.memory_for(self.agent).paths), 1)
        path.write_text("not json", encoding="utf-8")
        self.agent._ensure_session(path)
        self.assertEqual(len(s10.memory_for(self.agent).paths), 0)

    def test_cached_snapshots_are_bounded_and_path_scoped(self):
        memory = s10.ScopedMemory(max_paths=2)
        saved = self.session.state_path.read_bytes()
        for i in range(6):
            path = Path(self.temp.name) / f"cache_{i}.json"
            path.write_bytes(saved)
            memory.refresh(path)
        self.assertEqual(len(memory.paths), 2)
        self.assertTrue(all("cache_signature" in scope for scope in memory.paths.values()))
        self.assertTrue(all("history" not in scope["snapshot"] for scope in memory.paths.values()))
        self.assertTrue(all("grid" in scope["snapshot"] for scope in memory.paths.values()))

    def test_custom_loader_bypasses_file_cache_and_supports_missing_paths(self):
        memory = s10.ScopedMemory()
        snapshot = s10.load_snapshot(self.session.state_path)
        calls = []
        def loader(path):
            calls.append(path)
            return dict(snapshot, level=len(calls))
        path = Path(self.temp.name) / "virtual_state.json"
        first, _ = memory.refresh(path, loader=loader)
        second, _ = memory.refresh(path, loader=loader)
        self.assertEqual((first["level"], second["level"]), (1, 2))
        self.assertEqual(len(calls), 2)
        self.assertNotIn("cache_signature", memory.paths[str(path.resolve())])

    def test_install_contract_idempotency_and_telemetry_without_budget_changes(self):
        async def run():
            return "done"
        bm = SimpleNamespace(run=run, solver=SimpleNamespace(concurrency=28, max_runtime_s_per_game=7920))
        target = SimpleNamespace(max_runtime_s=28800)
        modules = {"inference": ModuleType("inference"), "inference.agent": ModuleType("inference.agent"),
                   "inference.agent.tool_agent": ModuleType("inference.agent.tool_agent")}
        modules["inference.agent.tool_agent"].ToolAgent = self.Agent
        with patch.dict(sys.modules, modules):
            s10.install_s10_hooks(bm, target, working_dir=Path(self.temp.name))
            first = self.Agent._run_python_tool
            s10.install_s10_hooks(bm, target, working_dir=Path(self.temp.name))
            self.assertIs(first, self.Agent._run_python_tool)
            self.assertEqual(asyncio.run(bm.run()), "done")
        self.assertEqual(bm.solver.concurrency, 28)
        self.assertEqual(bm.solver.max_runtime_s_per_game, 7920)
        self.assertEqual(target.max_runtime_s, 28800)
        payload = json.loads((Path(self.temp.name) / s10.S10_TELEMETRY_NAME).read_text())
        self.assertFalse(payload["global_ban"])
        self.assertEqual(payload["hud_top_rows"], 2)
        self.assertIn("runtime_seconds", payload)
        with self.assertRaisesRegex(RuntimeError, "missing callable"):
            s10.validate_hook_contract(SimpleNamespace())


class FixtureIntegrityTests(unittest.TestCase):
    def test_checked_in_fixtures_match_original_source_slice_hashes(self):
        manifest = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
        self.assertIn("Tufa Labs", manifest["upstream"])
        for filename, record in manifest["files"].items():
            with self.subTest(fixture=filename):
                text = (FIXTURE_ROOT / filename).read_text(encoding="utf-8")
                self.assertEqual(hashlib.sha256(text.encode("utf-8")).hexdigest(),
                                 record["fixture_sha256_lf"])
                if "methods" not in record:
                    continue
                self.assertIn(record["source_sha256"], text)
                tree = ast.parse(text)
                cls = next(node for node in tree.body if isinstance(node, ast.ClassDef))
                methods = [node for node in cls.body if isinstance(node, ast.FunctionDef)]
                self.assertEqual({node.name for node in methods}, set(record["methods"]))
                lines = text.splitlines(keepends=True)
                for node in methods:
                    start = min([node.lineno, *[d.lineno for d in node.decorator_list]])
                    snippet = "".join(lines[start - 1:node.end_lineno])
                    self.assertEqual(hashlib.sha256(snippet.encode("utf-8")).hexdigest(),
                                     record["methods"][node.name]["sha256_lf"])


class HelperTests(unittest.TestCase):
    def test_top_two_rows_only_and_bottom_is_real(self):
        before = [[0, 0] for _ in range(5)]
        after = [row[:] for row in before]
        after[0][0] = 1
        after[1][1] = 2
        self.assertEqual(s10.classify_transition(before, after), "hud_only")
        after[-1][0] = 3
        self.assertEqual(s10.classify_transition(before, after), "real_change")

    def test_unverified_action_span_is_rejected(self):
        before = {"step": 1}
        after = {"step": 2, "level": 1, "last_action_step": 2, "last_action": "LEFT"}
        summary = {"executed_count": 1, "executed_actions": ["LEFT"], "start_action_num": 1,
                   "end_action_num": 1, "level": 1}
        self.assertIsNone(s10.fresh_single_action(SimpleNamespace(step_executed=True), None,
                                                summary, before, after))


if __name__ == "__main__":
    unittest.main()
