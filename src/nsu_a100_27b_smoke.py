"""One-A100 smoke for the 27B proxy. Run only after a valid resource_queue RESERVED lease."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

PROJECT = Path("/home/scientists/gluz_d_s/kaggle/projects/arc-prize-2026-arc-agi-3")
MODEL_DIR = PROJECT / "models" / "Qwen3.8-27B-FP8"
RUN_DIR = PROJECT / "runs" / "20260907T-p0d-27b-smoke"
RECEIPT = RUN_DIR / "smoke_receipt.json"


def main() -> None:
    started = time.time()
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    visible = os.environ.get("CUDA_VISIBLE_DEVICES", "")
    if not visible:
        raise SystemExit("CUDA_VISIBLE_DEVICES is empty; refuse to smoke without a GPU lease")
    if not MODEL_DIR.is_dir() or not any(MODEL_DIR.iterdir()):
        raise SystemExit(f"model not present: {MODEL_DIR}")

    import torch

    if not torch.cuda.is_available():
        raise SystemExit("torch.cuda.is_available() is false inside the leased GPU process")

    backend = "unknown"
    text = None
    error = None
    try:
        try:
            from vllm import LLM, SamplingParams

            llm = LLM(
                model=str(MODEL_DIR),
                trust_remote_code=True,
                max_model_len=2048,
                gpu_memory_utilization=0.85,
                tensor_parallel_size=1,
            )
            out = llm.generate(
                ["Say OK."],
                SamplingParams(max_tokens=8, temperature=0.0),
            )
            text = out[0].outputs[0].text
            backend = "vllm"
            del llm
        except Exception as exc:
            error = f"vllm:{type(exc).__name__}:{exc}"
            from transformers import AutoModelForCausalLM, AutoTokenizer

            tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR, trust_remote_code=True)
            model = AutoModelForCausalLM.from_pretrained(
                MODEL_DIR,
                torch_dtype=torch.bfloat16,
                device_map="cuda",
                trust_remote_code=True,
            )
            inputs = tokenizer("Say OK.", return_tensors="pt").to("cuda")
            tokens = model.generate(**inputs, max_new_tokens=8)
            text = tokenizer.decode(tokens[0], skip_special_tokens=True)
            backend = "transformers_fallback"
            del model
            torch.cuda.empty_cache()
            error = error
    finally:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    receipt = {
        "backend": backend,
        "text": text,
        "error": error,
        "cuda_visible_devices": visible,
        "gpu_name": torch.cuda.get_device_name(0),
        "elapsed_s": round(time.time() - started, 1),
        "ok": bool(text),
    }
    RECEIPT.write_text(json.dumps(receipt, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, default=str), flush=True)
    if not text:
        raise SystemExit("27B smoke produced no text")


if __name__ == "__main__":
    main()
