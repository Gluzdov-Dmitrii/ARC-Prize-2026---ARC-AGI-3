"""Download the official Qwen3.8-27B-FP8 proxy checkpoint into the ARC-3 project tree.

Does not reserve a GPU. Uses the NSU ML venv after bootstrap.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

PROJECT = Path("/home/scientists/gluz_d_s/kaggle/projects/arc-prize-2026-arc-agi-3")
HOST = os.uname().nodename
ENV_PYTHON = PROJECT / "envs" / HOST / "py3.11-cu124-vllm-v1" / "bin" / "python"
MODEL_ID = "Qwen/Qwen3.8-27B-FP8"
DEST = PROJECT / "models" / "Qwen3.8-27B-FP8"
CACHE = PROJECT / "cache" / "huggingface"
RUN_DIR = PROJECT / "runs" / "20260907T-p0c-27b-download"
RECEIPT = RUN_DIR / "download_receipt.json"


def main() -> None:
    started = time.time()
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    DEST.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HUB_CACHE"] = str(CACHE)
    os.environ["HF_HOME"] = str(CACHE)
    os.environ["HUGGINGFACE_HUB_CACHE"] = str(CACHE)
    from huggingface_hub import snapshot_download

    path = snapshot_download(
        repo_id=MODEL_ID,
        local_dir=str(DEST),
        local_dir_use_symlinks=False,
        resume_download=True,
    )
    size = 0
    files = 0
    for root, _dirs, names in os.walk(DEST):
        for name in names:
            files += 1
            size += (Path(root) / name).stat().st_size
    receipt = {
        "model_id": MODEL_ID,
        "dest": str(DEST),
        "snapshot_path": path,
        "files": files,
        "bytes": size,
        "elapsed_s": round(time.time() - started, 1),
        "gpu_reserved": False,
        "role": "A100 proxy screening; not the Kaggle Flash champion",
    }
    RECEIPT.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2), flush=True)


if __name__ == "__main__":
    main()
