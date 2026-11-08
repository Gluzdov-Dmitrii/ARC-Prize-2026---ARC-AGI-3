from types import SimpleNamespace
import pytest
from src.sprint_runtime import PRODUCTION, apply_run_config, resolve_run_config, select_offline_ids


def test_hidden_branch_ignores_all_smoke_settings():
    cfg = resolve_run_config(true_submission=True, profile="s10_scoped", offline_mode="smoke",
                             eval_seed=101, panel_seconds=30, panel_actions=1)
    assert cfg["mode"] == "competition" and cfg["seed"] == -1
    assert cfg["budgets"] == PRODUCTION and cfg["panel"] is None
    with pytest.raises(RuntimeError, match="live gateway"):
        select_offline_ids([], {}, cfg)


def test_smoke_caps_do_not_mutate_production():
    cfg = resolve_run_config(true_submission=False, profile="s10_scoped")
    solver = SimpleNamespace(**PRODUCTION)
    bm = SimpleNamespace(solver=solver)
    apply_run_config(bm, SimpleNamespace(max_runtime_s=32400), cfg)
    assert solver.max_actions_per_game == 4 and solver.concurrency == 2
    assert PRODUCTION["max_actions_per_game"] is None
    apply_run_config(bm, SimpleNamespace(max_runtime_s=32400),
                     resolve_run_config(true_submission=True, profile="s10_scoped"))
    assert solver.concurrency == 28 and solver.max_actions_per_game is None


def test_panel_partition_and_selection_are_explicit():
    ids = [f"game{i}" for i in range(25)]
    panels = dict(development=ids[:8], validation=ids[8:16], held_public=ids[16:])
    cfg = resolve_run_config(true_submission=False, profile="s10_scoped", offline_mode="panel")
    assert select_offline_ids(ids, panels, cfg) == ids[8:16]
    panels["held_public"][-1] = ids[0]
    with pytest.raises(RuntimeError, match="partition"):
        select_offline_ids(ids, panels, cfg)


def test_invalid_profile_and_bundle_fail_early():
    with pytest.raises(ValueError):
        resolve_run_config(true_submission=True, profile="typo")
    with pytest.raises(RuntimeError, match="9-hour"):
        apply_run_config(SimpleNamespace(), SimpleNamespace(max_runtime_s=3600), {})
