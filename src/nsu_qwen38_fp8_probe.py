"""Probe the NSU Qwen3.8-27B-FP8 loading blocker without loading weights.

Default mode is CPU-only/read-only: inspect config, installed Transformers FP8
helpers, and candidate tp-plan fixes. Use this before spending an A100 lease.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import platform
import time
import traceback
from pathlib import Path
from typing import Any


DEFAULT_PROJECT = Path("/home/scientists/gluz_d_s/kaggle/projects/arc-prize-2026-arc-agi-3")
DEFAULT_MODEL_DIR = DEFAULT_PROJECT / "models" / "Qwen3.8-27B-FP8"


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


def _quantization_summary(value: Any) -> Any:
    if value is None:
        return None
    payload = _jsonable(value)
    if isinstance(payload, dict) and isinstance(payload.get("modules_to_not_convert"), list):
        modules = payload["modules_to_not_convert"]
        payload["modules_to_not_convert"] = {
            "count": len(modules),
            "sample": modules[:20],
        }
    return payload


def _config_summary(config: Any) -> dict[str, Any]:
    text_config = getattr(config, "text_config", None)
    keys = [
        "_experts_implementation",
        "_experts_implementation_internal",
        "model_type",
        "architectures",
        "num_hidden_layers",
        "hidden_size",
        "intermediate_size",
        "num_attention_heads",
        "num_key_value_heads",
        "num_experts",
        "num_experts_per_tok",
        "n_routed_experts",
        "base_model_tp_plan",
        "base_model_ep_plan",
    ]
    return {
        "top": {key: _jsonable(getattr(config, key, None)) for key in keys},
        "text": {key: _jsonable(getattr(text_config, key, None)) for key in keys}
        if text_config is not None
        else None,
        "quantization_config": _quantization_summary(getattr(config, "quantization_config", None)),
        "text_quantization_config": _quantization_summary(getattr(text_config, "quantization_config", None))
        if text_config is not None
        else None,
    }


def _plan_summary(config: Any) -> dict[str, Any]:
    def summarize_plan(name: str) -> dict[str, Any]:
        plan = getattr(config, name, None) or {}
        return {
            "count": len(plan),
            "sample": dict(list(plan.items())[:12]),
            "styles": sorted({str(value) for value in plan.values()}),
        }

    return {
        "base_model_tp_plan": summarize_plan("base_model_tp_plan"),
        "base_model_ep_plan": summarize_plan("base_model_ep_plan"),
    }


def _run_tp_plan_variant(name: str, base_config: Any, quantizer: Any, mutator: Any | None = None) -> dict[str, Any]:
    config = copy.deepcopy(base_config)
    if mutator is not None:
        mutator(config)
    started = time.time()
    try:
        updated = quantizer.update_tp_plan(config)
        return {
            "name": name,
            "ok": True,
            "elapsed_s": round(time.time() - started, 3),
            "plan": _plan_summary(updated),
            "experts_implementation": getattr(updated, "_experts_implementation", None),
        }
    except Exception as exc:  # noqa: BLE001 - diagnostic script should capture all failures.
        return {
            "name": name,
            "ok": False,
            "elapsed_s": round(time.time() - started, 3),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback_tail": traceback.format_exc()[-2500:],
        }


def build_probe(model_dir: Path) -> dict[str, Any]:
    import torch
    import transformers
    from transformers import AutoConfig
    from transformers.integrations.finegrained_fp8 import FP8Experts
    from transformers.quantizers.quantizer_finegrained_fp8 import FineGrainedFP8HfQuantizer

    config = AutoConfig.from_pretrained(model_dir, trust_remote_code=True)
    quantization_config = getattr(config, "quantization_config", None)
    quantizer = FineGrainedFP8HfQuantizer(quantization_config, pre_quantized=True)
    impl_keys_before = sorted(str(key) for key in FP8Experts._impl_tp_layer_overrides.keys())

    def set_top_deepgemm(candidate: Any) -> None:
        setattr(candidate, "_experts_implementation", "deepgemm_megamoe")

    def set_both_deepgemm(candidate: Any) -> None:
        setattr(candidate, "_experts_implementation", "deepgemm_megamoe")
        text_config = getattr(candidate, "text_config", None)
        if text_config is not None:
            setattr(text_config, "_experts_implementation", "deepgemm_megamoe")

    def add_none_override(candidate: Any) -> None:
        FP8Experts._impl_tp_layer_overrides.setdefault(None, {})

    variants = [
        _run_tp_plan_variant("native_config", config, quantizer),
        _run_tp_plan_variant("top_deepgemm_megamoe", config, quantizer, set_top_deepgemm),
        _run_tp_plan_variant("top_and_text_deepgemm_megamoe", config, quantizer, set_both_deepgemm),
        _run_tp_plan_variant("none_override_guard", config, quantizer, add_none_override),
    ]

    cuda = {
        "available": bool(torch.cuda.is_available()),
        "device_count": torch.cuda.device_count() if torch.cuda.is_available() else 0,
    }
    if torch.cuda.is_available():
        cuda["devices"] = [
            {
                "index": index,
                "name": torch.cuda.get_device_name(index),
                "capability": torch.cuda.get_device_capability(index),
            }
            for index in range(torch.cuda.device_count())
        ]

    return {
        "probe": "nsu_qwen38_fp8",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host": platform.node(),
        "user": os.environ.get("USER") or os.environ.get("USERNAME"),
        "model_dir": str(model_dir),
        "model_dir_exists": model_dir.is_dir(),
        "versions": {
            "python": platform.python_version(),
            "torch": getattr(torch, "__version__", None),
            "torch_cuda": getattr(torch.version, "cuda", None),
            "transformers": getattr(transformers, "__version__", None),
        },
        "cuda": cuda,
        "fp8_experts_impl_keys_before": impl_keys_before,
        "fp8_experts_impl_keys_after": sorted(str(key) for key in FP8Experts._impl_tp_layer_overrides.keys()),
        "config": _config_summary(config),
        "tp_plan_variants": variants,
        "interpretation": {
            "native_failure_expected": "native_config fails if _experts_implementation is None and quantizer does layer_overrides.get",
            "safe_next_step": "If a config-only variant passes, run a leased A100 load smoke for that variant before any LoRA or paired eval.",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    result = build_probe(args.model_dir)
    text = json.dumps(result, indent=2, default=str) + "\n"
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
