"""Embed S1 deterministic-control source into the champion notebook hook cell."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "src" / "s1_deterministic_control.py"
NOTEBOOK_PATH = (
    ROOT
    / "tmp"
    / "kernels"
    / "s1-deterministic"
    / "duck-qwen3-8-flash-next-nvfp4-mtp.ipynb"
)
MARKER = "# === S1 deterministic control: single causal change ==="
HOOK_NEEDLE = "bm.solver.concurrency = 28"


def cell_text(cell: dict) -> str:
    source = cell.get("source") or ""
    return "".join(source) if isinstance(source, list) else str(source)


def set_cell_text(cell: dict, text: str) -> None:
    cell["source"] = text.splitlines(keepends=True)
    if cell["source"] and not cell["source"][-1].endswith("\n"):
        cell["source"][-1] += "\n"


def s1_hook_block(source: str) -> str:
    if "'''" in source:
        raise RuntimeError("S1 source contains triple single quotes; refuse to embed")
    return f'''
{MARKER}
# Keep the PUBLIC25 solver settings above unchanged. This block only replaces
# LOCAL_ANALYZER_SEED=-1 with a stable per-game seed and writes telemetry.
S1_SOURCE = r\'\'\'{source}\'\'\'
_s1_ns = {{"__name__": "s1_deterministic_control"}}
exec(S1_SOURCE, _s1_ns)
S1_TELEMETRY = _s1_ns["install_s1_hooks"](
    bm,
    target=target,
    working_dir=WORKING_DIR,
    bundle_dir=BUNDLE_DIR,
    extra={{
        "parent_kernel": "dmitriigluzdov/duck-qwen3-8-flash-next-nvfp4-mtp",
        "parent_kernel_version": 3,
        "parent_submission_ref": 55959595,
        "parent_public_score": 3.39,
        "true_submission": TRUE_SUBMISSION,
        "vllm_profile": PUBLIC25_VLLM_PROFILE_NAME,
        "vllm_profile_env": PUBLIC25_VLLM_PROFILE_ENV,
    }},
    source_text=S1_SOURCE,
)
print(
    "S1_SEED_MODE namespace="
    + _s1_ns["S1_SEED_NAMESPACE"]
    + " telemetry="
    + str(_s1_ns["telemetry_path"](WORKING_DIR)),
    flush=True,
)
'''


def patch_notebook(notebook_path: Path = NOTEBOOK_PATH) -> None:
    source = SOURCE_PATH.read_text(encoding="utf-8")
    nb = json.loads(notebook_path.read_text(encoding="utf-8"))
    hook_idx = None
    for idx, cell in enumerate(nb["cells"]):
        if cell.get("cell_type") == "code" and HOOK_NEEDLE in cell_text(cell):
            hook_idx = idx
            break
    if hook_idx is None:
        raise RuntimeError("Could not find the PUBLIC25 customization-hook cell")
    cell = nb["cells"][hook_idx]
    text = cell_text(cell)
    if MARKER in text:
        text = text.split(MARKER, 1)[0].rstrip() + "\n"
    patched = text.rstrip() + "\n" + s1_hook_block(source)
    set_cell_text(cell, patched)
    notebook_path.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"patched cell {hook_idx} in {notebook_path}")


if __name__ == "__main__":
    patch_notebook()
