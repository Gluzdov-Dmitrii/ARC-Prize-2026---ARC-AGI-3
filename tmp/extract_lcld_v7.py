import json
from pathlib import Path
p = Path(r"C:\Users\Dmitry\Desktop\Kaggle\ARC Prize 2026 - ARC-AGI-3\tmp\kernels\lcld-v10-latest\arc-prize-2026-lcld-qwen-v10.ipynb")
nb = json.loads(p.read_text(encoding="utf-8"))
out = Path(r"C:\Users\Dmitry\Desktop\Kaggle\ARC Prize 2026 - ARC-AGI-3\tmp\kernels\lcld-v10-latest\cells")
out.mkdir(exist_ok=True)
for i, c in enumerate(nb["cells"]):
    src = c.get("source") or []
    if isinstance(src, list):
        src = "".join(src)
    (out / f"cell_{i:02d}_{c['cell_type']}.txt").write_text(src, encoding="utf-8")
    print(i, c["cell_type"], len(src.splitlines()), "chars", len(src))