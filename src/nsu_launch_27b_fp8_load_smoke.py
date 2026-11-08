"""Launch the FP8 load smoke under a leased CUDA UUID and write pid identity."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT = Path("/home/scientists/gluz_d_s/kaggle/projects/arc-prize-2026-arc-agi-3")
PYTHON = PROJECT / "envs" / "ngpu01" / "py3.11-cu124-vllm-v1" / "bin" / "python"
SMOKE = PROJECT / "code" / "nsu_a100_27b_fp8_load_smoke.py"
DEFAULT_RUN = PROJECT / "runs" / "20260914T-fp8-load-smoke"


def main() -> None:
    variant = sys.argv[1] if len(sys.argv) > 1 else "none_override_guard"
    run = Path(os.environ.get("ARC3_FP8_RUN_DIR") or (sys.argv[2] if len(sys.argv) > 2 else DEFAULT_RUN))
    identity = run / "process.json"
    log = run / "load_smoke.log"
    gpu = os.environ["CUDA_VISIBLE_DEVICES"]
    run.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = gpu
    env["HF_HUB_CACHE"] = str(PROJECT / "cache" / "huggingface")
    env["HF_HOME"] = str(PROJECT / "cache" / "huggingface")
    env["TMPDIR"] = str(run / "tmp")
    (run / "tmp").mkdir(exist_ok=True)

    handle = log.open("ab")
    proc = subprocess.Popen(
        [str(PYTHON), str(SMOKE), "--variant", variant, "--run-dir", str(run)],
        stdout=handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        env=env,
        cwd=str(run),
    )
    time.sleep(0.2)
    process_start = ""
    proc_dir = Path(f"/proc/{proc.pid}")
    if (proc_dir / "stat").is_file():
        process_start = (proc_dir / "stat").read_text().split()[21]
    payload = {
        "pid": proc.pid,
        "process_start": process_start or str(time.time()),
        "gpu": gpu,
        "variant": variant,
        "started_at": time.time(),
        "log": str(log),
    }
    identity.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
