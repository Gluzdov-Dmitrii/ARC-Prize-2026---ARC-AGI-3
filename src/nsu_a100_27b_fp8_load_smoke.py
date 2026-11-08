"""A100 load smoke for Qwen3.8-27B-FP8 with quantization_config intact.

Run only inside a resource_queue A100 lease. This is not training and not a
quality baseline; it checks whether the FP8 checkpoint can be loaded honestly
through Transformers' dequant path on A100 instead of stripping scale tensors.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import traceback
from pathlib import Path
from typing import Any

PROJECT = Path("/home/scientists/gluz_d_s/kaggle/projects/arc-prize-2026-arc-agi-3")
MODEL_DIR = PROJECT / "models" / "Qwen3.8-27B-FP8"
DEFAULT_RUN_DIR = PROJECT / "runs" / "20260914T-fp8-load-smoke"


def _jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return str(value)


def _apply_variant(config: Any, variant: str) -> None:
    if variant == "none_override_guard":
        from transformers.integrations.finegrained_fp8 import FP8Experts

        FP8Experts._impl_tp_layer_overrides.setdefault(None, {})
    elif variant == "top_deepgemm_megamoe":
        setattr(config, "_experts_implementation", "deepgemm_megamoe")
    elif variant == "top_and_text_deepgemm_megamoe":
        setattr(config, "_experts_implementation", "deepgemm_megamoe")
        text_config = getattr(config, "text_config", None)
        if text_config is not None:
            setattr(text_config, "_experts_implementation", "deepgemm_megamoe")
    else:
        raise ValueError(f"unknown variant: {variant}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", default="none_override_guard")
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--max-new-tokens", type=int, default=8)
    args = parser.parse_args()

    started = time.time()
    args.run_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = args.run_dir / f"load_smoke_{args.variant}.json"
    visible = os.environ.get("CUDA_VISIBLE_DEVICES", "")
    if not visible:
        raise SystemExit("CUDA_VISIBLE_DEVICES is empty; refuse to smoke without a GPU lease")

    import torch
    import transformers
    from transformers import AutoConfig, AutoProcessor
    from transformers.models.qwen3_5.modeling_qwen3_5 import Qwen3_5ForConditionalGeneration

    receipt: dict[str, Any] = {
        "probe": "nsu_qwen38_fp8_load_smoke",
        "variant": args.variant,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
        "model_dir": str(MODEL_DIR),
        "cuda_visible_devices": visible,
        "versions": {
            "torch": getattr(torch, "__version__", None),
            "torch_cuda": getattr(torch.version, "cuda", None),
            "transformers": getattr(transformers, "__version__", None),
        },
        "cuda": {
            "available": bool(torch.cuda.is_available()),
            "device_count": torch.cuda.device_count() if torch.cuda.is_available() else 0,
        },
        "ok": False,
    }
    if torch.cuda.is_available():
        receipt["cuda"]["device_name"] = torch.cuda.get_device_name(0)
        receipt["cuda"]["capability"] = torch.cuda.get_device_capability(0)
    if not torch.cuda.is_available():
        receipt["error"] = "torch.cuda.is_available() is false"
        receipt["elapsed_s"] = round(time.time() - started, 1)
        receipt_path.write_text(json.dumps(receipt, indent=2, default=str) + "\n", encoding="utf-8")
        raise SystemExit(receipt["error"])

    model = None
    try:
        config = AutoConfig.from_pretrained(MODEL_DIR, trust_remote_code=True)
        _apply_variant(config, args.variant)
        receipt["config_after_variant"] = {
            "_experts_implementation": getattr(config, "_experts_implementation", None),
            "quantization_config_present": getattr(config, "quantization_config", None) is not None,
            "quantization_config": _jsonable(getattr(config, "quantization_config", None)),
        }
        quant_cfg = receipt["config_after_variant"]["quantization_config"]
        if isinstance(quant_cfg, dict) and isinstance(quant_cfg.get("modules_to_not_convert"), list):
            modules = quant_cfg["modules_to_not_convert"]
            quant_cfg["modules_to_not_convert"] = {"count": len(modules), "sample": modules[:20]}

        processor = AutoProcessor.from_pretrained(MODEL_DIR, trust_remote_code=True)
        load_start = time.time()
        model, loading_info = Qwen3_5ForConditionalGeneration.from_pretrained(
            MODEL_DIR,
            config=config,
            dtype=torch.bfloat16,
            device_map={"": 0},
            trust_remote_code=True,
            output_loading_info=True,
        )
        receipt["load_elapsed_s"] = round(time.time() - load_start, 1)
        unexpected = sorted(loading_info.get("unexpected_keys", []))
        missing = sorted(loading_info.get("missing_keys", []))
        receipt["loading_info"] = {
            "missing_count": len(missing),
            "missing_sample": missing[:20],
            "unexpected_count": len(unexpected),
            "unexpected_sample": unexpected[:20],
            "unexpected_scale_inv_count": sum("scale_inv" in key for key in unexpected),
        }

        encoded = processor.tokenizer("Say OK.", return_tensors="pt")
        encoded = {key: value.to("cuda:0") for key, value in encoded.items()}
        generate_start = time.time()
        tokens = model.generate(**encoded, max_new_tokens=args.max_new_tokens)
        receipt["generate_elapsed_s"] = round(time.time() - generate_start, 1)
        receipt["text"] = processor.tokenizer.decode(tokens[0], skip_special_tokens=True)
        receipt["ok"] = bool(receipt["text"])
    except Exception as exc:  # noqa: BLE001 - smoke must capture loader failures.
        receipt["error_type"] = type(exc).__name__
        receipt["error"] = str(exc)
        receipt["traceback_tail"] = traceback.format_exc()[-4000:]
    finally:
        try:
            del model
        except Exception:
            pass
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            receipt["max_memory_allocated_gib"] = round(
                torch.cuda.max_memory_allocated(0) / (1024**3),
                2,
            )
            receipt["memory_reserved_gib"] = round(torch.cuda.memory_reserved(0) / (1024**3), 2)
        receipt["elapsed_s"] = round(time.time() - started, 1)
        receipt_path.write_text(json.dumps(receipt, indent=2, default=str) + "\n", encoding="utf-8")
        print(json.dumps(receipt, indent=2, default=str), flush=True)

    if not receipt.get("ok"):
        raise SystemExit("FP8 load smoke failed")


if __name__ == "__main__":
    main()
