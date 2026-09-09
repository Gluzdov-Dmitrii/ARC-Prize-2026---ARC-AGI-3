"""Build S4b notebook: outer HUD strip on the S4 (3.70) packaging, with our markdown."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.notebook_prose import rewrite_markdown_cells
from src.patch_s4_notebook import (
    HOOK_NEEDLE,
    P0_PATH,
    S4_MARKER,
    S4_PATH,
    cell_text,
    embed,
    set_cell_text,
)

PARENT_DIR = ROOT / "tmp" / "kernels" / "s4-no-impact"
PARENT_NOTEBOOK = PARENT_DIR / "duck-qwen3-8-flash-next-nvfp4-mtp.ipynb"
PARENT_META = PARENT_DIR / "kernel-metadata.json"
NOTEBOOK_DIR = ROOT / "tmp" / "kernels" / "s4b-outer2"
NOTEBOOK_PATH = NOTEBOOK_DIR / "duck-qwen3-8-flash-next-nvfp4-mtp.ipynb"
S4B_MARKER = "# === S4b outer HUD strip on S4 parent ==="
KERNEL_SLUG = "dmitriigluzdov/arc-agi-3-s4b-outer-hud-no-impact-flash-nvfp4"
KERNEL_TITLE = "ARC-AGI-3 S4b outer-HUD no-impact (Flash NVFP4)"


def hook_block(p0: str, s4: str) -> str:
    return f'''
{S4B_MARKER}
# Packaging: competition rerun keeps production budgets. Offline Save & Run is a
# short smoke. Policy: S4 no-impact memory with top+bottom HUD rows stripped.
# S1/S2/S3 not stacked. Parent is S4 kernel v7 / Public 3.70.
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
    hud_bottom_rows=2,
    extra={{
        "experiment_id": "S4b",
        "single_change": (
            "same S4 no-impact guard with top and bottom two HUD rows stripped"
        ),
        "parent_kernel": "dmitriigluzdov/duck-qwen3-8-flash-next-nvfp4-mtp",
        "parent_kernel_version": 7,
        "parent_submission_ref": 56097508,
        "parent_public_score": 3.70,
        "phase_a_mode": PHASE_A_MODE,
        "true_submission": TRUE_SUBMISSION,
        "vllm_profile": PUBLIC25_VLLM_PROFILE_NAME,
        "vllm_profile_env": PUBLIC25_VLLM_PROFILE_ENV,
    }},
    source_text=S4_SOURCE,
)
print(
    "S4B_OUTER_HUD hud_bottom_rows=2 telemetry="
    + str(_s4_ns["telemetry_path"](WORKING_DIR)),
    flush=True,
)
'''


def patch_notebook() -> None:
    if not PARENT_NOTEBOOK.is_file() or not PARENT_META.is_file():
        raise RuntimeError(f"S4 parent notebook missing: {PARENT_DIR}")
    NOTEBOOK_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(PARENT_META, NOTEBOOK_DIR / "kernel-metadata.json")
    meta_path = NOTEBOOK_DIR / "kernel-metadata.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["id"] = KERNEL_SLUG
    meta["title"] = KERNEL_TITLE
    meta["is_private"] = True
    meta["enable_internet"] = False
    meta["machine_shape"] = "NvidiaRtxPro6000"
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    p0 = P0_PATH.read_text(encoding="utf-8")
    s4 = S4_PATH.read_text(encoding="utf-8")
    nb = json.loads(PARENT_NOTEBOOK.read_text(encoding="utf-8"))
    hook_idx = None
    for idx, cell in enumerate(nb["cells"]):
        text = cell_text(cell)
        if cell.get("cell_type") == "code" and (
            HOOK_NEEDLE in text or S4_MARKER in text or S4B_MARKER in text
        ):
            hook_idx = idx
    if hook_idx is None:
        raise RuntimeError("Could not find customization cell")

    hook = nb["cells"][hook_idx]
    text = cell_text(hook)
    for marker in (S4B_MARKER, S4_MARKER):
        if marker in text:
            text = text.split(marker, 1)[0].rstrip() + "\n"
            break
    set_cell_text(hook, text.rstrip() + "\n" + hook_block(p0, s4))
    rewrite_markdown_cells(nb)

    NOTEBOOK_PATH.write_text(
        json.dumps(nb, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"patched cell {hook_idx} in {NOTEBOOK_PATH}")


if __name__ == "__main__":
    patch_notebook()
