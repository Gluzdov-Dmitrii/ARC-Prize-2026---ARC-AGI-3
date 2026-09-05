"""LayeredVerifier integrating Brusentsov ternary logic for empirical transition evaluation."""

from __future__ import annotations

import math
from typing import Any

from v10_agent.arga_lite import ARGALiteSnapshot, extract_arga_snapshot
from v10_agent.brusentsov_logic import BrusentsovJudgment, Ternary, implies_brusentsov
from v10_agent.config import V10Config
from v10_agent.planning_set import PlanningSet
from v10_agent.types import AtomicProposition, PropositionSet
from v10_agent.verification import GroundedStep


class LayeredVerifier:
    """Absolute authority on empirical transition evaluation (Brusentsov FOLLOW / NULL / OMIT)."""

    def __init__(self, config: V10Config):
        self.config = config

    def extract_observed_propositions(
        self,
        before_snapshot: ARGALiteSnapshot,
        after_obs: dict[str, Any],
        planning_set: PlanningSet,
    ) -> PropositionSet:
        """Derive observed atomic propositions from before-snapshot and after-observation."""
        raw_grid = after_obs.get("grid", [])
        after_snapshot = extract_arga_snapshot(raw_grid)

        props: list[AtomicProposition] = []

        # 1. Match objects between before and after snapshots
        matched_pairs: list[tuple[str, Any]] = []
        for b_obj in before_snapshot.objects:
            best_match = None
            best_dist = float("inf")
            for a_obj in after_snapshot.objects:
                if a_obj.color == b_obj.color:
                    d = math.hypot(b_obj.centroid.row - a_obj.centroid.row, b_obj.centroid.col - a_obj.centroid.col)
                    if d < best_dist:
                        best_dist = d
                        best_match = a_obj

            if best_match is not None and best_dist <= max(2.5, b_obj.bbox.height, b_obj.bbox.width):
                matched_pairs.append((b_obj.id, best_match))
                # Object identity preserved
                props.append(AtomicProposition(family="object_identity", subject_id=b_obj.id, predicate="preserved"))

                # Positional metric signs
                dr = best_match.centroid.row - b_obj.centroid.row
                dc = best_match.centroid.col - b_obj.centroid.col
                r_sign = 1 if dr > 0.05 else (-1 if dr < -0.05 else 0)
                c_sign = 1 if dc > 0.05 else (-1 if dc < -0.05 else 0)

                props.append(AtomicProposition(family="metric_sign", subject_id=b_obj.id, predicate="row_delta", value=r_sign))
                props.append(AtomicProposition(family="metric_sign", subject_id=b_obj.id, predicate="col_delta", value=c_sign))

                # Attribute deltas
                props.append(AtomicProposition(family="attribute_delta", subject_id=b_obj.id, predicate="color", value=best_match.color))
                props.append(AtomicProposition(family="attribute_delta", subject_id=b_obj.id, predicate="area", value=best_match.area))
            else:
                # Object destroyed or disappeared
                props.append(AtomicProposition(family="object_identity", subject_id=b_obj.id, predicate="destroyed"))

        # 2. Pairwise distance metric signs
        for i in range(len(matched_pairs)):
            id_a, a_after = matched_pairs[i]
            a_before = before_snapshot.get_object(id_a)
            if not a_before:
                continue
            for j in range(i + 1, len(matched_pairs)):
                id_b, b_after = matched_pairs[j]
                b_before = before_snapshot.get_object(id_b)
                if not b_before:
                    continue

                dist_before = math.hypot(a_before.centroid.row - b_before.centroid.row, a_before.centroid.col - b_before.centroid.col)
                dist_after = math.hypot(a_after.centroid.row - b_after.centroid.row, a_after.centroid.col - b_after.centroid.col)
                dd = dist_after - dist_before
                d_sign = 1 if dd > 0.05 else (-1 if dd < -0.05 else 0)

                props.append(
                    AtomicProposition(
                        family="metric_sign",
                        subject_id=id_a,
                        predicate="distance",
                        value=d_sign,
                        secondary_id=id_b,
                    )
                )

        # 3. Spatial relations in after-state
        for rel in after_snapshot.relations:
            props.append(
                AtomicProposition(
                    family="relation_existence",
                    subject_id=rel.subject_id,
                    predicate=rel.relation_type,
                    value=True,
                    secondary_id=rel.target_id,
                )
            )

        # 4. Terminal Metadata
        state = str(after_obs.get("state", "")).upper()
        if state in {"WIN", "WON", "DONE", "VICTORY"}:
            props.append(AtomicProposition(family="terminal_metadata", subject_id="game", predicate="win", value=True))
        elif state in {"GAME_OVER", "LOST", "FAILED"}:
            props.append(AtomicProposition(family="terminal_metadata", subject_id="game", predicate="game_over", value=True))

        levels_completed = after_obs.get("levels_completed", 0)
        props.append(AtomicProposition(family="terminal_metadata", subject_id="game", predicate="levels_completed", value=int(levels_completed or 0)))

        return PropositionSet.from_iterable(props)

    def evaluate_transition(
        self,
        step: GroundedStep,
        before_snapshot: ARGALiteSnapshot,
        after_obs: dict[str, Any],
        planning_set: PlanningSet,
    ) -> BrusentsovJudgment:
        """Evaluate empirical post-step transition and produce Brusentsov judgment."""
        observed = self.extract_observed_propositions(before_snapshot, after_obs, planning_set)
        verdict = implies_brusentsov(step.expected_propositions, observed)

        explanation = f"Step {step.step_id} ({step.dsl_function}): Verdict={verdict.name} (expected {len(step.expected_propositions)}, observed {len(observed)})"
        return BrusentsovJudgment(
            trajectory_id=step.step_id,
            step_id=step.step_id,
            verdict=verdict,
            expected_propositions=step.expected_propositions,
            observed_propositions=observed,
            explanation=explanation,
        )
