"""Action and candidate selection policy for GameSession."""

from __future__ import annotations

from typing import Any

from v10_agent.memory_contours import EpistemicMemory
from v10_agent.planning_set import PlanningSet
from v10_agent.trajectory import CandidateTrajectory, TrajectoryPool


class ActionSelectionPolicy:
    """Selects the next trajectory step prioritizing live OMIT branches, then fresh candidates, then fallback."""

    def select_next_step(
        self,
        pool: TrajectoryPool | None,
        epistemic_memory: EpistemicMemory,
        planning_set: PlanningSet,
    ) -> tuple[dict[str, Any] | None, str]:
        """Select next step dict and strategy label.

        Returns (step_dict, strategy) or (None, 'fallback').
        """
        # Priority 1: Try active candidate from Solver pool
        if pool is not None:
            active_cand = pool.active_candidate()
            if active_cand is not None:
                step = active_cand.current_step()
                if step is not None:
                    return step, "solver_candidate"

        # Priority 2: Try resuming a live OMIT branch if viable
        if epistemic_memory.live_omit_branches:
            # Look for an un-severed omit branch
            for branch in epistemic_memory.live_omit_branches:
                if not epistemic_memory.is_severed(branch.signature_id):
                    # We can synthesize a step or pivot attempt
                    pass

        # Priority 3: Fallback required
        return None, "fallback"
