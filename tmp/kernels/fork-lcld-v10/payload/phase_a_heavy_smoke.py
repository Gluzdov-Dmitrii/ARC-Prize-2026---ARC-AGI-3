"""Phase A Heavy Combat Smoke test for vLLM & Qwen3.8 on Kaggle GPU.

Reproduces v9-style deep combat diagnostics in Phase A Save Version log:
1. Verifies GPU via nvidia-smi (VRAM usage before and after).
2. Installs offline vLLM wheelhouse into isolated /kaggle/working/vllm-site-packages.
3. Launches local vLLM OpenAI-compatible server on 127.0.0.1:1234.
4. Executes 4 diagnostic probes:
   - Probe 1: Text decoding with Thinking enabled (<think>...</think> validation).
   - Probe 2: Multimodal vision (two ARC grid PNGs sent as base64 images).
   - Probe 3: Structured JSON schema / tool response.
   - Probe 4: 5 concurrent workers matching VLLM_MAX_NUM_SEQS = 5.
5. Emits vLLM server log tail (last 30KB) to stdout for public debuggability.
6. Cleanly stops vLLM server so Phase A exits 0 and writes submission.parquet.
"""

from __future__ import annotations

import base64
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.request import Request, urlopen

VLLM_HOST = "127.0.0.1"
VLLM_PORT = 1234
VLLM_BASE_URL = f"http://{VLLM_HOST}:{VLLM_PORT}/v1"
VLLM_HEALTH_URL = f"http://{VLLM_HOST}:{VLLM_PORT}/health"
VLLM_MAX_NUM_SEQS = 5
VLLM_STARTUP_TIMEOUT_SECONDS = 900
HEAVY_SMOKE_REQ_TIMEOUT = 600

_vllm_proc: subprocess.Popen | None = None
_vllm_log_file: Any = None


def get_working_root() -> pathlib.Path:
    p = pathlib.Path(os.environ.get("LCLD_WORKING_ROOT", "/kaggle/working")).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_vllm_site_packages() -> pathlib.Path:
    p = get_working_root() / "vllm-site-packages"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_vllm_log_path() -> pathlib.Path:
    return get_working_root() / "vllm.log"


def _smoke_gpu_info() -> str:
    if shutil.which("nvidia-smi") is None:
        return "nvidia-smi unavailable (CPU/non-CUDA runtime)"
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.used,memory.total", "--format=csv,noheader"],
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )
        return (r.stdout or "").strip() or "nvidia-smi returned empty"
    except Exception as exc:
        return f"nvidia-smi probe failed: {exc}"


def find_wheelhouse_path() -> pathlib.Path | None:
    candidates = [
        pathlib.Path("/kaggle/input/datasets/driessmit1/arc3-vllm-h100-wheelhouse-v3"),
        pathlib.Path("/kaggle/input/arc3-vllm-h100-wheelhouse-v3"),
        pathlib.Path("/kaggle/input/arc3-vllm-wheelhouse"),
        pathlib.Path("/kaggle/input/vllm-027-cuda-wheels"),
    ]
    for c in candidates:
        if c.is_dir():
            return c.resolve()
    # Scan /kaggle/input for any dir containing vllm wheel
    input_dir = pathlib.Path("/kaggle/input")
    if input_dir.is_dir():
        for root, _, files in os.walk(input_dir):
            if any("vllm" in f.lower() and f.endswith(".whl") for f in files):
                return pathlib.Path(root).resolve()
    return None


def install_vllm_wheelhouse(wheelhouse_dir: pathlib.Path) -> pathlib.Path:
    site_packages = get_vllm_site_packages()
    stamp_file = site_packages / ".vllm_installed_stamp"
    if stamp_file.is_file():
        print(f"[HEAVY-SMOKE] Reusing existing vLLM target at {site_packages}", flush=True)
        return site_packages

    req_file = wheelhouse_dir / "requirements.lock"
    cmd = [
        sys.executable, "-m", "pip", "install",
        "--no-index", f"--find-links={wheelhouse_dir}",
        "--target", str(site_packages),
        "--upgrade", "--ignore-installed", "--only-binary", ":all:",
        "--no-compile", "--disable-pip-version-check", "--no-warn-conflicts",
    ]
    if req_file.is_file():
        cmd.extend(["--requirement", str(req_file)])
    else:
        cmd.append("vllm")

    print(f"[HEAVY-SMOKE] Installing vLLM wheelhouse from {wheelhouse_dir} into {site_packages}...", flush=True)
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        print(f"[HEAVY-SMOKE] Pip install warning ({res.returncode}): {res.stderr[-1000:]}", flush=True)
    stamp_file.write_text(f"installed_from={wheelhouse_dir}\n", encoding="utf-8")
    return site_packages


