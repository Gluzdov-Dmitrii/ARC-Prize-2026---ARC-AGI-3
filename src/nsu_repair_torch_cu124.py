"""Restore cu124 PyTorch after vLLM replaced it with CUDA 13. No GPU reservation."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

PROJECT = Path("/home/scientists/gluz_d_s/kaggle/projects/arc-prize-2026-arc-agi-3")
ENV = PROJECT / "envs" / "ngpu01" / "py3.11-cu124-vllm-v1"
PYTHON = ENV / "bin" / "python"
CACHE = PROJECT / "cache" / "pip"
RUN = PROJECT / "runs" / "20260907T-p0c-ml-env"
RECEIPT = RUN / "torch_cu124_repair.json"


def main() -> None:
    started = time.time()
    env = os.environ.copy()
    env["PIP_CACHE_DIR"] = str(CACHE)
    env["PYTHONNOUSERSITE"] = "1"
    env["CUDA_VISIBLE_DEVICES"] = ""
    cmd = [
        str(PYTHON),
        "-m",
        "pip",
        "install",
        "--cache-dir",
        str(CACHE),
        "torch==2.6.0",
        "torchvision==0.21.0",
        "torchaudio==2.6.0",
        "--index-url",
        "https://download.pytorch.org/whl/cu124",
    ]
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, env=env)
    probe = (
        "import json, importlib.metadata as m\n"
        "import torch\n"
        "names=['torch','torchvision','torchaudio','vllm','transformers']\n"
        "out={name: None for name in names}\n"
        "for name in names:\n"
        "    try:\n"
        "        out[name]=m.version(name)\n"
        "    except Exception as exc:\n"
        "        out[name]=f'ABSENT:{type(exc).__name__}'\n"
        "out['torch_cuda']=torch.version.cuda\n"
        "print(json.dumps(out))\n"
    )
    versions = json.loads(
        subprocess.check_output([str(PYTHON), "-c", probe], env=env, text=True)
    )
    receipt = {
        "elapsed_s": round(time.time() - started, 1),
        "versions": versions,
        "gpu_reserved": False,
        "reason": "vLLM 0.28 pulled torch 2.13 CUDA 13; driver 550.54.15 reports CUDA 12.4",
    }
    RECEIPT.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2), flush=True)


if __name__ == "__main__":
    main()
