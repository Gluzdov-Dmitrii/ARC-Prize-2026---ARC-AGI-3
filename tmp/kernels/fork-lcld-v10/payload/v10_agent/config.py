"""Configuration engine for ARC-AGI-3 LCLD Agent V10.0.

Provides V10Config with environment variable resolution and competition ceilings.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


@dataclass
class V10Config:
    """Normative configuration for V10 Tri-Agent Neuro-Symbolic Agent."""

    # LLM Advisor & vLLM Backend
    llm_advisor_backend: str = "vllm"  # "vllm" | "fake" | "ollama" | "llama_cli"
    qwen_model_path: str = "foysalemonshanto/qwen3-8-27b-fp8-repacked-v1"
    qwen_vllm_base_url: str = "http://127.0.0.1:1234/v1"
    qwen_vllm_api_key: str = "EMPTY"
    qwen_context_tokens: int = 131072
    qwen_max_input_tokens: int = 65536
    qwen_max_output_tokens: int = 49152
    qwen_temperature: float = 0.7
    qwen_top_p: float = 0.9
    qwen_top_k: int = 30
    qwen_min_p: float = 0.0
    qwen_presence_penalty: float = 0.05
    qwen_repeat_penalty: float = 1.0
    qwen_seed: int = 42
    qwen_timeout_seconds: int = 700
    qwen_multimodal_enabled: bool = True
    qwen_enable_thinking: bool = True
    qwen_reasoning_budget_tokens: int = 32000

    # Tri-Agent Retries & Budgets (Normative Ceilings)
    max_coder_retries_per_level: int = 3
    max_solver_retries_per_level: int = 4
    max_explorer_probe_actions_per_level: int = 8
    max_total_llm_calls_per_level: int = 15

    # Trajectory & Solver Package Limits
    max_candidates_per_solver_package: int = 4
    max_steps_per_candidate: int = 6
    execute_one_step_at_a_time: bool = True

    # Deterministic Sandbox
    sandbox_enabled: bool = True
    sandbox_allowed_modules: list[str] = field(
        default_factory=lambda: ["math", "typing", "dataclasses", "enum", "collections"]
    )
    sandbox_max_cpu_seconds: float = 2.0
    sandbox_max_memory_mb: int = 512

    # Memory Contours
    game_memory_reset_on_game_change: bool = True
    game_memory_reset_on_level_change: bool = False
    epistemic_memory_max_entries: int = 50
    syntax_error_memory_max_entries: int = 5

    # Fallback System
    enable_symbolic_fallback: bool = True
    coder_exhaustion_forces_fallback: bool = True
    solver_exhaustion_forces_fallback: bool = True

    # Competition Execution Limits
    max_actions_per_game: int = 500
    max_actions_per_level: int = 500
    max_game_over_resets_per_game: int = 40
    max_game_over_resets_per_level: int = 40
    reset_on_game_over: bool = True
    game_wall_clock_limit_seconds: float = 5000.0
    competition_wall_clock_limit_seconds: float = 30600.0
    concurrency: int = 5
    vllm_max_num_seqs: int = 5
    vllm_startup_timeout_seconds: int = 900

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to dictionary."""
        return asdict(self)

    def update_runtime(self, updates: Mapping[str, Any]) -> None:
        """Update mutable configuration settings at runtime."""
        for key, value in updates.items():
            if hasattr(self, key):
                field_type = type(getattr(self, key))
                if value is not None and field_type is not type(None):
                    try:
                        if field_type is bool and isinstance(value, str):
                            setattr(self, key, value.strip().lower() in {"1", "true", "yes", "on"})
                        else:
                            setattr(self, key, field_type(value))
                    except (ValueError, TypeError):
                        setattr(self, key, value)
                else:
                    setattr(self, key, value)


def _bool_from_env(key: str, default: bool) -> bool:
    val = os.environ.get(key)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _int_from_env(key: str, default: int) -> int:
    val = os.environ.get(key)
    if val is None:
        return default
    try:
        return int(val.strip())
    except ValueError:
        return default


def _float_from_env(key: str, default: float) -> float:
    val = os.environ.get(key)
    if val is None:
        return default
    try:
        return float(val.strip())
    except ValueError:
        return default


