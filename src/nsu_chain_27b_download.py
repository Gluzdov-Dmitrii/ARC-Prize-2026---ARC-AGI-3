"""Wait for the ML venv receipt, then download Qwen3.8-27B-FP8. No GPU reservation."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

PROJECT = Path("/home/scientists/gluz_d_s/kaggle/projects/arc-prize-2026-arc-agi-3")
RECEIPT = PROJECT / "runs" / "20260907T-p0c-ml-env" / "bootstrap_receipt.json"
DOWNLOAD = PROJECT / "code" / "nsu_download_qwen38_27b.py"
LOG = PROJECT / "runs" / "20260907T-p0c-27b-download" / "chain.log"


def main() -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    while not RECEIPT.is_file():
        if time.time() - started > 4 * 3600:
            raise SystemExit("timeout waiting for bootstrap_receipt.json")
        time.sleep(20)
    data = json.loads(RECEIPT.read_text(encoding="utf-8"))
    python = Path(data["env_dir"]) / "bin" / "python"
    if not python.is_file():
        raise SystemExit(f"missing venv python: {python}")
    print(f"bootstrap ready vllm={data.get('vllm_installed')} python={python}", flush=True)
    raise SystemExit(
        subprocess.call([str(python), str(DOWNLOAD)])
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        LOG.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
        raise
