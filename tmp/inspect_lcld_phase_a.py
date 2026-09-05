from pathlib import Path
import json
import sys

nb_path = Path(r"C:\Users\Dmitry\Desktop\Kaggle\ARC Prize 2026 - ARC-AGI-3\tmp\kernels\fork-lcld-v10\arc-prize-2026-lcld-qwen-v10.ipynb")
out_dir = Path(r"C:\Users\Dmitry\Desktop\Kaggle\ARC Prize 2026 - ARC-AGI-3\tmp\kernels\fork-lcld-v10\cells")
out_dir.mkdir(exist_ok=True)
nb = json.loads(nb_path.read_text(encoding="utf-8"))
for i, cell in enumerate(nb["cells"]):
    src = "".join(cell.get("source") or [])
    p = out_dir / f"cell_{i:02d}_{cell['cell_type']}.txt"
    p.write_text(src, encoding="utf-8")
    print(f"CELL {i} {cell['cell_type']} chars={len(src)} lines={len(src.splitlines())} -> {p.name}")

p = Path(r"C:\Users\Dmitry\Desktop\Kaggle\ARC Prize 2026 - ARC-AGI-3\tmp\kernels\lcld-fork-output\submission.parquet")
print("parquet exists", p.exists(), "size", p.stat().st_size if p.exists() else None)
if p.exists():
    data = p.read_bytes()
    print("magic", data[:8])
    try:
        import pandas as pd
        df = pd.read_parquet(p)
        print("cols", list(df.columns), "rows", len(df))
        print(df.to_string())
    except Exception as e:
        print("pandas parquet failed:", type(e).__name__, e)
        # fallback: look for PAR1
        print("PAR1 count", data.count(b"PAR1"))