"""Build S4 notebook: P0a short Phase A smoke + no-impact guard on champion packaging."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P0_PATH = ROOT / "src" / "p0_phase_a_modes.py"
S4_PATH = ROOT / "src" / "s4_semantic_no_impact.py"
PARENT_NOTEBOOK = (
    ROOT
    / "tmp"
    / "kernels"
    / "s1-deterministic"
    / "duck-qwen3-8-flash-next-nvfp4-mtp.ipynb"
)
PARENT_META = ROOT / "tmp" / "kernels" / "s1-deterministic" / "kernel-metadata.json"
NOTEBOOK_DIR = ROOT / "tmp" / "kernels" / "s4-no-impact"
NOTEBOOK_PATH = NOTEBOOK_DIR / "duck-qwen3-8-flash-next-nvfp4-mtp.ipynb"
S1_MARKER = "# === S1 deterministic control: single causal change ==="
S2_MARKER = "# === S2 memory capture: single causal change ==="
S3_MARKER = "# === S3 cross-level transfer: single causal change ==="
S4_MARKER = "# === S4 semantic no-impact + P0a short Phase A ==="
HOOK_NEEDLE = "bm.solver.concurrency = 28"
RUN_NEEDLE = "def _competition_games():"


def cell_text(cell: dict) -> str:
    source = cell.get("source") or ""
    return "".join(source) if isinstance(source, list) else str(source)


def set_cell_text(cell: dict, text: str) -> None:
    cell["source"] = text.splitlines(keepends=True)
    if cell["source"] and not cell["source"][-1].endswith("\n"):
        cell["source"][-1] += "\n"


def embed(name: str, source: str) -> str:
    if "'''" in source:
        raise RuntimeError(f"{name} contains triple single quotes; refuse to embed")
    return source


def hook_block(p0: str, s4: str) -> str:
    return f'''
{S4_MARKER}
# Packaging: competition rerun keeps production budgets. Offline Save & Run is a
# short smoke. Policy change is S4 no-impact memory only. S1/S2/S3 not stacked.
P0_SOURCE = r\'\'\'{embed("p0", p0)}\'\'\'
S4_SOURCE = r\'\'\'{embed("s4", s4)}\'\'\'
_p0_ns = {{"__name__": "p0_phase_a_modes"}}
_s4_ns = {{"__name__": "s4_semantic_no_impact"}}
exec(P0_SOURCE, _p0_ns)
exec(S4_SOURCE, _s4_ns)
PHASE_A_MODE = _p0_ns["apply_solver_settings"](
    bm, target, true_submission=TRUE_SUBMISSION
)
S4_TELEMETRY = _s4_ns["install_s4_hooks"](
    bm,
    target=target,
    working_dir=WORKING_DIR,
    bundle_dir=BUNDLE_DIR,
    extra={{
        "parent_kernel": "dmitriigluzdov/duck-qwen3-8-flash-next-nvfp4-mtp",
        "parent_kernel_version": 3,
        "parent_submission_ref": 55959595,
        "parent_public_score": 3.39,
        "phase_a_mode": PHASE_A_MODE,
        "true_submission": TRUE_SUBMISSION,
        "vllm_profile": PUBLIC25_VLLM_PROFILE_NAME,
        "vllm_profile_env": PUBLIC25_VLLM_PROFILE_ENV,
    }},
    source_text=S4_SOURCE,
)
print(
    "S4_NO_IMPACT hud-insensitive telemetry="
    + str(_s4_ns["telemetry_path"](WORKING_DIR)),
    flush=True,
)
'''


OLD_SETTINGS = """# Exact public-25 and competition settings.
bm.solver.max_runtime_s_per_game = 7920.0
bm.solver.analyzer_timeout = 900.0
bm.solver.concurrency = 28
bm.solver.max_actions_per_game = None
bm.solver.save_request_logs = False
if float(getattr(target, 'max_runtime_s', 0.0) or 0.0) != 32400.0:
    raise RuntimeError(
        f'Expected the 32400-second notebook budget, got {target.max_runtime_s!r}.'
    )
print(
    f'PUBLIC25_SETTINGS budget_s={bm.solver.max_runtime_s_per_game} '
    f'concurrency={bm.solver.concurrency} analyzer_timeout={bm.solver.analyzer_timeout} '
    f'action_cap={bm.solver.max_actions_per_game} request_logs={bm.solver.save_request_logs}',
    flush=True,
)
"""

OLD_OFFLINE_SELECT = """    bm.games = [offline_by_id[game_id] for game_id in PUBLIC_GAME_IDS]
    if len(bm.games) != 25:
        raise RuntimeError(f'Expected 25 public games, got {len(bm.games)}.')
    print(f'PUBLIC25_SELECTION games={len(bm.games)} passes=1', flush=True)
"""

NEW_OFFLINE_SELECT = """    selected_ids = _p0_ns["select_offline_game_ids"](PUBLIC_GAME_IDS, mode=PHASE_A_MODE)
    bm.games = [offline_by_id[game_id] for game_id in selected_ids]
    print(
        f'OFFLINE_SELECTION mode={PHASE_A_MODE} games={len(bm.games)}',
        flush=True,
    )
