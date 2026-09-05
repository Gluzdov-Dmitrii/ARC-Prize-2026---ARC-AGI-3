"""Coder Prompt Builder (Call 2 Family).

Constructs prompts strictly quarantined from level goals, Solver hypotheses, and EpistemicMemory.
"""

from __future__ import annotations

import json
from typing import Any, Sequence

from v10_agent.memory_contours import SyntaxErrorRecord

CODER_SYSTEM_PROMPT = """\
You are the DSL Coder Agent for an ARC-AGI-3 environment.
Your ONLY role is to implement a deterministic, side-effect-free Python 3.12 module and a typed JSON function manifest based strictly on the provided EnvironmentSpecification and SandboxAPI.

CRITICAL ARCHITECTURAL CONSTRAINTS:
1. You have NO INFORMATION about the puzzle goal or winning conditions. Do NOT attempt to solve the puzzle.
2. Generate pure functions that declare actions using `api.declare_environment_action(action_id, ...)`.
3. Allowed imports ONLY: math, typing, dataclasses, enum, collections.
4. Strictly FORBIDDEN: os, sys, subprocess, socket, open, eval, exec, compile, dunder traversal (__subclasses__).
5. Output MUST contain exactly two blocks:
   - A ```python ... ``` code block containing the DSL module.
   - A ```json ... ``` block containing the JSON manifest matching schema 'v10.dsl_manifest.1'.
"""

SANDBOX_API_DOC = """\
The SandboxAPI injected into your functions exposes:
  - api.planning_set: PlanningSet (read-only access to objects, relations, allowed actions)
  - api.get_object(obj_id_or_alias: str) -> PlanningObject | None
  - api.query_objects(predicate: Callable) -> list[PlanningObject]
  - api.metric_distance(obj_a: str, obj_b: str, metric_name: str = "centroid_distance") -> float
  - api.declare_environment_action(
        action_id: str,
        data: dict | None = None,
        reasoning: dict | None = None,
        expected_metric_deltas: dict | None = None,
        target_object_ids: list[str] | None = None,
        confidence: float = 1.0,
    ) -> EffectDeclaration
"""


def build_coder_prompts(
    env_spec: dict[str, Any],
    syntax_errors: Sequence[SyntaxErrorRecord] | None = None,
) -> tuple[str, str]:
    """Construct (system_prompt, user_prompt) for the DSL Coder Agent."""
    sections: list[str] = [
        "Environment Specification (Observed Facts & Affordances):",
        json.dumps(env_spec, indent=2),
        "",
        "Sandbox API Contract:",
        SANDBOX_API_DOC,
    ]

    if syntax_errors:
        sections.append("PREVIOUS COMPILATION / STATIC VALIDATION DIAGNOSTICS (FIX THESE ERRORS):")
        for idx, err in enumerate(syntax_errors, 1):
            sections.append(f"--- Attempt #{idx} Failure ---")
            sections.append(f"Error Type: {err.error_type}")
            sections.append(f"Message: {err.error_message}")
            if err.diagnostics:
                sections.append("Diagnostics:\n" + "\n".join(f"- {d}" for d in err.diagnostics))
            if err.source_code:
                sections.append(f"Faulty Source Snippet:\n```python\n{err.source_code[:1500]}\n```")

    user_instructions = """\
Generate the Python DSL functions and matching function manifest.
Example format:
```python
import math
from typing import Any

def move_toward(api, obj: str, target: str):
    dist = api.metric_distance(obj, target)
    return api.declare_environment_action(
        action_id="ACTION1",
        expected_metric_deltas={"distance": -1},
        target_object_ids=[obj, target],
    )
```

```json
{
  "schema_version": "v10.dsl_manifest.1",
  "functions": [
    {
      "name": "move_toward",
      "parameters": [
        {"name": "obj", "type": "planning_object_id"},
        {"name": "target", "type": "planning_object_id"}
      ],
      "returns": "effect_declaration",
      "docstring": "Declare intent to reduce distance between obj and target.",
      "purity": "pure_declaration",
      "expected_effect_template": {
        "metric_delta_sign": -1,
        "object_ids": ["obj", "target"]
      }
    }
  ]
}
```
"""
    sections.append(user_instructions)
    return CODER_SYSTEM_PROMPT, "\n".join(sections)