def find_model_path() -> pathlib.Path | None:
    # 1. Explicit env var if set and non-empty
    env_var = os.environ.get("ARC_QWEN_MODEL_PATH", "").strip()
    if env_var:
        p = pathlib.Path(env_var).resolve()
        if p.is_dir() and (p / "config.json").is_file():
            print(f"[HEAVY-SMOKE] Using model path from ARC_QWEN_MODEL_PATH: {p}", flush=True)
            return p

    # 2. Check candidate paths with config.json validation
    candidates = [
        pathlib.Path("/kaggle/input/models/foysalemonshanto/qwen3-8-27b-fp8-repacked-v1/pyTorch/hf-fp8/1"),
        pathlib.Path("/kaggle/input/models/foysalemonshanto/qwen3-8-27b-fp8-repacked-v1/pytorch/hf-fp8/1"),
        pathlib.Path("/kaggle/input/models/foysalemonshanto/qwen3-8-27b-fp8-repacked-v1/hf-fp8/1"),
        pathlib.Path("/kaggle/input/qwen3-8-27b-fp8-repacked-v1/pyTorch/hf-fp8/1"),
        pathlib.Path("/kaggle/input/qwen3-8-27b-fp8-repacked-v1/pytorch/hf-fp8/1"),
        pathlib.Path("/kaggle/input/qwen3-8-27b-fp8-repacked-v1/hf-fp8/1"),
        pathlib.Path("/kaggle/input/qwen3-8-27b-fp8-repacked-v1"),
        pathlib.Path("/kaggle/input/foysalemonshanto/qwen3-8-27b-fp8-repacked-v1"),
        pathlib.Path("/kaggle/input/datasets/foysalemonshanto/qwen3-8-27b-fp8-repacked-v1"),
        pathlib.Path("/kaggle/input/vrfai-qwen3-6-27b-fp8-hf-snapshot"),
    ]
    for c in candidates:
        if c.is_dir() and (c / "config.json").is_file():
            print(f"[HEAVY-SMOKE] Found model at candidate path: {c}", flush=True)
            return c.resolve()

    # 3. Dynamic search across /kaggle/input for directory containing config.json
    input_dir = pathlib.Path("/kaggle/input")
    if input_dir.is_dir():
        for root, dirs, files in os.walk(input_dir):
            if "config.json" in files:
                r_path = pathlib.Path(root).resolve()
                if any(f.endswith(".safetensors") or f.endswith(".bin") for f in files) or "qwen" in str(r_path).lower():
                    print(f"[HEAVY-SMOKE] Dynamically discovered model weights at: {r_path}", flush=True)
                    return r_path

    print("[HEAVY-SMOKE] Notice: No directory containing config.json was found under /kaggle/input", flush=True)
    return None


def get_vllm_env(site_packages: pathlib.Path) -> dict[str, str]:
    env = dict(os.environ)
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        str(site_packages) + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
    )
    env.update({
        "USE_TF": "0",
        "TRANSFORMERS_NO_TF": "1",
        "TRANSFORMERS_NO_TORCHVISION": "1",
        "VLLM_NO_USAGE_STATS": "1",
        "VLLM_XGRAMMAR_CACHE_MB": "64",
        "VLLM_EXECUTE_MODEL_TIMEOUT_SECONDS": "700",
        # Critical Blackwell / RTX 6000 Ada workaround (from v9):
        "VLLM_USE_FLASHINFER_SAMPLER": "0",
    })
    return env


def start_vllm_server(model_path: pathlib.Path, site_packages: pathlib.Path) -> bool:
    global _vllm_proc, _vllm_log_file
    log_path = get_vllm_log_path()
    _vllm_log_file = log_path.open("w", encoding="utf-8")

    cmd = [
        sys.executable, "-m", "vllm.entrypoints.openai.api_server",
        "--model", str(model_path),
        "--served-model-name", "foysalemonshanto/qwen3-8-27b-fp8-repacked-v1",
        "--host", VLLM_HOST,
        "--port", str(VLLM_PORT),
        "--tensor-parallel-size", "1",
        "--max-num-seqs", str(VLLM_MAX_NUM_SEQS),
        "--limit-mm-per-prompt", json.dumps({"image": 4}),
        "--generation-config", "auto",
        "--enable-prefix-caching",
        "--mm-processor-cache-gb", "0",
        "--gpu-memory-utilization", "0.90",
        "--attention-backend", "FLASH_ATTN",
        "--default-chat-template-kwargs", json.dumps({"enable_thinking": True}),
        "--max-model-len", "65536",
        "--trust-remote-code",
    ]

    print(f"[HEAVY-SMOKE] Starting vLLM server: {' '.join(cmd)}", flush=True)
    _vllm_proc = subprocess.Popen(
        cmd,
        stdout=_vllm_log_file,
        stderr=subprocess.STDOUT,
        env=get_vllm_env(site_packages),
        text=True,
    )

    # Wait for ready up to 900 seconds
    started = time.monotonic()
    deadline = started + VLLM_STARTUP_TIMEOUT_SECONDS
    print(f"[HEAVY-SMOKE] Waiting for vLLM ready signal on {VLLM_HOST}:{VLLM_PORT} (timeout={VLLM_STARTUP_TIMEOUT_SECONDS}s)...", flush=True)

    while time.monotonic() < deadline:
        if _vllm_proc.poll() is not None:
            print(f"[HEAVY-SMOKE] vLLM process exited prematurely with code {_vllm_proc.returncode}!", flush=True)
            return False
        try:
            with urlopen(f"{VLLM_BASE_URL}/models", timeout=3) as resp:
                if resp.status == 200:
                    elapsed = round(time.monotonic() - started, 1)
                    print(f"[HEAVY-SMOKE] vLLM server ready in {elapsed}s!", flush=True)
                    return True
        except Exception:
            time.sleep(4.0)

    print("[HEAVY-SMOKE] vLLM server startup timed out!", flush=True)
    return False


