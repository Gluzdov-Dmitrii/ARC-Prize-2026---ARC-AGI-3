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

    receipt_base = {
        "torch": getattr(torch, "__version__", None),
        "torch_cuda": torch.version.cuda,
        "cuda_visible_devices": visible,
        "cuda_available": bool(torch.cuda.is_available()),
    }
    if not torch.cuda.is_available():
        receipt_base.update(
            {
                "backend": "none",
                "text": None,
                "error": "torch.cuda.is_available() is false",
                "ok": False,
                "elapsed_s": round(time.time() - started, 1),
            }
        )
        RECEIPT.write_text(json.dumps(receipt_base, indent=2, default=str) + "\n", encoding="utf-8")
        raise SystemExit("torch.cuda.is_available() is false inside the leased GPU process")

    backend = "unknown"
    text = None
    error = None
    try:
        from transformers import AutoConfig, AutoProcessor
        from transformers.models.qwen3_5.modeling_qwen3_5 import (
            Qwen3_5ForConditionalGeneration,
        )

        print("SMOKE_LOAD class=Qwen3_5ForConditionalGeneration", flush=True)
        processor = AutoProcessor.from_pretrained(MODEL_DIR, trust_remote_code=True)
        config = AutoConfig.from_pretrained(MODEL_DIR, trust_remote_code=True)
        config.quantization_config = None
        text_config = getattr(config, "text_config", None)
        if text_config is not None and hasattr(text_config, "quantization_config"):
            text_config.quantization_config = None
        model = Qwen3_5ForConditionalGeneration.from_pretrained(
            MODEL_DIR,
            config=config,
            dtype=torch.bfloat16,
            device_map={"": 0},
            trust_remote_code=True,
        )
        print("SMOKE_LOADED", flush=True)
        encoded = processor.tokenizer("Say OK.", return_tensors="pt")
        encoded = {k: v.to("cuda:0") for k, v in encoded.items()}
        tokens = model.generate(**encoded, max_new_tokens=8)
        text = processor.tokenizer.decode(tokens[0], skip_special_tokens=True)
        backend = "transformers_qwen3_5"
        del model
        torch.cuda.empty_cache()
    except Exception as exc:
        import traceback

        error = f"{type(exc).__name__}:{exc}\n" + traceback.format_exc()[-2500:]
    finally:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    receipt = {
        **receipt_base,
        "backend": backend,
        "text": text,
        "error": error,
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
