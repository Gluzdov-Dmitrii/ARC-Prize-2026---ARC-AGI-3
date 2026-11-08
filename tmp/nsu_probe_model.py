from pathlib import Path
import os
import json

project = Path("/home/scientists/gluz_d_s/kaggle/projects/arc-prize-2026-arc-agi-3")
model = project / "models" / "Qwen3.8-27B-FP8"
env_py = project / "envs" / "ngpu01" / "py3.11-cu124-vllm-v1" / "bin" / "python"
files = [p for p in model.rglob("*") if p.is_file()]
print("host", os.uname().nodename)
print("model_dir", model.is_dir())
print("config", (model / "config.json").is_file())
print("files", len(files))
print("bytes", sum(p.stat().st_size for p in files))
print("env", env_py.is_file())
for name in ["bootstrap_receipt.json", "requirements.lock"]:
    pass
receipt = project / "runs" / "20260907T-p0c-ml-env" / "bootstrap_receipt.json"
download = project / "runs" / "20260907T-p0c-27b-download" / "download_receipt.json"
print("bootstrap_receipt", receipt.is_file())
print("download_receipt", download.is_file())
if download.is_file():
    print(download.read_text()[:800])
