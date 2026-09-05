"""Explorer Prompt Builder (Call 1 Family).

Constructs prompts strictly quarantined from game goals and trajectory planning.
"""

from __future__ import annotations

import json
from typing import Sequence

from v10_agent.memory_contours import ProbeRecord
from v10_agent.planning_set import PlanningSet

EXPLORER_SYSTEM_PROMPT = """\
You are the Explorer Agent for an ARC-AGI-3 environment.
Your task is purely empirical discovery: discover the physical rules, action effects, and coordinate affordances of the current level.

CRITICAL ARCHITECTURAL CONSTRAINTS:
1. You describe ONLY factual action effects and coordinate affordances.
2. You NEVER speculate on puzzle goals, winning conditions, or strategies.
3. You NEVER emit action sequences, solution plans, or step-by-step paths.
4. Output MUST be a valid JSON object matching schema 'v10.env_spec.1' enclosed in ```json ... ```.
"""


def build_explorer_prompts(
    planning_set: PlanningSet,
    probe_history: Sequence[ProbeRecord] | None = None,
) -> tuple[str, str]:
    """Construct (system_prompt, user_prompt) for the Explorer Agent."""
    objects_summary = [
        {
            "id": obj.id,
            "alias": planning_set.object_real_to_alias.get(obj.id, obj.id),
            "color": obj.color,
            "area": obj.area,
            "bbox": obj.bbox.to_dict(),
            "centroid": obj.centroid.to_dict(),
        }
        for obj in planning_set.objects
    ]

    coords_summary = [
        {"id": c.candidate_id, "x": c.x, "y": c.y, "label": c.label, "source": c.source_type}
        for c in planning_set.coordinate_candidates
    ]

    probes_summary = [
        {
            "action": p.action_id,
            "data": p.action_data,
            "effect": p.observed_effect,
            "confidence": p.confidence,
        }
        for p in (probe_history or [])
    ]

    user_payload = {
        "planning_set_id": planning_set.snapshot_id,
        "grid_hash": planning_set.grid_hash,
        "grid_dims": {"height": planning_set.grid_dims[0], "width": planning_set.grid_dims[1]},
        "available_actions": list(planning_set.allowed_action_ids),
        "planning_objects": objects_summary,
        "coordinate_candidates": coords_summary,
        "prior_probe_history": probes_summary,
    }

    user_text = f"""\
Current Environment State:
{json.dumps(user_payload, indent=2)}

Analyze the available actions, objects, and prior probes to formulate an EnvironmentSpecification.
Output format:
```json
{{
  "schema_version": "v10.env_spec.1",
  "snapshot_hash": "{planning_set.grid_hash}",
  "planning_set_id": "{planning_set.snapshot_id}",
  "researched_actions": [
    {{
      "action_id": "ACTION1",
      "effect_summary": "description of observed or hypothesized physical effect",
      "supporting_evidence_ids": ["probe_0"],
      "confidence": 0.8,
      "contradicted": false
    }}
  ],
  "coordinate_affordances": [
    {{
      "coordinate_candidate_id": "coord_c_obj_0",
      "x": 10,
      "y": 12,
      "source": {{"type": "object_centroid", "object_id": "obj_0"}},
      "observed_effects": ["interaction_effect"],
      "confidence": 0.7
    }}
  ],
  "object_class_notes": [],
  "action_surface_notes": [],
  "invariants": ["object_identity_stable_under_ACTION2"]
}}
```
"""
    return EXPLORER_SYSTEM_PROMPT, user_text