"""

OLD_AUDIT = """        public_runs = list(bm.game_runs)
        public_run_ids = [run.game_id for run in public_runs]
        if len(public_runs) != 25 or public_run_ids != list(PUBLIC_GAME_IDS):
            raise RuntimeError(
                f'Public run coverage changed: count={len(public_runs)} ids={public_run_ids}.'
            )
        unfinished = [
            (run.game_id, run.state, run.final_score)
            for run in public_runs
            if run.state not in {'won', 'gave_up', 'cancelled'}
            or run.final_score is None
        ]
        if unfinished:
            raise RuntimeError(f'Public runs did not finalize cleanly: {unfinished}.')
        crashed = [run.game_id for run in public_runs if run.state == 'crashed']
        if crashed:
            raise RuntimeError(f'Public runs crashed: {crashed}.')
        total_actions = sum(len(run.history) for run in public_runs)
        if total_actions <= 0:
            raise RuntimeError('Public runs produced no actions.')

        from inference.tools.eval import evaluate_runs, save_score_file

        score_summary = evaluate_runs([WORKING_DIR])
        score_path = save_score_file(
            score_summary,
            run_dirs=[WORKING_DIR],
            output_path=WORKING_DIR / "score.json",
        )
        if Path(score_path) != WORKING_DIR / 'score.json' or not Path(score_path).is_file():
            raise RuntimeError(f'Frozen scorer did not write score.json: {score_path}.')
        print(
            f'PUBLIC25_AUDIT runs=25 actions={total_actions} score_path={score_path}',
            flush=True,
        )
"""

NEW_AUDIT = """        public_runs = list(bm.game_runs)
        total_actions = sum(len(run.history) for run in public_runs)
        _p0_ns["require_model_actions"](total_actions, mode=PHASE_A_MODE)
        unfinished = [
            (run.game_id, run.state, run.final_score)
            for run in public_runs
            if run.state not in {'won', 'gave_up', 'cancelled'}
            or run.final_score is None
        ]
        if unfinished:
            raise RuntimeError(f'Offline runs did not finalize cleanly: {unfinished}.')
        crashed = [run.game_id for run in public_runs if run.state == 'crashed']
        if crashed:
            raise RuntimeError(f'Offline runs crashed: {crashed}.')
        if _p0_ns["should_run_public25_audit"](PHASE_A_MODE):
            public_run_ids = [run.game_id for run in public_runs]
            if len(public_runs) != 25 or public_run_ids != list(PUBLIC_GAME_IDS):
                raise RuntimeError(
                    f'Public run coverage changed: count={len(public_runs)} ids={public_run_ids}.'
                )
            from inference.tools.eval import evaluate_runs, save_score_file

            score_summary = evaluate_runs([WORKING_DIR])
            score_path = save_score_file(
                score_summary,
                run_dirs=[WORKING_DIR],
                output_path=WORKING_DIR / "score.json",
            )
            if Path(score_path) != WORKING_DIR / 'score.json' or not Path(score_path).is_file():
                raise RuntimeError(f'Frozen scorer did not write score.json: {score_path}.')
            print(
                f'PUBLIC25_AUDIT runs=25 actions={total_actions} score_path={score_path}',
                flush=True,
            )
        else:
            print(
                f'SMOKE_AUDIT mode={PHASE_A_MODE} runs={len(public_runs)} '
                f'actions={total_actions}',
                flush=True,
            )
"""


def patch_notebook() -> None:
    NOTEBOOK_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(PARENT_META, NOTEBOOK_DIR / "kernel-metadata.json")
    p0 = P0_PATH.read_text(encoding="utf-8")
    s4 = S4_PATH.read_text(encoding="utf-8")
    nb = json.loads(PARENT_NOTEBOOK.read_text(encoding="utf-8"))
    hook_idx = run_idx = None
    for idx, cell in enumerate(nb["cells"]):
        text = cell_text(cell)
        if cell.get("cell_type") == "code" and HOOK_NEEDLE in text:
            hook_idx = idx
        if cell.get("cell_type") == "code" and RUN_NEEDLE in text:
            run_idx = idx
    if hook_idx is None or run_idx is None:
        raise RuntimeError("Could not find customization or run cells")

    hook = nb["cells"][hook_idx]
    text = cell_text(hook)
    for marker in (S1_MARKER, S2_MARKER, S3_MARKER, S4_MARKER):
        if marker in text:
            text = text.split(marker, 1)[0].rstrip() + "\n"
    if OLD_SETTINGS not in text:
        raise RuntimeError("Champion solver-settings block not found")
    text = text.replace(OLD_SETTINGS, "", 1)
    set_cell_text(hook, text.rstrip() + "\n" + hook_block(p0, s4))

    run = nb["cells"][run_idx]
    run_text = cell_text(run)
    if OLD_OFFLINE_SELECT not in run_text or OLD_AUDIT not in run_text:
        raise RuntimeError("Offline selection/audit blocks not found")
    run_text = run_text.replace(OLD_OFFLINE_SELECT, NEW_OFFLINE_SELECT, 1)
    run_text = run_text.replace(OLD_AUDIT, NEW_AUDIT, 1)
    set_cell_text(run, run_text)

    NOTEBOOK_PATH.write_text(
        json.dumps(nb, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"patched cells {hook_idx},{run_idx} in {NOTEBOOK_PATH}")


if __name__ == "__main__":
    patch_notebook()
