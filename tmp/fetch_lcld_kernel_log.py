from pathlib import Path
from kaggle.api.kaggle_api_extended import KaggleApi
from kagglesdk.kernels.types.kernels_api_service import (
    ApiGetKernelRequest,
    ApiListKernelSessionOutputRequest,
)

out_dir = Path(r"C:\Users\Dmitry\Desktop\Kaggle\ARC Prize 2026 - ARC-AGI-3\tmp\kernels\lcld-fork-output")
out_dir.mkdir(parents=True, exist_ok=True)

api = KaggleApi()
api.authenticate()

with api.build_kaggle_client() as kaggle:
    req = ApiGetKernelRequest()
    req.user_name = "dmitriigluzdov"
    req.kernel_slug = "arc-prize-2026-lcld-qwen-v10"
    meta = kaggle.kernels.kernels_api_client.get_kernel(req).metadata
    for name in dir(meta):
        if name.startswith("_"):
            continue
        low = name.lower()
        if any(k in low for k in ("gpu", "internet", "status", "version", "machine", "accelerator", "title", "private", "id")):
            try:
                val = getattr(meta, name)
            except Exception:
                continue
            if callable(val):
                continue
            print(f"meta.{name} = {val}")

    out_req = ApiListKernelSessionOutputRequest()
    out_req.user_name = "dmitriigluzdov"
    out_req.kernel_slug = "arc-prize-2026-lcld-qwen-v10"
    api._set_paging(out_req, 20, None)
    response = kaggle.kernels.kernels_api_client.list_kernel_session_output(out_req)
    files = [f.file_name for f in (response.files or [])]
    print("first_page_files_count", len(files))
    for n in files[:25]:
        print(" file", n)
    log = response.log or ""
    log_path = out_dir / "arc-prize-2026-lcld-qwen-v10.log"
    log_path.write_text(log, encoding="utf-8", errors="replace")
    print("log_len", len(log), "saved", str(log_path))
    keys = (
        "error", "warning", "heavy-smoke", "phase a", "phase b", "vllm",
        "wheelhouse", "model", "found", "gpu", "cuda", "traceback",
        "complete", "submission", "rtx", "notice", "install", "status",
        "ready", "failed", "filenotfound", "nvidia", "probe", "skipped",
        "internet", "competition",
    )
    print("===== KEY LOG LINES =====")
    n = 0
    for line in log.splitlines():
        low = line.lower()
        if any(k in low for k in keys):
            print(line[:400])
            n += 1
            if n >= 120:
                print("...truncated key lines...")
                break