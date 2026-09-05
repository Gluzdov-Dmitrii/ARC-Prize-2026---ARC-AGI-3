import json, pathlib, difflib
root = pathlib.Path(r"C:\Users\Dmitry\Desktop\Kaggle\ARC Prize 2026 - ARC-AGI-3\tmp\kernels")

def cells(p):
    nb=json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
    out=[]
    for i,c in enumerate(nb["cells"]):
        s=c.get("source","")
        if isinstance(s,list): s="".join(s)
        out.append((c.get("cell_type"), s))
    return out

ours = cells(root/"own-flash-pull/duck-qwen3-8-flash-next-nvfp4-mtp.ipynb")
sam = cells(next((root/"samrishb").glob("*.ipynb")))
print("ours cells", len(ours), "sam cells", len(sam))
print("\nSAM cell heads:")
for i,(t,s) in enumerate(sam):
    print(f"  [{i}] {t} {len(s):6d} {s[:90].replace(chr(10),' | ')}")

# compare code cells only concatenated
def code(cells_):
    return "\n\n".join(s for t,s in cells_ if t=="code")
a,b = code(ours), code(sam)
if a==b:
    print("\nCODE CELLS IDENTICAL")
else:
    d=list(difflib.unified_diff(a.splitlines(), b.splitlines(), fromfile="ours", tofile="samrish", lineterm=""))
    print("\nCODE DIFF lines", len(d))
    print("\n".join(d[:180]))