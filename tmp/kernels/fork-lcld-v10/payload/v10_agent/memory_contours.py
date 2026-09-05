"""Isolated Memory Contours enforcing invariants ISO-1 through ISO-5.

Guarantees zero cross-contamination between:
  - Factual discovery (EnvironmentSpecMemory)
  - Syntax/compilation diagnostics (SyntaxErrorMemory)
  - Epistemic/semantic judgments (EpistemicMemory)
  - Game-wide cross-level summaries (GameMemory)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from v10_agent.brusentsov_logic import BrusentsovJudgment, Ternary


class IsolationViolationError(RuntimeError):
    """Raised when an architectural memory contour invariant (ISO-1..ISO-5) is violated."""


FORBIDDEN_SYNTAX_KEYWORDS_IN_SOLVER = {
    "traceback",
    "syntaxerror",
    "typeerror",
    "nameerror",
    "attributeerror",
    "zerodivisionerror",
    "indexerror",
    "keyerror",
    "filenotfounderror",
    "runtimeerror",
    "exception:",
    "stack trace",
}

FORBIDDEN_GOAL_KEYWORDS_IN_CODER = {
    "level_goal",
    "win_condition",
    "target_score",
    "hypothesis_family",
    "epistemic_verdict",
    "brusentsov",
    "live_omit",
    "severed_null",
}


@dataclass
class ProbeRecord:
    """Record of an exploratory probe action executed in the environment."""
    probe_id: str
    action_id: str
    action_data: dict[str, Any]
    observed_effect: str
    confidence: float
    timestamp: float = field(default_factory=time.time)


@dataclass
class EnvironmentSpecMemory:
    """Memory contour for Explorer Agent.

    Stores ONLY verified factual environment discoveries and probe histories.
    Guaranteed free of planning goals or trajectory proposals (ISO-3).
    """
    game_id: str
    level_id: str
    specs: list[dict[str, Any]] = field(default_factory=list)
    probe_history: list[ProbeRecord] = field(default_factory=list)

    def record_spec(self, spec: dict[str, Any]) -> None:
        """Record an EnvironmentSpecification JSON, asserting no goals or trajectory steps exist."""
        spec_str = str(spec).lower()
        if "trajectory" in spec_str or "candidate_steps" in spec_str or "goal_statement" in spec_str:
            raise IsolationViolationError(
                "ISO-3 Violation: Explorer attempted to write planning/trajectory data into EnvironmentSpecMemory"
            )
        self.specs.append(dict(spec))

    def record_probe(self, probe: ProbeRecord) -> None:
        self.probe_history.append(probe)

    def clear_level(self, new_level_id: str) -> None:
        self.level_id = new_level_id
        # Keep high-confidence specs from previous level if general, but reset level-local specs
        self.specs.clear()
        self.probe_history.clear()


@dataclass
class SyntaxErrorRecord:
    """Diagnostic record of a failed DSL compilation or sandbox static validation."""
    prompt_hash: str
    source_code: str
    error_type: str
    error_message: str
    diagnostics: list[str] = field(default_factory=list)
    traceback_str: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt_hash": self.prompt_hash,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "diagnostics": list(self.diagnostics),
            "traceback": self.traceback_str,
            "timestamp": self.timestamp,
        }


@dataclass
class SyntaxErrorMemory:
    """Memory contour for Coder Agent.

    Stores ONLY syntactic and ontological diagnostic records.
    Guaranteed free of level goals or epistemic judgments (ISO-2).
    """
    level_id: str
    entries: list[SyntaxErrorRecord] = field(default_factory=list)
    max_entries: int = 5

    def record_error(self, record: SyntaxErrorRecord) -> None:
        """Record a syntax or validation failure, asserting no goals leak in."""
        rec_str = (record.error_message + " " + record.error_type + " " + record.source_code).lower()
        for forbidden in FORBIDDEN_GOAL_KEYWORDS_IN_CODER:
            if forbidden in rec_str:
                raise IsolationViolationError(
                    f"ISO-2 Violation: Level goal keyword {forbidden!r} leaked into SyntaxErrorMemory"
                )
        self.entries.append(record)
        if len(self.entries) > self.max_entries:
            self.entries.pop(0)

    def clear(self) -> None:
        self.entries.clear()


@dataclass
class BranchSignature:
    """A paused or active branch signature in EpistemicMemory."""
    signature_id: str
    trajectory_id: str
    last_step_id: str
    expected_propositions: list[dict[str, Any]]
    observed_propositions: list[dict[str, Any]]
    created_at: float = field(default_factory=time.time)


@dataclass
class EpistemicMemory:
    """Memory contour for Solver Agent.

    Stores ONLY Brusentsov judgments, live OMIT branches, and severed NULL branches.
    Guaranteed free of raw Python tracebacks, syntax errors, or Python source (ISO-1).
    """
    level_id: str
    judgments: list[BrusentsovJudgment] = field(default_factory=list)
    live_omit_branches: list[BranchSignature] = field(default_factory=list)
    severed_null_signatures: set[str] = field(default_factory=set)
    max_entries: int = 50

    def record_judgment(self, judgment: BrusentsovJudgment) -> None:
        """Record a Brusentsov transition judgment, strictly asserting ISO-1."""
        expl = (judgment.explanation or "").lower()
        for forbidden in FORBIDDEN_SYNTAX_KEYWORDS_IN_SOLVER:
            if forbidden in expl:
                raise IsolationViolationError(
                    f"ISO-1 Violation: Python syntax error / traceback text {forbidden!r} appeared in EpistemicMemory"
                )

        self.judgments.append(judgment)
        if len(self.judgments) > self.max_entries:
            self.judgments.pop(0)

    def pause_branch_as_omit(self, branch: BranchSignature) -> None:
        """Record an inessential missing effect as a live OMIT growth point."""
        # Ensure not already severed
        if branch.signature_id not in self.severed_null_signatures:
            self.live_omit_branches.append(branch)

    def sever_branch(self, signature_id: str) -> None:
        """Permanently sever a contradicted branch (NULL verdict)."""
        self.severed_null_signatures.add(signature_id)
        self.live_omit_branches = [b for b in self.live_omit_branches if b.signature_id != signature_id]

    def is_severed(self, signature_id: str) -> bool:
        return signature_id in self.severed_null_signatures

    def clear(self) -> None:
        self.judgments.clear()
        self.live_omit_branches.clear()
        self.severed_null_signatures.clear()


@dataclass
class GameMemory:
    """Cross-level memory summary surviving level transitions within the same game."""
    game_id: str
    confirmed_action_effects: dict[str, str] = field(default_factory=dict)
    invariant_rules: list[str] = field(default_factory=list)
    completed_levels: int = 0

    def record_action_effect(self, action_id: str, summary: str) -> None:
        self.confirmed_action_effects[action_id] = summary

    def clear(self) -> None:
        self.confirmed_action_effects.clear()
        self.invariant_rules.clear()
        self.completed_levels = 0


class MemoryContourManager:
    """Sole owner and mediator of the four memory contours (ISO-4)."""

    def __init__(self, game_id: str = "init_game", level_id: str = "init_level"):
        self.env_spec_memory = EnvironmentSpecMemory(game_id=game_id, level_id=level_id)
        self.syntax_error_memory = SyntaxErrorMemory(level_id=level_id)
        self.epistemic_memory = EpistemicMemory(level_id=level_id)
        self.game_memory = GameMemory(game_id=game_id)

    def get_env_spec_memory(self, caller_role: str) -> EnvironmentSpecMemory:
        """Authorized for Explorer and GameSession only."""
        if caller_role not in {"explorer", "session"}:
            raise IsolationViolationError(
                f"ISO-4 Violation: Role {caller_role!r} is not permitted to access EnvironmentSpecMemory"
            )
        return self.env_spec_memory

    def get_syntax_error_memory(self, caller_role: str) -> SyntaxErrorMemory:
        """Authorized for Coder and GameSession only."""
        if caller_role not in {"coder", "session"}:
            raise IsolationViolationError(
                f"ISO-4 Violation: Role {caller_role!r} is not permitted to access SyntaxErrorMemory"
            )
        return self.syntax_error_memory

    def get_epistemic_memory(self, caller_role: str) -> EpistemicMemory:
        """Authorized for Solver and GameSession only."""
        if caller_role not in {"solver", "session"}:
            raise IsolationViolationError(
                f"ISO-4 Violation: Role {caller_role!r} is not permitted to access EpistemicMemory"
            )
        return self.epistemic_memory

    def get_game_memory(self, caller_role: str) -> GameMemory:
        """Authorized for GameSession only."""
        if caller_role != "session":
            raise IsolationViolationError(
                f"ISO-4 Violation: Role {caller_role!r} is not permitted to access GameMemory"
            )
        return self.game_memory

    def handle_level_transition(self, new_level_id: str) -> None:
        """Preserve GameMemory, summarize EpistemicMemory, clear SyntaxErrorMemory."""
        self.syntax_error_memory.clear()
        self.epistemic_memory.clear()
        self.env_spec_memory.clear_level(new_level_id)
        self.game_memory.completed_levels += 1

    def handle_game_transition(self, new_game_id: str, new_level_id: str) -> None:
        """Completely reset all contours when switching games."""
        self.env_spec_memory = EnvironmentSpecMemory(game_id=new_game_id, level_id=new_level_id)
        self.syntax_error_memory = SyntaxErrorMemory(level_id=new_level_id)
        self.epistemic_memory = EpistemicMemory(level_id=new_level_id)
        self.game_memory = GameMemory(game_id=new_game_id)
