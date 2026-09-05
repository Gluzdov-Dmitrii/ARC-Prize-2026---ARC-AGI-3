import json, pathlib, base64, zipfile, io, re
p = pathlib.Path(r"C:\Users\Dmitry\Desktop\Kaggle\ARC Prize 2026 - ARC-AGI-3\tmp\kernels\fork-lcld-v10\arc-prize-2026-lcld-qwen-v10.ipynb")
nb = json.loads(p.read_text(encoding="utf-8"))
src = "".join(nb["cells"][2]["source"]) if isinstance(nb["cells"][2]["source"], list) else nb["cells"][2]["source"]
m = re.search(r"PAYLOAD_B64 = '([^']+)'", src)
print("payload match", bool(m), "len", len(m.group(1)) if m else 0)
b = base64.b64decode(m.group(1))
out = pathlib.Path(r"C:\Users\Dmitry\Desktop\Kaggle\ARC Prize 2026 - ARC-AGI-3\tmp\diag_extract\v7_zip")
out.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(io.BytesIO(b)) as zf:
    print("files:")
    for n in zf.namelist():
        info = zf.getinfo(n)
        print(f"  {n:50s} {info.file_size:6d}")
    zf.extractall(out)

smoke = (out/"phase_a_heavy_smoke.py").read_text(encoding="utf-8")
print("\nphase_a_heavy_smoke defs:")
for line in smoke.splitlines():
    if line.startswith("def "):
        print(" ", line)
print("has phase_b_model_smoke_or_die", "phase_b_model_smoke_or_die" in smoke)
print("file size", len(smoke))