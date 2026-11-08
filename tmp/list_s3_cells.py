import json
from pathlib import Path

p = Path("tmp/kernels/s3-cross-level/duck-qwen3-8-flash-next-nvfp4-mtp.ipynb")
nb = json.loads(p.read_text(encoding="utf-8"))
for i, cell in enumerate(nb["cells"]):
    src = "".join(cell.get("source") or [])
    first = src.strip().splitlines()[:2]
    print(f"=== cell {i} {cell.get('cell_type')} {len(src)} chars ===")
    print("\n".join(first)[:240])
    print()
