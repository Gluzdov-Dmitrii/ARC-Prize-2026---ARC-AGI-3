import json
from pathlib import Path
p = Path(r"C:\Users\Dmitry\Desktop\Kaggle\ARC Prize 2026 - ARC-AGI-3\tmp\kernels\lcld-fork-output\arc-prize-2026-lcld-qwen-v10.log")
raw = p.read_text(encoding="utf-8", errors="replace")
# log is JSON array of stream events
events = json.loads(raw)
text = "".join(e.get("data","") for e in events if e.get("stream_name")=="stdout")
# extract probe blobs around labels
for marker in ["Probe 1 result:", "Probe 2 result:", "Probe 3 concurrent results:", "Heavy smoke execution status:"]:
    i = text.find(marker)
    print("\n====", marker, "====")
    if i < 0:
        print("NOT FOUND")
        continue
    print(text[i:i+1800])