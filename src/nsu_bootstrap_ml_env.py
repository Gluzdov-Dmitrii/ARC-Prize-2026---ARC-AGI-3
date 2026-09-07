"""Create an ARC-3 ML venv on NSU without mutating stdlib envs or reserving a GPU."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
import venv
from pathlib import Path

PROJECT = Path("/home/scientists/gluz_d_s/kaggle/projects/arc-prize-2026-arc-agi-3")
HOST = os.uname().nodename
ENV_DIR = PROJECT / "envs" / HOST / "py3.11-cu124-vllm-v1"
CACHE_DIR = PROJECT / "cache" / "pip"
RUN_DIR = PROJECT / "runs" / "20260907T-p0c-ml-env"
GET_PIP = PROJECT / "cache" / "get-pip.py"
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"
RECEIPT = RUN_DIR / "bootstrap_receipt.json"
LOCKFILE = ENV_DIR / "requirements.lock"


def log(message: str) -> None:
    print(message, flush=True)


def run(cmd: list[str], env: dict[str, str] | None = None) -> None:
    log("+ " + " ".join(cmd))
    subprocess.run(cmd, check=True, env=env)


def task_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PIP_CACHE_DIR"] = str(CACHE_DIR)
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    env["TMPDIR"] = str(RUN_DIR / "tmp")
    env["VIRTUAL_ENV"] = str(ENV_DIR)
    env["PATH"] = str(ENV_DIR / "bin") + os.pathsep + env.get("PATH", "")
    return env


def create_venv() -> None:
    if (ENV_DIR / "bin" / "python").is_file():
        log(f"reuse venv {ENV_DIR}")
        return
    log(f"create venv {ENV_DIR}")
    ENV_DIR.parent.mkdir(parents=True, exist_ok=True)
    builder = venv.EnvBuilder(with_pip=False, clear=False, symlinks=True)
    builder.create(ENV_DIR)


def ensure_pip(python: Path) -> None:
    probe = subprocess.run(
        [str(python), "-m", "pip", "--version"],
        capture_output=True,
        text=True,
    )
    if probe.returncode == 0:
        log(probe.stdout.strip() or probe.stderr.strip())
        return
    GET_PIP.parent.mkdir(parents=True, exist_ok=True)
    if not GET_PIP.is_file():
        log(f"download {GET_PIP_URL}")
        urllib.request.urlretrieve(GET_PIP_URL, GET_PIP)
    run([str(python), str(GET_PIP), "--cache-dir", str(CACHE_DIR)])


def pip_install(python: Path, args: list[str]) -> None:
    run(
        [str(python), "-m", "pip", "install", "--cache-dir", str(CACHE_DIR), *args],
        env=task_env(),
    )


def main() -> None:
    started = time.time()
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    (RUN_DIR / "tmp").mkdir(exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    create_venv()
    python = ENV_DIR / "bin" / "python"
    ensure_pip(python)
    pip_install(python, ["-U", "pip", "setuptools", "wheel"])
    pip_install(
        python,
        [
            "torch",
            "torchvision",
            "torchaudio",
            "--index-url",
            "https://download.pytorch.org/whl/cu124",
        ],
    )
    pip_install(
        python,
        [
            "huggingface_hub",
            "transformers",
            "accelerate",
            "safetensors",
            "sentencepiece",
            "pillow",
            "numpy",
        ],
    )
    vllm_ok = True
    vllm_error = None
    try:
        pip_install(python, ["vllm"])
    except subprocess.CalledProcessError as exc:
        vllm_ok = False
        vllm_error = str(exc)
        log(f"vLLM install failed; continuing with transformers fallback: {exc}")

    freeze = subprocess.check_output(
        [str(python), "-m", "pip", "freeze"],
        env=task_env(),
        text=True,
    )
    LOCKFILE.write_text(freeze, encoding="utf-8")
    probe_src = (
        "import json, importlib.metadata as m\n"
        "names=['torch','torchvision','transformers','huggingface_hub','vllm','accelerate']\n"
        "out={}\n"
        "for name in names:\n"
        "    try:\n"
        "        out[name]=m.version(name)\n"
        "    except Exception as exc:\n"
        "        out[name]=f'ABSENT:{type(exc).__name__}'\n"
        "import torch\n"
        "out['torch_cuda']=torch.version.cuda\n"
        "print(json.dumps(out))\n"
    )
    versions = subprocess.check_output(
        [str(python), "-c", probe_src],
        text=True,
        env=task_env(),
    )
    receipt = {
        "project": str(PROJECT),
        "host": HOST,
        "env_dir": str(ENV_DIR),
        "lockfile": str(LOCKFILE),
        "vllm_installed": vllm_ok,
        "vllm_error": vllm_error,
        "versions": json.loads(versions),
        "elapsed_s": round(time.time() - started, 1),
        "gpu_reserved": False,
        "note": "CPU-only bootstrap; GPU availability from torch here may be false until a lease sets CUDA_VISIBLE_DEVICES",
    }
    RECEIPT.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    log(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
