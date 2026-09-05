"""Brusentsov Ternary Logic Engine for empirical transition judgments.

Implements necessary implication semantics:
  - TRUE (1)       : FOLLOW - expected effect is necessarily contained in observed state.
  - FALSE (-1)     : NULL   - physical contradiction / nullity violation (hard branch sever).
  - IRRELEVANT (0) : OMIT   - expected effect did not occur, but no physical laws or invariants
                              were violated (branch paused for future growth/pivot).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from v10_agent.types import AtomicProposition, PropositionSet


class Ternary(Enum):
    """Brusentsov ternary truth values for transition verdicts."""
    TRUE = 1          # FOLLOW: Trajectory step confirmed; necessary containment held.
    FALSE = -1        # NULL: Hard contradiction; branch severed.
    IRRELEVANT = 0    # OMIT: Inessential / passive outcome; branch paused.


@dataclass(frozen=True)
class BrusentsovJudgment:
    """Auditable transition evaluation judgment grounded on Brusentsov logic."""
    trajectory_id: str
    step_id: str
    verdict: Ternary
    expected_propositions: PropositionSet
    observed_propositions: PropositionSet
    explanation: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trajectory_id": self.trajectory_id,
            "step_id": self.step_id,
            "verdict": self.verdict.name,
            "verdict_value": self.verdict.value,
            "expected_count": len(self.expected_propositions),
            "observed_count": len(self.observed_propositions),
            "explanation": self.explanation,
            "timestamp": self.timestamp,
        }


def contradicts(expected: AtomicProposition, observed: AtomicProposition) -> bool:
    """Check if an observed proposition physically contradicts an expected proposition."""
    # 1. Object Identity preservation contradiction:
    # Expected object preserved, but observed destroyed/missing
    if expected.family == "object_identity":
        if expected.subject_id == observed.subject_id:
            if expected.predicate == "preserved" and observed.predicate in {"destroyed", "missing", "vanished"}:
                return True
            if expected.predicate in {"destroyed", "vanished"} and observed.predicate == "preserved":
                return True

    # 2. Attribute Delta contradiction:
    # Same subject, same attribute, but differing values (e.g. expected color 2, observed color 3)
    if expected.family == "attribute_delta" and observed.family == "attribute_delta":
        if expected.subject_id == observed.subject_id and expected.predicate == observed.predicate:
            if expected.value is not None and observed.value is not None:
                if expected.value != observed.value:
                    return True

    # 3. Metric Sign contradiction:
    # Expected change in a specific direction (+1 or -1), but observed opposite direction
    if expected.family == "metric_sign" and observed.family == "metric_sign":
        if expected.subject_id == observed.subject_id and expected.predicate == observed.predicate:
            if expected.secondary_id == observed.secondary_id:
                try:
                    exp_sign = int(expected.value)
                    obs_sign = int(observed.value)
                    # Contradiction if opposite sign (e.g. expected +1, observed -1)
                    if exp_sign != 0 and obs_sign != 0 and exp_sign != obs_sign:
                        return True
                    # If strictly non-zero expected delta was anticipated, but movement was strictly zero and blocked
                    if exp_sign != 0 and obs_sign == 0 and expected.predicate.endswith("_delta"):
                        # If predicate strictly demands delta, a 0 is contradictory only if explicit opposite effect
                        pass
                except (ValueError, TypeError):
                    pass

    # 4. Relation Existence contradiction:
    # Same pair of objects, contradictory relational state
    if expected.family == "relation_existence" and observed.family == "relation_existence":
        if (
            expected.subject_id == observed.subject_id
            and expected.secondary_id == observed.secondary_id
            and expected.predicate == observed.predicate
        ):
            if expected.value is not None and observed.value is not None:
                if bool(expected.value) != bool(observed.value):
                    return True

    # 5. Terminal Metadata contradiction:
    # e.g., Expected win, but observed game_over
    if expected.family == "terminal_metadata" and observed.family == "terminal_metadata":
        if expected.predicate == "win" and observed.predicate in {"game_over", "lost"}:
            return True

    return False


def is_necessarily_contained(expected: AtomicProposition, observed_set: PropositionSet) -> bool:
    """Check if the expected proposition is necessarily contained in the observed proposition set."""
    for obs in observed_set:
        if obs.family != expected.family:
            continue
        if obs.subject_id != expected.subject_id:
            continue
        if obs.predicate != expected.predicate:
            continue
        if expected.secondary_id is not None and obs.secondary_id != expected.secondary_id:
            continue

        # If value is specified, verify compatibility
        if expected.value is not None:
            if obs.value is None:
                continue
            if obs.value != expected.value:
                continue

        return True

    return False


def implies_brusentsov(expected: PropositionSet, observed: PropositionSet) -> Ternary:
    """Evaluate necessary implication following Brusentsov ternary logic.

    Returns:
      TRUE (1)       : Every expected atomic proposition is necessarily contained in the observed set.
      FALSE (-1)     : Any expected proposition is physically contradicted (incompatibility / nullity).
      IRRELEVANT (0) : The expected set is not implied, yet no incompatibility exists (inessential missing effect).
    """
    if len(expected) == 0:
        # Trivial fulfillment
        return Ternary.TRUE

    # 1. Incompatibility check (NULL check)
    for e in expected:
        # Check against every observed proposition
        for o in observed:
            if contradicts(e, o):
                return Ternary.FALSE

        # Object preservation check
        if e.family == "object_identity" and e.predicate == "preserved":
            is_destroyed = any(
                o.family == "object_identity"
                and o.subject_id == e.subject_id
                and o.predicate in {"destroyed", "missing", "vanished"}
                for o in observed
            )
            if is_destroyed:
                return Ternary.FALSE

    # 2. Necessary containment check (FOLLOW check)
    if all(is_necessarily_contained(e, observed) for e in expected):
        return Ternary.TRUE

    # 3. Inessential missing effect without physical contradiction (OMIT check)
    return Ternary.IRRELEVANT
