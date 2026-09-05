import json, pathlib, hashlib, difflib
root = pathlib.Path(r"C:\Users\Dmitry\Desktop\Kaggle\ARC Prize 2026 - ARC-AGI-3\tmp")
out = root / "diag_extract"
out.mkdir(exist_ok=True)

def src(cell):
    s = cell.get("source", "")
    return "".join(s) if isinstance(s, list) else s

def load(p):
    return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))

fork = load(root/"kernels/fork-lcld-v10/arc-prize-2026-lcld-qwen-v10.ipynb")
auth = load(root/"kernels/lcld-v10-latest/arc-prize-2026-lcld-qwen-v10.ipynb")
v1 = load(root/"kernels/lcld-v10/arc-prize-2026-lcld-qwen-v10.ipynb")
flash = load(root/"kernels/own-flash-pull/duck-qwen3-8-flash-next-nvfp4-mtp.ipynb")

def h(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]

print("fork vs author cell hashes:")
for i in range(6):
    a, b = src(fork["cells"][i]), src(auth["cells"][i])
    print(f"  cell {i}: same={a==b} fork={h(a)} author={h(b)}")

(out/"lcld_v7_cell5.py").write_text(src(fork["cells"][5]), encoding="utf-8")
(out/"lcld_v1_cell5.py").write_text(src(v1["cells"][5]), encoding="utf-8")
(out/"flash_cell15.py").write_text(src(flash["cells"][15]), encoding="utf-8")
(out/"flash_cell3.py").write_text(src(flash["cells"][3]), encoding="utf-8")
(out/"lcld_v7_cell1.py").write_text(src(fork["cells"][1]), encoding="utf-8")
(out/"lcld_v7_cell4.py").write_text(src(fork["cells"][4]), encoding="utf-8")

print("\n=== v1 vs v7 cell5 diff ===")
d = list(difflib.unified_diff(
    src(v1["cells"][5]).splitlines(),
    src(fork["cells"][5]).splitlines(),
    fromfile="v1", tofile="v7", lineterm=""))
print("\n".join(d[:250]))
print("diff lines", len(d))