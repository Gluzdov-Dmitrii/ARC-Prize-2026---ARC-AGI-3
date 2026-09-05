"""Unit tests for S1 per-game seed injection and telemetry."""

from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.s1_deterministic_control import (
    S1_SEED_NAMESPACE,
    bind_game,
    build_initial_telemetry,
    clear_game,
    current_game_seed,
    game_id_from,
    per_game_seed,
    wrap_build_chat_payload,
    wrap_play_one,
)


def _vllm_build_chat_payload(*, seed=None, **kwargs):
    payload = {"model": kwargs.get("model", "dummy"), "stream": False}
    if seed is not None and seed >= 0:
        payload["seed"] = seed
    return payload


class PerGameSeedTests(unittest.TestCase):
    def test_seed_is_non_negative_and_stable(self):
        first = per_game_seed("tn36-ef4dde99")
        second = per_game_seed("tn36-ef4dde99")
        self.assertEqual(first, second)
        self.assertGreaterEqual(first, 0)
        self.assertLess(first, 2**32)

    def test_different_games_get_different_seeds(self):
        a = per_game_seed("tn36-ef4dde99")
        b = per_game_seed("lf52-271a04aa")
        self.assertNotEqual(a, b)

    def test_namespace_changes_seed(self):
        self.assertNotEqual(
            per_game_seed("tn36-ef4dde99"),
            per_game_seed("tn36-ef4dde99", namespace="other"),
        )
        self.assertEqual(S1_SEED_NAMESPACE, "arc-agi-3-s1-v1")

    def test_seed_minus_one_is_replaced_in_payload(self):
        wrapped = wrap_build_chat_payload(_vllm_build_chat_payload)
        bind_game("ls20-9607627b")
        try:
            unseeded = _vllm_build_chat_payload(seed=-1)
            seeded = wrapped(seed=-1, model="Qwen/Qwen3.8-Flash-Next-NVFP4")
        finally:
            clear_game()
        self.assertNotIn("seed", unseeded)
        self.assertEqual(seeded["seed"], per_game_seed("ls20-9607627b"))
        self.assertGreaterEqual(seeded["seed"], 0)

    def test_without_bound_game_original_seed_is_kept(self):
        wrapped = wrap_build_chat_payload(_vllm_build_chat_payload)
        clear_game()
        self.assertNotIn("seed", wrapped(seed=-1))
        self.assertEqual(wrapped(seed=7)["seed"], 7)

    def test_threads_do_not_leak_seeds(self):
        wrapped = wrap_build_chat_payload(_vllm_build_chat_payload)
        game_ids = [f"game-{i:02d}" for i in range(16)]
        barrier = threading.Barrier(len(game_ids))

        def worker(game_id: str) -> tuple[str, int, int]:
            bind_game(game_id)
            try:
                barrier.wait(timeout=5)
                payload = wrapped(seed=-1)
                return game_id, payload["seed"], current_game_seed()
            finally:
                clear_game()

        with ThreadPoolExecutor(max_workers=len(game_ids)) as pool:
            results = list(pool.map(worker, game_ids))
        observed = {game_id: seed for game_id, seed, ctx in results}
        self.assertEqual(len(set(observed.values())), len(game_ids))
        for game_id, seed, ctx in results:
            self.assertEqual(seed, per_game_seed(game_id))
            self.assertEqual(seed, ctx)

    def test_play_one_wrapper_binds_and_clears(self):
        seen: dict[str, int | None] = {}

        def original(self, game, index, pass_index, local_server=None):
            seen["during"] = current_game_seed()
            seen["game_id"] = game.game_run.game_id

        wrapped = wrap_play_one(original)
        game = SimpleNamespace(game_run=SimpleNamespace(game_id="vc33-5430563c"))
        wrapped(object(), game, 3, 0, None)
        self.assertEqual(seen["game_id"], "vc33-5430563c")
        self.assertEqual(seen["during"], per_game_seed("vc33-5430563c"))
        self.assertIsNone(current_game_seed())

    def test_game_id_fallback(self):
        self.assertEqual(
            game_id_from(SimpleNamespace(env_name="bp35-0a0ad940"), 9),
            "bp35-0a0ad940",
        )
        self.assertEqual(game_id_from(SimpleNamespace(), 9), "9")

    def test_telemetry_is_read_only_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            working = Path(tmp)
            bundle = working / "bundle"
            bundle.mkdir()
            (bundle / "setup_commands.json").write_text('["true"]\n', encoding="utf-8")
            bm = SimpleNamespace(
                n_passes=1,
                solver=SimpleNamespace(
                    max_runtime_s_per_game=7920.0,
                    analyzer_timeout=900.0,
                    concurrency=28,
                    max_actions_per_game=None,
                    save_request_logs=False,
                    label="HarnessSolver",
                    model="local",
                ),
            )
            payload = build_initial_telemetry(
                bm=bm,
                target=SimpleNamespace(max_runtime_s=32400.0),
                working_dir=working,
                bundle_dir=bundle,
                extra={"parent_kernel_version": 3},
                source_text="demo",
            )
            self.assertEqual(payload["experiment_id"], "S1")
            self.assertTrue(payload["read_only_telemetry"])
            self.assertTrue(payload["policy_unchanged"])
            self.assertEqual(payload["solver"]["concurrency"], 28)
            self.assertEqual(payload["extra"]["parent_kernel_version"], 3)
            self.assertIsNotNone(payload["bundle_hashes"]["setup_commands.json"])
            self.assertIsNone(payload["runtime_seconds"])


class NotebookSyncTests(unittest.TestCase):
    def test_notebook_embeds_current_s1_source(self):
        source = (ROOT / "src" / "s1_deterministic_control.py").read_text(
            encoding="utf-8"
        )
        notebook = ROOT / "tmp" / "kernels" / "s1-deterministic" / (
            "duck-qwen3-8-flash-next-nvfp4-mtp.ipynb"
        )
        if not notebook.is_file():
            self.skipTest("S1 notebook is not present")
        import json

        nb = json.loads(notebook.read_text(encoding="utf-8"))
        joined = "\n".join(
            "".join(cell.get("source") or [])
            if isinstance(cell.get("source"), list)
            else str(cell.get("source") or "")
            for cell in nb["cells"]
        )
        self.assertIn("S1 deterministic control", joined)
        self.assertIn(S1_SEED_NAMESPACE, joined)
        self.assertIn(source.strip(), joined)
        public_settings = joined.count("bm.solver.concurrency = 28")
        self.assertGreaterEqual(public_settings, 1)


if __name__ == "__main__":
    unittest.main()
