import json, hashlib, pathlib
root = pathlib.Path(r"C:\Users\Dmitry\Desktop\Kaggle\ARC Prize 2026 - ARC-AGI-3\tmp\kernels")

def load(p):
    return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))

def src_join(nb):
    parts=[]
    for c in nb.get("cells",[]):
        s=c.get("source","")
        if isinstance(s,list): s="".join(s)
        parts.append(s)
    return "\n\n#####CELL#####\n\n".join(parts)

def sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

nbs = {
    "ours": root/"own-flash-pull/duck-qwen3-8-flash-next-nvfp4-mtp.ipynb",
    "keith_fresh_old": root/"keithtyser-fresh/duck-qwen3-8-flash-next-nvfp4-mtp.ipynb",
    "keith_v14": root/"keithtyser-v14/duck-qwen3-8-flash-next-nvfp4-mtp.ipynb",
    "samrish": next((root/"samrishb").glob("*.ipynb")),
    "jakob": root/"jakob-anim/duck-qwen3-8-anim-base.ipynb",
    "dante": root/"dantelok/duck-qwen3-8-flash-next-nvfp4-mtp.ipynb",
}
texts={}
for k,p in nbs.items():
    if p and pathlib.Path(p).exists():
        t=src_join(load(p))
        texts[k]=t
        print(f"{k:16s} {len(t):7d} {sha(t)[:16]}  {p.name}")
    else:
        print("MISSING", k, p)

print("\nEquality:")
keys=list(texts)
for i,a in enumerate(keys):
    for b in keys[i+1:]:
        print(f"  {a} == {b}: {texts[a]==texts[b]}")