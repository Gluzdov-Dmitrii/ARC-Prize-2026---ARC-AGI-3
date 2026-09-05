import json, pathlib, re, textwrap
root = pathlib.Path(r"C:\Users\Dmitry\Desktop\Kaggle\ARC Prize 2026 - ARC-AGI-3\tmp\kernels")

def src(cell):
    s = cell.get("source", "")
    return "".join(s) if isinstance(s, list) else s

def dump_nb(path, tag):
    nb = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    print("="*80)
    print(tag, "cells", len(nb["cells"]), path)
    for i, c in enumerate(nb["cells"]):
        t = c.get("cell_type")
        body = src(c)
        head = body[:120].replace("\n"," | ")
        print(f"  [{i}] {t} {len(body):6d} {head}")

nbs = {
    "fork_v2": root/"fork-lcld-v10/arc-prize-2026-lcld-qwen-v10.ipynb",
    "author_v7": root/"lcld-v10-latest/arc-prize-2026-lcld-qwen-v10.ipynb",
    "lcld_v1": root/"lcld-v10/arc-prize-2026-lcld-qwen-v10.ipynb",
    "flash": root/"own-flash-pull/duck-qwen3-8-flash-next-nvfp4-mtp.ipynb",
    "keith": root/"keithtyser-fresh/duck-qwen3-8-flash-next-nvfp4-mtp.ipynb",
}
for tag, p in nbs.items():
    if p.exists():
        dump_nb(p, tag)
    else:
        print("MISSING", tag, p)