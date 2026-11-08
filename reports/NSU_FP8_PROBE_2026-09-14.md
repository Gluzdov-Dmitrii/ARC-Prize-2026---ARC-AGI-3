# NSU FP8 probe — 2026-09-14

Scope: no Kaggle submission, no publication, no LoRA/training. S9/ref 56221692 remained `PENDING` in a read-only Kaggle CLI check, so new Phase B work stayed blocked.

## Artifacts

- Local probe script: `src/nsu_qwen38_fp8_probe.py`
- Local A100 smoke scripts: `src/nsu_a100_27b_fp8_load_smoke.py`, `src/nsu_launch_27b_fp8_load_smoke.py`
- Config probe JSON: `reports/NSU_FP8_PROBE_2026-09-14.json`
- Load smoke JSON: `reports/NSU_FP8_LOAD_SMOKE_2026-09-14.json`
- Remote config run: `/home/scientists/gluz_d_s/kaggle/projects/arc-prize-2026-arc-agi-3/runs/20260914T-fp8-probe/`
- Remote load retry: `/home/scientists/gluz_d_s/kaggle/projects/arc-prize-2026-arc-agi-3/runs/20260914T-fp8-load-smoke-retry1/`

## Result

The previous FP8 blocker was narrowed to a config/Transformers issue, not an unusable checkpoint:

- Native config-only `FineGrainedFP8HfQuantizer.update_tp_plan()` fails with `AttributeError: 'NoneType' object has no attribute 'get'`.
- Cause: `Qwen3.8-27B-FP8` has `_experts_implementation = null`, while installed Transformers 5.16.1 has only `deepgemm_megamoe` in `FP8Experts._impl_tp_layer_overrides`.
- Config-only passing variants: `top_deepgemm_megamoe`, `top_and_text_deepgemm_megamoe`, and `none_override_guard`.
- Preferred smoke variant: `none_override_guard`, because the model config has no expert counts and the guard avoids pretending the dense model is MegaMoE.

Leased A100 retry with `none_override_guard` passed:

- GPU: A100 80GB, `sm_80`; Transformers warned that FP8 kernels require `>=8.9` and fell back to bf16 dequantization.
- `quantization_config_present=true`, no stripped quantization config.
- `load_elapsed_s=13.9` on warm cache; first cold-ish attempt loaded in `118.8s` but the receipt script crashed after load due a local `set` slicing bug.
- `missing_count=0`, `unexpected_count=0`, `unexpected_scale_inv_count=0`.
- Generation succeeded: `Say OK.\n\nOK.`
- Peak allocated memory: `51.15 GiB`.

## Decision

P0c is upgraded from “FP8 workaround only” to “FP8 checkpoint loads through honest dequant-to-bf16 path on one A100.” This is still a proxy model path, not Kaggle Flash/Blackwell equivalence and not a quality baseline.

C3 LoRA is no longer blocked by the earlier `weight_scale_inv UNEXPECTED` workaround, but it should not start training yet. Next residual step is P0d: paired external baseline/validation with this load path, fixed public panels/seeds, and manifests.
