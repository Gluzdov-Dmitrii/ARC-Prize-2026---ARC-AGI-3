"""Explorer Agent (Call 1 Family).

Conducts empirical research into action mechanics and coordinate affordances,
writing exclusively to EnvironmentSpecMemory.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from v10_agent.config import V10Config
from v10_agent.llm_advisor import BaseLLMAdvisor
from v10_agent.memory_contours import EnvironmentSpecMemory, ProbeRecord
from v10_agent.planning_set import PlanningSet
from v10_agent.prompt_builders.explorer_prompt import build_explorer_prompts
from v10_agent.types import ActionDeclaration

logger = logging.getLogger(__name__)


def extract_json_block(text: str) -> dict[str, Any] | None:
    """Extract and parse JSON object from markdown fenced block or raw string."""
    clean_text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    # Match ```json ... ```
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", clean_text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try raw JSON substring finding first { to last }
    first_brace = clean_text.find("{")
    last_brace = clean_text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        try:
            return json.loads(clean_text[first_brace : last_brace + 1])
        except json.JSONDecodeError:
            pass

    return None


class ExplorerAgent:
    """Call 1: Investigates action effects and coordinate affordances."""

    def __init__(self, config: V10Config, advisor: BaseLLMAdvisor):
        self.config = config
        self.advisor = advisor

    def generate_environment_spec(
        self,
        planning_set: PlanningSet,
        memory: EnvironmentSpecMemory,
        image_png: bytes | None = None,
    ) -> dict[str, Any]:
        """Generate and record a validated EnvironmentSpecification."""
        sys_prompt, user_prompt = build_explorer_prompts(
            planning_set=planning_set,
            probe_history=memory.probe_history,
        )

        response_text = self.advisor.generate(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            config=self.config,
            image_bytes=image_png,
            agent_role="explorer",
        )

        spec = extract_json_block(response_text)
        if not spec or not isinstance(spec, dict):
            # Fallback deterministic minimal spec
            spec = {
                "schema_version": "v10.env_spec.1",
                "snapshot_hash": planning_set.grid_hash,
                "planning_set_id": planning_set.snapshot_id,
                "researched_actions": [
                    {
                        "action_id": act,
                        "effect_summary": "unexplored_atomic_action",
                        "supporting_evidence_ids": [],
                        "confidence": 0.5,
                        "contradicted": False,
                    }
                    for act in planning_set.allowed_action_ids
                ],
                "coordinate_affordances": [
                    {
                        "coordinate_candidate_id": c.candidate_id,
                        "x": c.x,
                        "y": c.y,
                        "source": {"type": c.source_type, "object_id": c.object_id},
                        "observed_effects": [],
                        "confidence": 0.5,
                    }
                    for c in planning_set.coordinate_candidates[:5]
                ],
                "object_class_notes": [],
                "action_surface_notes": [],
                "invariants": ["object_identities_discrete"],
            }

        # Validate schema version
        spec.setdefault("schema_version", "v10.env_spec.1")
        spec.setdefault("snapshot_hash", planning_set.grid_hash)
        spec.setdefault("planning_set_id", planning_set.snapshot_id)

        # Write to memory (enforces ISO-3)
        memory.record_spec(spec)
        return spec

    def plan_probes(
        self,
        planning_set: PlanningSet,
        memory: EnvironmentSpecMemory,
        max_probes: int = 4,
    ) -> list[ActionDeclaration]:
        """Generate systematic probe actions to test affordances."""
        probes: list[ActionDeclaration] = []
        tested_actions = {p.action_id for p in memory.probe_history}

        # 1. Test basic discrete actions (e.g. ACTION1..ACTION5)
        for act in planning_set.allowed_action_ids:
            if act != "RESET" and act not in tested_actions and len(probes) < max_probes:
                probes.append(
                    ActionDeclaration(
                        action_id=act,
                        reasoning={"source": "explorer_probe", "type": "discrete_action_test"},
                    )
                )

        # 2. Test clicking object centroids (ACTION6)
        if "ACTION6" in planning_set.allowed_action_ids and len(probes) < max_probes:
            for coord in planning_set.coordinate_candidates:
                if coord.source_type == "object_centroid" and len(probes) < max_probes:
                    probes.append(
                        ActionDeclaration(
                            action_id="ACTION6",
                            data={"x": coord.x, "y": coord.y},
                            reasoning={"source": "explorer_probe", "type": "centroid_click", "coord_id": coord.candidate_id},
                        )
                    )

        return probes
