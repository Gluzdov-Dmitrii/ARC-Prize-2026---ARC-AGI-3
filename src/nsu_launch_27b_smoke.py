"""Launch the 27B smoke under a leased CUDA UUID and write pid identity."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

PROJECT = Path("/home/scientists/gluz_d_s/kaggle/projects/arc-prize-2026-arc-agi-3")
RUN = PROJECT / "runs" / "20260907T-p0d-27b-smoke"
PYTHON = PROJECT / "envs" / "ngpu01" / "py3.11-cu124-vllm-v1" / "bin" / "python"
SMOKE = PROJECT / "code" / "nsu_a100_27b_smoke.py"
GPU = os.environ["CUDA_VISIBLE_DEVICES"]
IDENTITY = RUN / "process.json"
LOG = RUN / "smoke.log"


def main() -> None:
    RUN.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = GPU
    env["HF_HUB_CACHE"] = str(PROJECT / "cache" / "huggingface")
    env["HF_HOME"] = str(PROJECT / "cache" / "huggingface")
    env["TMPDIR"] = str(RUN / "tmp")
    (RUN / "tmp").mkdir(exist_ok=True)
    handle = LOG.open("ab")
    proc = subprocess.Popen(
        [str(PYTHON), str(SMOKE)],
        stdout=handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        env=env,
        cwd=str(RUN),
    )
    time.sleep(0.2)
    start = ""
    proc_dir = Path(f"/proc/{proc.pid}")
    if (proc_dir / "stat").is_file():
        start = (proc_dir / "stat").read_text().split()[21]
    payload = {
        "pid": proc.pid,
        "process_start": start or str(time.time()),
        "gpu": GPU,
        "started_at": time.time(),
    }
    IDENTITY.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
