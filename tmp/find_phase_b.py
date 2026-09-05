import json, pathlib, re, zipfile, io, ast
p = pathlib.Path(r"C:\Users\Dmitry\Desktop\Kaggle\ARC Prize 2026 - ARC-AGI-3\tmp\kernels\fork-lcld-v10\arc-prize-2026-lcld-qwen-v10.ipynb")
nb = json.loads(p.read_text(encoding="utf-8"))
def src(c):
    s=c.get("source",""); return "".join(s) if isinstance(s,list) else s
cell2 = src(nb["cells"][2])
print("cell2 len", len(cell2))
for pat in ["phase_b_model_smoke_or_die", "def phase_b", "phase_b_model"]:
    print(pat, cell2.count(pat))

# extract payload files from cell2
# typical pattern: files = { 'path': '''...''' }
out = pathlib.Path(r"C:\Users\Dmitry\Desktop\Kaggle\ARC Prize 2026 - ARC-AGI-3\tmp\diag_extract\v7_payload")
out.mkdir(parents=True, exist_ok=True)
(out/"cell2.py").write_text(cell2, encoding="utf-8")

# find function defs in cell2
defs = re.findall(r"def [A-Za-z0-9_]+\(", cell2)
print("unique defs sample", sorted(set(defs))[:80])
print("n defs", len(set(defs)))
print("has phase_b", "phase_b_model_smoke_or_die" in cell2)

# locate around the call site in cell2 if present
idx = cell2.find("phase_b_model_smoke")
print("idx", idx)
if idx>=0:
    print(cell2[max(0,idx-200):idx+400])