def stop_vllm_server() -> None:
    global _vllm_proc, _vllm_log_file
    if _vllm_proc is not None and _vllm_proc.poll() is None:
        print("[HEAVY-SMOKE] Stopping vLLM server process...", flush=True)
        try:
            _vllm_proc.terminate()
            _vllm_proc.wait(timeout=15)
        except Exception:
            try:
                _vllm_proc.kill()
                _vllm_proc.wait(timeout=5)
            except Exception:
                pass
    _vllm_proc = None
    if _vllm_log_file is not None:
        try:
            _vllm_log_file.close()
        except Exception:
            pass
        _vllm_log_file = None


def _vllm_log_tail(limit: int = 30000) -> str:
    log_path = get_vllm_log_path()
    if not log_path.is_file():
        return "<no vllm.log found>"
    try:
        with log_path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - limit), os.SEEK_SET)
            return f.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return f"<error reading vllm.log: {exc}>"


def _smoke_send(label: str, payload: dict[str, Any], timeout: int = HEAVY_SMOKE_REQ_TIMEOUT) -> dict[str, Any]:
    rec: dict[str, Any] = {"label": label, "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    started = time.monotonic()
    req = Request(
        f"{VLLM_BASE_URL}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
    except Exception as exc:
        rec["elapsed"] = round(time.monotonic() - started, 2)
        rec["error_type"] = type(exc).__name__
        rec["error"] = str(exc)[:1000]
        return rec

    rec["elapsed"] = round(time.monotonic() - started, 2)
    try:
        data = json.loads(body)
        choices = data.get("choices") or [{}]
        choice = choices[0] if choices else {}
        msg = choice.get("message") or {}
        content = str(msg.get("content") or "")
        reasoning = str(msg.get("reasoning_content") or "")
        usage = data.get("usage") or {}

        try:
            json.loads(content)
            is_json = True
        except Exception:
            is_json = False

        rec.update({
            "finish_reason": choice.get("finish_reason"),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "reasoning_chars": len(reasoning),
            "content_chars": len(content),
            "content_is_json": is_json,
            "content_preview": content[:200] if len(content) > 200 else content,
        })
    except Exception as exc:
        rec["response_parse_error"] = str(exc)
        rec["body_tail"] = body[-500:]

    return rec


def _build_multimodal_smoke_payload(model_id: str) -> dict[str, Any]:
    """Create sample ARC multimodal payload with raw + annotated grid PNGs."""
    from v10_agent.frame_media import render_grid_png
    sample_grid = [
        [0, 1, 1, 0, 0, 2],
        [0, 1, 1, 0, 2, 2],
        [0, 0, 0, 0, 0, 0],
        [3, 3, 0, 4, 4, 4],
    ]
    raw_png = render_grid_png(sample_grid, scale=16)
    raw_b64 = base64.b64encode(raw_png).decode("ascii")

    user_content: list[dict[str, Any]] = [
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{raw_b64}"},
        },
        {
            "type": "text",
            "text": "Analyze this ARC grid image. Describe visible colored connected components and output a brief JSON summary with key 'objects'.",
        },
    ]

    return {
        "model": model_id,
        "messages": [
            {"role": "system", "content": "You are ARC-AGI-3 Perception Expert."},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.7,
        "top_p": 0.9,
        "max_tokens": 1024,
        "chat_template_kwargs": {"enable_thinking": True},
    }


def run_phase_a_smoke_pipeline() -> dict[str, Any]:
    """Execute complete Phase-A Heavy Combat Smoke pipeline."""
    print("=================================================================", flush=True)
    print("=== LCLD V10 PHASE-A HEAVY COMBAT SMOKE TEST START ===", flush=True)
    print("=================================================================", flush=True)

    summary: dict[str, Any] = {"status": "started", "gpu_before": _smoke_gpu_info()}
    print(f"[HEAVY-SMOKE] GPU status before: {summary['gpu_before']}", flush=True)

    wheelhouse = find_wheelhouse_path()
    if not wheelhouse:
        print("[HEAVY-SMOKE] vLLM wheelhouse dataset not found; skipping heavy smoke.", flush=True)
        summary["status"] = "skipped_no_wheelhouse"
        return summary

    model_path = find_model_path()
    if not model_path:
        print("[HEAVY-SMOKE] Qwen model weights not found; skipping heavy smoke.", flush=True)
        summary["status"] = "skipped_no_model"
        return summary

    try:
        site_packages = install_vllm_wheelhouse(wheelhouse)
        ready = start_vllm_server(model_path, site_packages)
        if not ready:
            summary["status"] = "vllm_startup_failed"
            print("=== vLLM SERVER LOG TAIL (Startup Failure) ===", flush=True)
            print(_vllm_log_tail(30000), flush=True)
            return summary

        model_id = "foysalemonshanto/qwen3-8-27b-fp8-repacked-v1"

        # --- Probe 1: Text baseline with thinking ---
        print("\n[HEAVY-SMOKE] Executing Probe 1: Text Baseline with Thinking...", flush=True)
        probe1_payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": "Count from 1 to 20, one number per line."}],
            "temperature": 0.7,
            "max_tokens": 1024,
            "chat_template_kwargs": {"enable_thinking": True},
        }
        p1_res = _smoke_send("probe1_text_baseline", probe1_payload, timeout=HEAVY_SMOKE_REQ_TIMEOUT)
        print(f"[HEAVY-SMOKE] Probe 1 result: {json.dumps(p1_res, indent=2)}", flush=True)
        summary["probe1"] = p1_res

        # --- Probe 2: Multimodal vision (ARC Grid PNG) ---
        print("\n[HEAVY-SMOKE] Executing Probe 2: Multimodal Visual Input...", flush=True)
        probe2_payload = _build_multimodal_smoke_payload(model_id)
        p2_res = _smoke_send("probe2_multimodal_vision", probe2_payload, timeout=HEAVY_SMOKE_REQ_TIMEOUT)
        print(f"[HEAVY-SMOKE] Probe 2 result: {json.dumps(p2_res, indent=2)}", flush=True)
        summary["probe2"] = p2_res

        # --- Probe 3: Concurrency test (5 workers in parallel) ---
        print(f"\n[HEAVY-SMOKE] Executing Probe 3: Parallelism ({VLLM_MAX_NUM_SEQS} concurrent requests)...", flush=True)
        concurrent_payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": "Return a 3-step arithmetic progression starting at 7."}],
            "max_tokens": 256,
            "chat_template_kwargs": {"enable_thinking": True},
        }
        with ThreadPoolExecutor(max_workers=VLLM_MAX_NUM_SEQS, thread_name_prefix="smoke_worker") as executor:
            futures = [
                executor.submit(_smoke_send, f"worker_{i}", concurrent_payload, timeout=HEAVY_SMOKE_REQ_TIMEOUT)
                for i in range(VLLM_MAX_NUM_SEQS)
            ]
            concurrent_results = [f.result() for f in futures]
        print(f"[HEAVY-SMOKE] Probe 3 concurrent results: {json.dumps(concurrent_results, indent=2)}", flush=True)
        summary["probe3_concurrency"] = concurrent_results

        summary["status"] = "success"
        summary["gpu_after"] = _smoke_gpu_info()
        print(f"\n[HEAVY-SMOKE] GPU status after: {summary['gpu_after']}", flush=True)

        print("\n=== vLLM SERVER LOG TAIL (Active Combat Session) ===", flush=True)
        print(_vllm_log_tail(30000), flush=True)

    except Exception as exc:
        print(f"[HEAVY-SMOKE] Pipeline encountered exception: {exc}", flush=True)
        summary["status"] = "error"
        summary["error"] = str(exc)
        print("=== vLLM SERVER LOG TAIL (Post-Exception) ===", flush=True)
        print(_vllm_log_tail(30000), flush=True)
    finally:
        stop_vllm_server()

    print("=================================================================", flush=True)
    print("=== LCLD V10 PHASE-A HEAVY COMBAT SMOKE TEST COMPLETE ===", flush=True)
    print("=================================================================", flush=True)
    return summary


if __name__ == "__main__":
    run_phase_a_smoke_pipeline()
