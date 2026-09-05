"""Pure-symbolic deterministic fallback operators when retries are exhausted."""

from __future__ import annotations

import logging
from typing import Any

from v10_agent.config import V10Config
from v10_agent.planning_set import PlanningSet
from v10_agent.types import ActionDeclaration, EffectDeclaration

logger = logging.getLogger(__name__)


class SymbolicFallbackEngine:
    """Deterministic fallback policy activated when Coder or Solver retries are exhausted."""

    def __init__(self, config: V10Config):
        self.config = config
        self.step_counter = 0

    def select_fallback_action(self, planning_set: PlanningSet) -> EffectDeclaration:
        """Deterministically select a safe, grounded fallback action."""
        self.step_counter += 1
        allowed = planning_set.allowed_action_ids

        # Heuristic 1: If ACTION6 (coordinate action) is available, click object centroids
        if "ACTION6" in allowed and planning_set.objects:
            # Cycle through object centroids
            obj_idx = (self.step_counter - 1) % len(planning_set.objects)
            target_obj = planning_set.objects[obj_idx]
            coord_x = int(round(target_obj.centroid.col))
            coord_y = int(round(target_obj.centroid.row))

            return EffectDeclaration(
                declared_action=ActionDeclaration(
                    action_id="ACTION6",
                    data={"x": coord_x, "y": coord_y},
                    reasoning={"source": "symbolic_fallback", "strategy": "click_centroid", "target_id": target_obj.id},
                ),
                expected_metric_deltas={"interaction": 1},
                target_object_ids=[target_obj.id],
            )

        # Heuristic 2: Try directional motions (ACTION1..ACTION4)
        for act in ("ACTION1", "ACTION2", "ACTION3", "ACTION4"):
            if act in allowed:
                return EffectDeclaration(
                    declared_action=ActionDeclaration(
                        action_id=act,
                        reasoning={"source": "symbolic_fallback", "strategy": "directional_probe"},
                    ),
                    expected_metric_deltas={"delta": 1},
                    target_object_ids=list(planning_set.object_ids[:1]),
                )

        # Heuristic 3: Default allowed action
        fallback_action = allowed[0] if allowed else "RESET"
        return EffectDeclaration(
            declared_action=ActionDeclaration(
                action_id=fallback_action,
                reasoning={"source": "symbolic_fallback", "strategy": "default_allowed"},
            )
        )