def config_from_env(overrides: Mapping[str, Any] | None = None) -> V10Config:
    """Build V10Config reading from environment variables with safe defaults."""
    cfg = V10Config(
        llm_advisor_backend=os.environ.get("ARC_LLM_ADVISOR_BACKEND", os.environ.get("ARC_V8_QWEN_BACKEND", "vllm")),
        qwen_model_path=os.environ.get(
            "ARC_QWEN_MODEL_PATH",
            os.environ.get("ARC_LLM_MODEL_PATH", "foysalemonshanto/qwen3-8-27b-fp8-repacked-v1"),
        ),
        qwen_vllm_base_url=os.environ.get("ARC_QWEN_VLLM_BASE_URL", "http://127.0.0.1:1234/v1"),
        qwen_vllm_api_key=os.environ.get("ARC_QWEN_VLLM_API_KEY", "EMPTY"),
        qwen_context_tokens=_int_from_env("ARC_QWEN_CONTEXT_TOKENS", 131072),
        qwen_max_input_tokens=_int_from_env("ARC_QWEN_MAX_INPUT_TOKENS", 65536),
        qwen_max_output_tokens=_int_from_env("ARC_QWEN_MAX_OUTPUT_TOKENS", 49152),
        qwen_temperature=_float_from_env("ARC_QWEN_TEMPERATURE", 0.7),
        qwen_top_p=_float_from_env("ARC_QWEN_TOP_P", 0.9),
        qwen_top_k=_int_from_env("ARC_QWEN_TOP_K", 30),
        qwen_min_p=_float_from_env("ARC_QWEN_MIN_P", 0.0),
        qwen_presence_penalty=_float_from_env("ARC_QWEN_PRESENCE_PENALTY", 0.05),
        qwen_repeat_penalty=_float_from_env("ARC_QWEN_REPEAT_PENALTY", 1.0),
        qwen_seed=_int_from_env("ARC_QWEN_SEED", 42),
        qwen_timeout_seconds=_int_from_env("ARC_QWEN_TIMEOUT_SECONDS", 700),
        qwen_multimodal_enabled=_bool_from_env("ARC_QWEN_MULTIMODAL_ENABLED", True),
        qwen_enable_thinking=_bool_from_env("ARC_QWEN_ENABLE_THINKING", True),
        qwen_reasoning_budget_tokens=_int_from_env("ARC_QWEN_REASONING_BUDGET_TOKENS", 32000),
        max_coder_retries_per_level=_int_from_env("ARC_MAX_CODER_RETRIES", 3),
        max_solver_retries_per_level=_int_from_env("ARC_MAX_SOLVER_RETRIES", 4),
        max_explorer_probe_actions_per_level=_int_from_env("ARC_MAX_EXPLORER_PROBES", 8),
        max_total_llm_calls_per_level=_int_from_env("ARC_MAX_TOTAL_LLM_CALLS_PER_LEVEL", 15),
        max_candidates_per_solver_package=_int_from_env("ARC_MAX_CANDIDATES_PER_PACKAGE", 4),
        max_steps_per_candidate=_int_from_env("ARC_MAX_STEPS_PER_CANDIDATE", 6),
        execute_one_step_at_a_time=_bool_from_env("ARC_EXECUTE_ONE_STEP_AT_A_TIME", True),
        sandbox_enabled=_bool_from_env("ARC_SANDBOX_ENABLED", True),
        sandbox_max_cpu_seconds=_float_from_env("ARC_SANDBOX_MAX_CPU_SECONDS", 2.0),
        sandbox_max_memory_mb=_int_from_env("ARC_SANDBOX_MAX_MEMORY_MB", 512),
        game_memory_reset_on_game_change=_bool_from_env("ARC_GAME_MEMORY_RESET_ON_GAME_CHANGE", True),
        game_memory_reset_on_level_change=_bool_from_env("ARC_GAME_MEMORY_RESET_ON_LEVEL_CHANGE", False),
        epistemic_memory_max_entries=_int_from_env("ARC_EPISTEMIC_MEMORY_MAX_ENTRIES", 50),
        syntax_error_memory_max_entries=_int_from_env("ARC_SYNTAX_ERROR_MEMORY_MAX_ENTRIES", 5),
        enable_symbolic_fallback=_bool_from_env("ARC_ENABLE_SYMBOLIC_FALLBACK", True),
        coder_exhaustion_forces_fallback=_bool_from_env("ARC_CODER_EXHAUSTION_FORCES_FALLBACK", True),
        solver_exhaustion_forces_fallback=_bool_from_env("ARC_SOLVER_EXHAUSTION_FORCES_FALLBACK", True),
        max_actions_per_game=_int_from_env("LCLD_MAX_ACTIONS_PER_GAME", 500),
        max_actions_per_level=_int_from_env("LCLD_MAX_ACTIONS_PER_LEVEL", 500),
        game_wall_clock_limit_seconds=_float_from_env("LCLD_GAME_WALL_CLOCK_LIMIT_SECONDS", 5000.0),
        competition_wall_clock_limit_seconds=_float_from_env("LCLD_COMPETITION_WALL_CLOCK_LIMIT_SECONDS", 30600.0),
        concurrency=_int_from_env("LCLD_GAME_CONCURRENCY", 5),
        vllm_max_num_seqs=_int_from_env("LCLD_VLLM_MAX_NUM_SEQS", 5),
        vllm_startup_timeout_seconds=_int_from_env("VLLM_STARTUP_TIMEOUT_SECONDS", 900),
    )
    if overrides:
        cfg.update_runtime(overrides)
    return cfg


def config_from_mapping(mapping: Mapping[str, Any]) -> V10Config:
    """Build V10Config from a mapping/dict."""
    return config_from_env(mapping)
