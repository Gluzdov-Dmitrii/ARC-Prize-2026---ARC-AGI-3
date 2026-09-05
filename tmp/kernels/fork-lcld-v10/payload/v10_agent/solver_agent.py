"""Solver Agent (Call 3 Family).

Formulates candidate trajectory packages calling ONLY declared DSL functions,
writing exclusively to EpistemicMemory.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from v10_agent.config import V10Config
from v10_agent.explorer_agent import extract_json_block
from v10_agent.llm_advisor import BaseLLMAdvisor
from v10_agent.memory_contours import EpistemicMemory
from v10_agent.planning_set import PlanningSet
from v10_agent.prompt_builders.solver_prompt import build_solver_prompts

logger = logging.getLogger(__name__)


class SolverAgent:
    """Call 3: Proposes trajectory packages over certified DSL function manifests."""

    def __init__(self, config: V10Config, advisor: BaseLLMAdvisor):
        self.config = config
        self.advisor = advisor

    def generate_trajectory_package(
        self,
        manifest: dict[str, Any],
        planning_set: PlanningSet,
        epistemic_memory: EpistemicMemory | None = None,
        budget: int = 50,
        image_png: bytes | None = None,
    ) -> dict[str, Any] | None:
        """Propose candidate trajectories adhering strictly to schema v10.trajectory_package.1."""
        sys_prompt, user_prompt = build_solver_prompts(
            manifest=manifest,
            planning_set=planning_set,
            epistemic_memory=epistemic_memory,
            action_budget=budget,
        )

        try:
            response = self.advisor.generate(
                system_prompt=sys_prompt,
                user_prompt=user_prompt,
                config=self.config,
                image_bytes=image_png,
                agent_role="solver",
            )
        except Exception as exc:
            logger.warning(f"Solver LLM invocation failed: {exc}")
            return None

        package = extract_json_block(response)
        if not package or not isinstance(package, dict):
            logger.warning("Solver failed to return a valid JSON object")
            return None

        # Verify schema version and candidates
        candidates = package.get("candidates", [])
        if not candidates or not isinstance(candidates, list):
            logger.warning("Solver trajectory package contains no candidates")
            return None

        # Validate function names against manifest
        manifest_funcs = {f["name"] for f in manifest.get("functions", []) if "name" in f}
        valid_candidates: list[dict[str, Any]] = []

        for cand in candidates:
            steps = cand.get("steps", [])
            cand_valid = True
            for step in steps:
                fn_name = step.get("dsl_function")
                if fn_name not in manifest_funcs:
                    logger.warning(f"Step references undefined DSL function: {fn_name!r}")
                    cand_valid = False
                    break

                # Validate object arguments are grounded in PlanningSet (Rule I5)
                args = step.get("arguments", {})
                for k, v in args.items():
                    if isinstance(v, str) and (v.startswith("obj_") or v in planning_set.object_alias_to_real):
                        resolved = planning_set.resolve_object_id(v)
                        if resolved is None:
                            logger.warning(f"Argument {k}={v!r} not found in PlanningSet")
                            cand_valid = False
                            break

            if cand_valid and steps:
                valid_candidates.append(cand)

        if not valid_candidates:
            logger.warning("None of the proposed Solver candidates satisfied grounding checks")
            return None

        package["candidates"] = valid_candidates[: self.config.max_candidates_per_solver_package]
        package.setdefault("schema_version", "v10.trajectory_package.1")
        package.setdefault("snapshot_hash", planning_set.grid_hash)
        return package
