"""Domain data types and data contracts for ARC-AGI-3 LCLD Agent V10.0."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

Grid2D = list[list[int]]
PlanningObjectId = str
PlanningAlias = str


@dataclass(frozen=True)
class BoundingBox:
    """Bounding box defined by inclusive row and column coordinates."""
    min_row: int
    min_col: int
    max_row: int
    max_col: int

    @property
    def height(self) -> int:
        return self.max_row - self.min_row + 1

    @property
    def width(self) -> int:
        return self.max_col - self.min_col + 1

    @property
    def area(self) -> int:
        return self.height * self.width

    def to_dict(self) -> dict[str, int]:
        return {
            "min_row": self.min_row,
            "min_col": self.min_col,
            "max_row": self.max_row,
            "max_col": self.max_col,
            "height": self.height,
            "width": self.width,
        }


@dataclass(frozen=True)
class Centroid:
    """Centroid of an object or region in row/column coordinates."""
    row: float
    col: float

    def to_dict(self) -> dict[str, float]:
        return {"row": round(self.row, 2), "col": round(self.col, 2)}


@dataclass(frozen=True)
class CoordinateCandidate:
    """A spatial point candidate grounded on the PlanningSet."""
    candidate_id: str
    x: int  # column index (0-indexed)
    y: int  # row index (0-indexed)
    source_type: str  # e.g., "centroid", "corner_tl", "corner_br", "grid_center"
    object_id: str | None = None
    label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "x": self.x,
            "y": self.y,
            "source_type": self.source_type,
            "object_id": self.object_id,
            "label": self.label,
        }


@dataclass
class ActionDeclaration:
    """Declaration of an intended environment action."""
    action_id: str  # "ACTION1" .. "ACTION7", "RESET"
    data: dict[str, Any] = field(default_factory=dict)
    reasoning: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "data": dict(self.data),
            "reasoning": dict(self.reasoning),
        }


@dataclass
class EffectDeclaration:
    """Declaration of an expected transition effect produced by a DSL function."""
    declared_action: ActionDeclaration
    expected_metric_deltas: dict[str, int | float] = field(default_factory=dict)
    target_object_ids: list[str] = field(default_factory=list)
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "declared_action": self.declared_action.to_dict(),
            "expected_metric_deltas": dict(self.expected_metric_deltas),
            "target_object_ids": list(self.target_object_ids),
            "confidence": self.confidence,
        }


REGISTERED_PROPOSITION_FAMILIES = frozenset({
    "object_identity",
    "attribute_delta",
    "metric_sign",
    "relation_existence",
    "action_surface",
    "terminal_metadata",
    "affordance_flag",
})

PropositionFamily = str


@dataclass(frozen=True)
class AtomicProposition:
    """An atomic proposition grounded on PlanningSet identifiers.
    
    Raw grid pixels are never propositions. Only registered families are valid.
    """
    family: PropositionFamily
    subject_id: str
    predicate: str
    value: Any = None
    secondary_id: str | None = None

    def __post_init__(self) -> None:
        if self.family not in REGISTERED_PROPOSITION_FAMILIES:
            raise ValueError(
                f"Unknown proposition family {self.family!r}. Must be one of {REGISTERED_PROPOSITION_FAMILIES}"
            )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "family": self.family,
            "subject_id": self.subject_id,
            "predicate": self.predicate,
        }
        if self.value is not None:
            out["value"] = self.value
        if self.secondary_id is not None:
            out["secondary_id"] = self.secondary_id
        return out


@dataclass(frozen=True)
class PropositionSet:
    """An immutable set of AtomicPropositions."""
    propositions: frozenset[AtomicProposition] = field(default_factory=frozenset)

    @classmethod
    def from_iterable(cls, items: Iterable[AtomicProposition]) -> PropositionSet:
        return cls(frozenset(items))

    def union(self, other: PropositionSet) -> PropositionSet:
        return PropositionSet(self.propositions | other.propositions)

    def intersection(self, other: PropositionSet) -> PropositionSet:
        return PropositionSet(self.propositions & other.propositions)

    def difference(self, other: PropositionSet) -> PropositionSet:
        return PropositionSet(self.propositions - other.propositions)

    def filter_family(self, family: str) -> PropositionSet:
        return PropositionSet(frozenset(p for p in self.propositions if p.family == family))

    def __contains__(self, item: AtomicProposition) -> bool:
        return item in self.propositions

    def __len__(self) -> int:
        return len(self.propositions)

    def __iter__(self) -> Iterable[AtomicProposition]:
        return iter(self.propositions)

    def to_list(self) -> list[dict[str, Any]]:
        return [p.to_dict() for p in sorted(self.propositions, key=lambda p: (p.family, p.subject_id, p.predicate))]
