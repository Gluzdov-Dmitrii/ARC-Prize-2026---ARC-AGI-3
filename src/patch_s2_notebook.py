"""Build the S2 notebook from champion packaging minus the rejected S1 seed hook."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "src" / "s2_memory_capture.py"
PARENT_NOTEBOOK = (
    ROOT
    / "tmp"
    / "kernels"
    / "s1-deterministic"
    / "duck-qwen3-8-flash-next-nvfp4-mtp.ipynb"
)
PARENT_META = (
    ROOT / "tmp" / "kernels" / "s1-deterministic" / "kernel-metadata.json"
)
NOTEBOOK_DIR = ROOT / "tmp" / "kernels" / "s2-memory-capture"
NOTEBOOK_PATH = NOTEBOOK_DIR / "duck-qwen3-8-flash-next-nvfp4-mtp.ipynb"
S1_MARKER = "# === S1 deterministic control: single causal change ==="
S2_MARKER = "# === S2 memory capture: single causal change ==="
HOOK_NEEDLE = "bm.solver.concurrency = 28"


def cell_text(cell: dict) -> str:
    source = cell.get("source") or ""
    return "".join(source) if isinstance(source, list) else str(source)


def set_cell_text(cell: dict, text: str) -> None:
    cell["source"] = text.splitlines(keepends=True)
    if cell["source"] and not cell["source"][-1].endswith("\n"):
        cell["source"][-1] += "\n"


def s2_hook_block(source: str) -> str:
    if "'''" in source:
        raise RuntimeError("S2 source contains triple single quotes; refuse to embed")
    return f'''
{S2_MARKER}
# Keep the PUBLIC25 solver settings above unchanged. This block only captures
# labeled memory from reasoning and content. Seed/policy otherwise unchanged.
S2_SOURCE = r\'\'\'{source}\'\'\'
_s2_ns = {{"__name__": "s2_memory_capture"}}
exec(S2_SOURCE, _s2_ns)
S2_TELEMETRY = _s2_ns["install_s2_hooks"](
    bm,
    target=target,
    working_dir=WORKING_DIR,
    bundle_dir=BUNDLE_DIR,
    extra={{
        "parent_kernel": "dmitriigluzdov/duck-qwen3-8-flash-next-nvfp4-mtp",
        "parent_kernel_version": 3,
        "parent_submission_ref": 55959595,
        "parent_public_score": 3.39,
        "rejected_s1_ref": 56034166,
        "rejected_s1_score": 2.71,
        "true_submission": TRUE_SUBMISSION,
        "vllm_profile": PUBLIC25_VLLM_PROFILE_NAME,
        "vllm_profile_env": PUBLIC25_VLLM_PROFILE_ENV,
    }},
    source_text=S2_SOURCE,
)
print(
    "S2_MEMORY_CAPTURE reasoning+content telemetry="
    + str(_s2_ns["telemetry_path"](WORKING_DIR)),
    flush=True,
)
'''


def patch_notebook() -> None:
    NOTEBOOK_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(PARENT_META, NOTEBOOK_DIR / "kernel-metadata.json")
    source = SOURCE_PATH.read_text(encoding="utf-8")
    nb = json.loads(PARENT_NOTEBOOK.read_text(encoding="utf-8"))
    hook_idx = None
    for idx, cell in enumerate(nb["cells"]):
        if cell.get("cell_type") == "code" and HOOK_NEEDLE in cell_text(cell):
            hook_idx = idx
            break
    if hook_idx is None:
        raise RuntimeError("Could not find the PUBLIC25 customization-hook cell")
    cell = nb["cells"][hook_idx]
    text = cell_text(cell)
    if S1_MARKER in text:
        text = text.split(S1_MARKER, 1)[0].rstrip() + "\n"
    if S2_MARKER in text:
        text = text.split(S2_MARKER, 1)[0].rstrip() + "\n"
    patched = text.rstrip() + "\n" + s2_hook_block(source)
    set_cell_text(cell, patched)
    NOTEBOOK_PATH.write_text(
        json.dumps(nb, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"patched cell {hook_idx} in {NOTEBOOK_PATH}")


if __name__ == "__main__":
    patch_notebook()
