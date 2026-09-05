import json, hashlib, zipfile, io, base64, re
from pathlib import Path

def load_cells(p):
    nb = json.loads(Path(p).read_text(encoding="utf-8"))
    out = []
    for i, c in enumerate(nb["cells"]):
        src = c.get("source") or []
        if isinstance(src, list):
            src = "".join(src)
        out.append((i, c.get("cell_type"), src))
    return out

def h(s):
    return hashlib.md5(s.encode("utf-8", "replace")).hexdigest()[:10]

# --- Dante vs Keith ---
dante = load_cells(r"C:\Users\Dmitry\Desktop\Kaggle\ARC Prize 2026 - ARC-AGI-3\tmp\kernels\dantelok\duck-qwen3-8-flash-next-nvfp4-mtp.ipynb")
keith = load_cells(r"C:\Users\Dmitry\Desktop\Kaggle\ARC Prize 2026 - ARC-AGI-3\tmp\kernels\keithtyser-fresh\duck-qwen3-8-flash-next-nvfp4-mtp.ipynb")
print("DANTE vs KEITH", len(dante), len(keith), "chars", sum(len(x[2]) for x in dante), sum(len(x[2]) for x in keith))
for i in range(max(len(dante), len(keith))):
    a = dante[i][2] if i < len(dante) else ""
    b = keith[i][2] if i < len(keith) else ""
    if a != b:
        print(" DIFF cell", i, "d", len(a), "k", len(b))
        al, bl = a.splitlines(), b.splitlines()
        for li,(x,y) in enumerate(zip(al,bl)):
            if x!=y:
                print("  L", li, "D:", x[:160])
                print("     K:", y[:160])
                if li>8: break

# --- rakbidb customization ---
rak = load_cells(r"C:\Users\Dmitry\Desktop\Kaggle\ARC Prize 2026 - ARC-AGI-3\tmp\kernels\rakbidb\sukirman-verified-exact-profile-flash-next-mtp3.ipynb")
print("\nRAKBIDB n_cells", len(rak), "chars", sum(len(x[2]) for x in rak))
for i,t,s in rak:
    if "max_runtime" in s or "concurrency" in s or "Exact" in s or "profile" in s.lower():
        print("\n--- rak cell", i, t, "---")
        print(s[:1500])

# --- LCLD latest vs our fork ---
def extract_payload_names(nb_path):
    cells = load_cells(nb_path)
    print("\n", Path(nb_path).parent.name, "n_cells", len(cells))
    for i,t,s in cells:
        head = " ".join(s.splitlines()[:2])[:120]
        print(f"  cell {i} {t} lines={len(s.splitlines())} {head}")
    # payload from cell 2 if present
    for i,t,s in cells:
        m = re.search(r"PAYLOAD_B64 = '([^']+)'", s)
        if m:
            z = zipfile.ZipFile(io.BytesIO(base64.b64decode(m.group(1))))
            names = z.namelist()
            print("  payload files", names)
            for n in names:
                data = z.read(n)
                print("   ", n, len(data), h(data.decode("utf-8","replace") if n.endswith(".py") else str(len(data))))
            return z
    return None

z_old = extract_payload_names(r"C:\Users\Dmitry\Desktop\Kaggle\ARC Prize 2026 - ARC-AGI-3\tmp\kernels\fork-lcld-v10\arc-prize-2026-lcld-qwen-v10.ipynb")
z_new = extract_payload_names(r"C:\Users\Dmitry\Desktop\Kaggle\ARC Prize 2026 - ARC-AGI-3\tmp\kernels\lcld-v10-latest\arc-prize-2026-lcld-qwen-v10.ipynb")

if z_old and z_new:
    print("\n=== PAYLOAD DIFF old fork vs latest ===")
    old_n = set(z_old.namelist()); new_n = set(z_new.namelist())
    print("only old", old_n-new_n)
    print("only new", new_n-old_n)
    for n in sorted(old_n & new_n):
        a, b = z_old.read(n), z_new.read(n)
        if a != b:
            print("CHANGED", n, len(a), "->", len(b))
            # show small text diffs
            if n.endswith(".py") and abs(len(a)-len(b)) < 8000:
                import difflib
                da = a.decode("utf-8","replace").splitlines()
                db = b.decode("utf-8","replace").splitlines()
                d = list(difflib.unified_diff(da, db, lineterm="", n=1))
                print("\n".join(d[:60]))

# cell 5 of latest LCLD
cells_new = load_cells(r"C:\Users\Dmitry\Desktop\Kaggle\ARC Prize 2026 - ARC-AGI-3\tmp\kernels\lcld-v10-latest\arc-prize-2026-lcld-qwen-v10.ipynb")
print("\n=== LATEST LCLD CELL 5 ===")
print(cells_new[5][2] if len(cells_new)>5 else "no cell5")