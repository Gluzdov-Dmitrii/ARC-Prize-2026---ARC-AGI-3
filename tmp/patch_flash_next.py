import json
from pathlib import Path

nb_path = Path(r"C:\Users\Dmitry\Desktop\Kaggle\ARC Prize 2026 - ARC-AGI-3\tmp\kernels\fork-flash-next\duck-qwen3-8-flash-next-nvfp4-mtp.ipynb")
meta_path = Path(r"C:\Users\Dmitry\Desktop\Kaggle\ARC Prize 2026 - ARC-AGI-3\tmp\kernels\fork-flash-next\kernel-metadata.json")
nb = json.loads(nb_path.read_text(encoding="utf-8"))


def cell_src(cell):
    src = cell.get("source") or []
    return "".join(src) if isinstance(src, list) else src


def set_cell_src(cell, text):
    cell["source"] = text


helper = """
def _competition_root():
    candidates = [
        Path("/kaggle/input/competitions/arc-prize-2026-arc-agi-3"),
        Path("/kaggle/input/arc-prize-2026-arc-agi-3"),
    ]
    for root in candidates:
        if (root / "arc_agi_3_wheels").exists():
            print(f"taaf.kaggle: competition root = {root}")
            return root
    for wheels in Path("/kaggle/input").rglob("arc_agi_3_wheels"):
        if wheels.is_dir():
            print(f"taaf.kaggle: competition root = {wheels.parent}")
            return wheels.parent
    raise RuntimeError("Competition dataset with arc_agi_3_wheels was not mounted under /kaggle/input")

COMPETITION_ROOT = _competition_root()
"""

src3 = cell_src(nb["cells"][3])
if "_competition_root" not in src3:
    set_cell_src(nb["cells"][3], src3.rstrip() + "\n" + helper)

src5 = cell_src(nb["cells"][5])
old_wheels = '"/kaggle/input/competitions/arc-prize-2026-arc-agi-3/arc_agi_3_wheels"'
if old_wheels not in src5:
    raise SystemExit("cell 5 wheels path not found")
set_cell_src(nb["cells"][5], src5.replace(old_wheels, 'str(COMPETITION_ROOT / "arc_agi_3_wheels")'))

src15 = cell_src(nb["cells"][15])
old_env = 'competition_env_files = str(Path("/kaggle/input/competitions/arc-prize-2026-arc-agi-3/arc_agi_3_wheels").parent / "environment_files")'
if old_env not in src15:
    raise SystemExit("cell 15 env path not found")
set_cell_src(nb["cells"][15], src15.replace(old_env, 'competition_env_files = str(COMPETITION_ROOT / "environment_files")'))

nb_path.write_text(json.dumps(nb), encoding="utf-8")

meta = json.loads(meta_path.read_text(encoding="utf-8"))
meta["id_no"] = 132850984
meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
print("patched ok")
print(cell_src(nb["cells"][5]))
print("id_no", meta["id_no"])
