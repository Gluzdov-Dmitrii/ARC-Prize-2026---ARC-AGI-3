import json, hashlib
from pathlib import Path

def load(p):
    nb = json.loads(Path(p).read_text(encoding="utf-8"))
    cells = []
    for i, c in enumerate(nb["cells"]):
        src = c.get("source") or []
        if isinstance(src, list):
            src = "".join(src)
        cells.append((i, c.get("cell_type"), src))
    return cells

pairs = {
    "jakob": r"C:\Users\Dmitry\Desktop\Kaggle\ARC Prize 2026 - ARC-AGI-3\tmp\kernels\jakob-anim\duck-qwen3-8-anim-base.ipynb",
    "keith": r"C:\Users\Dmitry\Desktop\Kaggle\ARC Prize 2026 - ARC-AGI-3\tmp\kernels\keithtyser-fresh\duck-qwen3-8-flash-next-nvfp4-mtp.ipynb",
    "ours": r"C:\Users\Dmitry\Desktop\Kaggle\ARC Prize 2026 - ARC-AGI-3\tmp\kernels\fork-flash-next\duck-qwen3-8-flash-next-nvfp4-mtp.ipynb",
}
loaded = {k: load(v) for k,v in pairs.items()}
for k, cells in loaded.items():
    print(k, "n_cells", len(cells), "total_chars", sum(len(s) for _,_,s in cells))

j, kth = loaded["jakob"], loaded["keith"]
print("\n=== JAKOB vs KEITH cell count", len(j), len(kth))
n = max(len(j), len(kth))
for i in range(n):
    js = j[i][2] if i < len(j) else "<missing>"
    ks = kth[i][2] if i < len(kth) else "<missing>"
    if js != ks:
        print(f"\n--- DIFF cell {i} jakob={j[i][1] if i<len(j) else '-'} keith={kth[i][1] if i<len(kth) else '-'} ---")
        print("JAKOB hash", hashlib.md5(js.encode()).hexdigest(), "len", len(js))
        print("KEITH hash", hashlib.md5(ks.encode()).hexdigest(), "len", len(ks))
        # show first differing lines
        jl, kl = js.splitlines(), ks.splitlines()
        for li, (a,b) in enumerate(zip(jl, kl)):
            if a != b:
                print(f"  line {li} J: {a[:180]}")
                print(f"  line {li} K: {b[:180]}")
                if li > 12:
                    break
        if len(jl) != len(kl):
            print("  nlines", len(jl), len(kl))
        # print unique snippets
        if abs(len(js)-len(ks)) < 500:
            import difflib
            d = list(difflib.unified_diff(kl, jl, lineterm="", n=1))
            print("\n".join(d[:80]))

print("\n=== JAKOB CELL HEADS ===")
for i, t, s in j:
    head = s.splitlines()[:4]
    print(f"cell {i} {t} lines={len(s.splitlines())} | " + " | ".join(head)[:180])