"""Solver Prompt Builder (Call 3 Family).

Constructs prompts strictly quarantined from Python source code, syntax errors, and tracebacks.
"""

from __future__ import annotations

import json
from typing import Any

from v10_agent.memory_contours import EpistemicMemory
from v10_agent.planning_set import PlanningSet

SOLVER_SYSTEM_PROMPT = """\
You are the Solver Agent for an ARC-AGI-3 task.
Your role is to plan solution trajectories by calling ONLY the typed functions exposed in the provided function manifest.

CRITICAL ARCHITECTURAL CONSTRAINTS:
1. You interact ONLY through typed function signatures and docstrings. You NEVER see Python source code or runtime error logs.
2. All object arguments MUST resolve strictly inside the active PlanningSet object IDs. Do not invent object IDs.
3. Incorporate prior Brusentsov feedback: DO NOT retry branches with severed NULL signatures; adapt paused OMIT branches.
4. Output MUST be a valid JSON object matching schema 'v10.trajectory_package.1' enclosed in ```json ... ```.
"""


def build_solver_prompts(
    manifest: dict[str, Any],
    planning_set: PlanningSet,
    epistemic_memory: EpistemicMemory | None = None,
    action_budget: int = 50,
) -> tuple[str, str]:
    """Construct (system_prompt, user_prompt) for the Solver Agent."""
    functions_summary = manifest.get("functions", [])

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

    relations_summary = [
        rel.to_dict()
        for rel in planning_set.relations[:25]  # Token-budget friendly selection
    ]

    epistemic_summary: dict[str, Any] = {
        "severed_null_signatures": list(epistemic_memory.severed_null_signatures) if epistemic_memory else [],
        "live_omit_branches": [b.signature_id for b in (epistemic_memory.live_omit_branches if epistemic_memory else [])],
        "recent_judgments": [j.to_dict() for j in (epistemic_memory.judgments[-5:] if epistemic_memory else [])],
    }

    user_payload = {
        "planning_set_id": planning_set.snapshot_id,
        "grid_hash": planning_set.grid_hash,
        "remaining_action_budget": action_budget,
        "allowed_actions": list(planning_set.allowed_action_ids),
        "planning_objects": objects_summary,
        "spatial_relations": relations_summary,
        "epistemic_feedback": epistemic_summary,
        "available_dsl_functions": functions_summary,
    }

    user_text = f"""\
Current Problem State & Available DSL Functions:
{json.dumps(user_payload, indent=2)}

Formulate 1 to 4 candidate trajectories using the available DSL functions.
Output format:
```json
{{
  "schema_version": "v10.trajectory_package.1",
  "proposal_id": "prop_01",
  "snapshot_hash": "{planning_set.grid_hash}",
  "candidates": [
    {{
      "trajectory_id": "traj_01",
      "steps": [
        {{
          "step_id": "s1",
          "dsl_function": "{functions_summary[0]['name'] if functions_summary else 'move_toward'}",
          "arguments": {{"obj": "{planning_set.object_ids[0] if planning_set.object_ids else 'obj_0'}"}},
          "expected_propositions": [
            {{
              "family": "metric_sign",
              "subject_id": "{planning_set.object_ids[0] if planning_set.object_ids else 'obj_0'}",
              "predicate": "distance",
              "value": -1
            }}
          ],
          "abort_if": ["object_identity_destroyed"]
        }}
      ],
      "success_condition": {{"family": "terminal_metadata", "predicate": "win"}},
      "confidence": 0.8
    }}
  ]
}}
```
"""
    return SOLVER_SYSTEM_PROMPT, user_text
