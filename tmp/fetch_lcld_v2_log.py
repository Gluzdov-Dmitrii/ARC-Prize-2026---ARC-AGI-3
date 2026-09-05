from pathlib import Path
from kaggle.api.kaggle_api_extended import KaggleApi
from kagglesdk.kernels.types.kernels_api_service import (
    ApiGetKernelRequest,
    ApiListKernelSessionOutputRequest,
)
import json

out_dir = Path(r"C:\Users\Dmitry\Desktop\Kaggle\ARC Prize 2026 - ARC-AGI-3\tmp\kernels\lcld-v2-output")
out_dir.mkdir(parents=True, exist_ok=True)
api = KaggleApi(); api.authenticate()
with api.build_kaggle_client() as kg:
    req = ApiGetKernelRequest()
    req.user_name = "dmitriigluzdov"
    req.kernel_slug = "arc-prize-2026-lcld-qwen-v10"
    m = kg.kernels.kernels_api_client.get_kernel(req).metadata
    print("ver", m.current_version_number, "internet", m.enable_internet, "gpu", m.enable_gpu, "machine", m.machine_shape)

    out_req = ApiListKernelSessionOutputRequest()
    out_req.user_name = "dmitriigluzdov"
    out_req.kernel_slug = "arc-prize-2026-lcld-qwen-v10"
    api._set_paging(out_req, 20, None)
    response = kg.kernels.kernels_api_client.list_kernel_session_output(out_req)
    files = [f.file_name for f in (response.files or [])]
    print("first_page", files[:8], "n", len(files))
    log = response.log or ""
    (out_dir / "arc-prize-2026-lcld-qwen-v10.log").write_text(log, encoding="utf-8", errors="replace")
    print("log_len", len(log))

events = json.loads(log) if log.startswith("[") else []
text = "".join(e.get("data","") for e in events if e.get("stream_name")=="stdout")
err = "".join(e.get("data","") for e in events if e.get("stream_name")=="stderr")
print("stdout_len", len(text), "stderr_len", len(err))
for marker in [
    "Found competition wheels",
    "GPU status before",
    "Found model",
    "vLLM server ready",
    "Heavy smoke execution status",
    "PHASE A VALIDATION COMPLETE",
    "HEAVY-SMOKE WARNING",
    "Phase B competition execution skipped",
    "ENVIRONMENTS_DIR",
    "Traceback",
]:
    print("---", marker, "---")
    i = text.find(marker)
    if i < 0:
        i = err.find(marker)
        src = err if i>=0 else ""
        print("NOT IN STDOUT" if i<0 else src[i:i+400])
    else:
        print(text[i:i+500])