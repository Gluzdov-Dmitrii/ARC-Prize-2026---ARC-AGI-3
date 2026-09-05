from pathlib import Path
import json, base64, io, zipfile, re

nb_path = Path(r"C:\Users\Dmitry\Desktop\Kaggle\ARC Prize 2026 - ARC-AGI-3\tmp\kernels\fork-lcld-v10\arc-prize-2026-lcld-qwen-v10.ipynb")
nb = json.loads(nb_path.read_text(encoding="utf-8"))
src = "".join(nb["cells"][2].get("source") or [])
m = re.search(r"PAYLOAD_B64 = '([^']+)'", src)
zip_data = base64.b64decode(m.group(1))
out = Path(r"C:\Users\Dmitry\Desktop\Kaggle\ARC Prize 2026 - ARC-AGI-3\tmp\kernels\fork-lcld-v10\payload")
out.mkdir(exist_ok=True)
with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
    zf.extractall(out)
    print("extracted", len(zf.namelist()), "files")
    for n in zf.namelist():
        print(" ", n)