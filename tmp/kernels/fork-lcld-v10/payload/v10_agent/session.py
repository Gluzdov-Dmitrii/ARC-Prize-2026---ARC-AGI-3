"""GameSession: Master orchestrator of the Tri-Agent pipeline & Double-Loop feedback routing."""

from __future__ import annotations

import logging
import time
from typing import Any, Mapping

from v10_agent.action_adapter import to_native_action
from v10_agent.arga_lite import ARGALiteSnapshot, extract_arga_snapshot
from v10_agent.config import V10Config, config_from_mapping
from v10_agent.dsl_coder import DSLCoder
from v10_agent.explorer_agent import ExplorerAgent
from v10_agent.fallback_symbolic import SymbolicFallbackEngine
from v10_agent.judge import LayeredVerifier
from v10_agent.llm_advisor import BaseLLMAdvisor, build_llm_advisor
from v10_agent.logging import StructuredAuditLogger
from v10_agent.memory_contours import BranchSignature, MemoryContourManager
from v10_agent.observe import grid_to_hex_rows, normalize_observation
from v10_agent.planning_set import PlanningSet, build_planning_set
from v10_agent.policy import ActionSelectionPolicy
from v10_agent.sandbox import SandboxedModule, SandboxExecutor
from v10_agent.solver_agent import SolverAgent
from v10_agent.trajectory import TrajectoryPool
from v10_agent.types import EffectDeclaration
from v10_agent.verification import GroundedStep, GroundingError, VerificationBinder

logger = logging.getLogger(__name__)


class GameSession:
    """Sole mutable-state owner and orchestrator of Explorer, Coder, Solver, and Verifier."""

    def __init__(
        self,
        config: V10Config | None = None,
        advisor: BaseLLMAdvisor | None = None,
    ):
        self.config = config or V10Config()
        self.advisor = advisor or build_llm_advisor(self.config)

        # Contours & Services
        self.memory_manager = MemoryContourManager()
        self.sandbox_executor = SandboxExecutor(
            allowed_modules=self.config.sandbox_allowed_modules,
            timeout_seconds=self.config.sandbox_max_cpu_seconds,
        )
        self.binder = VerificationBinder()
        self.verifier = LayeredVerifier(self.config)
        self.fallback_engine = SymbolicFallbackEngine(self.config)
        self.policy = ActionSelectionPolicy()
        self.audit_logger = StructuredAuditLogger()

        # Agents
        self.explorer = ExplorerAgent(self.config, self.advisor)
        self.coder = DSLCoder(self.config, self.advisor, self.sandbox_executor)
        self.solver = SolverAgent(self.config, self.advisor)

        # Active Session State
        self.active_module: SandboxedModule | None = None
        self.active_manifest: dict[str, Any] | None = None
        self.active_pool: TrajectoryPool | None = None

        self.last_snapshot: ARGALiteSnapshot | None = None
        self.last_planning_set: PlanningSet | None = None
        self.pending_step: GroundedStep | None = None
        self.pending_action: dict[str, Any] | None = None

        self.game_over_reset_count: int = 0
        self.last_engine_action: str = ""
        self.current_level_id: str = "level_0"
        self.current_game_id: str = "game_0"
        self.accepted_action_count: int = 0
        self.levels_completed_observed: int = 0
        self.observed_transition_ingestions: int = 0
        self.observed_transition_duplicate_skips: int = 0

    def update_runtime_config(self, updates: Mapping[str, Any]) -> None:
        """Dynamically update runtime configuration without destroying session memory."""
        self.config.update_runtime(updates)

    def handle_level_transition(self, new_level_id: str) -> None:
        """Clean level-local state, preserve GameMemory cross-level invariants."""
        self.current_level_id = new_level_id
        self.active_module = None
        self.active_manifest = None
        self.active_pool = None
        self.pending_step = None
        self.pending_action = None
        self.memory_manager.handle_level_transition(new_level_id)
        logger.info(f"Transitioned to new level {new_level_id}; GameMemory preserved.")

    def handle_game_transition(self, new_game_id: str) -> None:
        """Reset all contours when switching games."""
        self.current_game_id = new_game_id
        self.current_level_id = "level_0"
        self.active_module = None
        self.active_manifest = None
        self.active_pool = None
        self.pending_step = None
        self.pending_action = None
        self.memory_manager.handle_game_transition(new_game_id, self.current_level_id)
        logger.info(f"Reset session for new game {new_game_id}.")

    def act(self, raw_observation: Mapping[str, Any]) -> dict[str, Any]:
        """Propose the single next environment action."""
        obs = normalize_observation(raw_observation, frame_index=self.accepted_action_count, game_id=self.current_game_id)
        state_name = obs["state"]

        # 1. Exact Tufa GAME_OVER single RESET Invariant
        if state_name == "GAME_OVER":
            if self.last_engine_action == "RESET":
                logger.error("GAME_OVER persisted after single RESET. Forcing loop break.")
                raise RuntimeError("GAME_OVER persisted after single RESET")

            self.game_over_reset_count += 1
            reset_action = {
                "id": "RESET",
                "action_id": "RESET",
                "data": {},
                "reasoning": {"source": "tufa_game_over_auto_reset", "reset_count": self.game_over_reset_count},
            }
            self.pending_action = reset_action
            self.last_engine_action = "RESET"
            self.pending_step = None
            return reset_action

        # Check for level change
        observed_levels = obs["levels_completed"]
        if observed_levels > self.levels_completed_observed:
            self.levels_completed_observed = observed_levels
            self.handle_level_transition(f"level_{observed_levels}")

        # 2. Perception & PlanningSet Construction
        grid = obs["grid"]
        snapshot = extract_arga_snapshot(grid)
        hex_rows = grid_to_hex_rows(grid)
        planning_set = build_planning_set(
            snapshot=snapshot,
            available_actions=obs["available_actions"],
            grid_hex_rows=hex_rows,
        )

        env_mem = self.memory_manager.get_env_spec_memory("session")
        syntax_mem = self.memory_manager.get_syntax_error_memory("session")
        ep_mem = self.memory_manager.get_epistemic_memory("session")

        # 3. Explorer Phase (if first time on level or budget allows)
        if not env_mem.specs and self.config.max_explorer_probe_actions_per_level > 0:
            self.explorer.generate_environment_spec(planning_set, env_mem)

        # 4. Coder Phase (if no certified DSL exists)
        if self.active_module is None:
            spec = env_mem.specs[0] if env_mem.specs else {}
            module, manifest, errors = self.coder.generate_dsl(spec, syntax_mem, planning_set)
            if module is not None and manifest is not None:
                self.active_module = module
                self.active_manifest = manifest
            else:
                logger.warning("Coder retries exhausted or failed. Fallback engaged.")

        # 5. Solver Phase (if certified DSL exists and pool empty)
        if self.active_module is not None and self.active_pool is None:
            pkg = self.solver.generate_trajectory_package(
                manifest=self.active_manifest or {},
                planning_set=planning_set,
                epistemic_memory=ep_mem,
                budget=max(1, self.config.max_actions_per_level - self.accepted_action_count),
            )
            if pkg is not None:
                self.active_pool = TrajectoryPool.from_package(pkg)

        # 6. Step Selection (Policy)
        step_dict, strategy = self.policy.select_next_step(
            pool=self.active_pool,
            epistemic_memory=ep_mem,
            planning_set=planning_set,
        )

        effect: EffectDeclaration | None = None
        grounded_step: GroundedStep | None = None

        # Try to execute Solver step inside Sandbox
        if step_dict is not None and self.active_module is not None:
            try:
                grounded_step = self.binder.ground_step(step_dict, planning_set)
                effect = self.sandbox_executor.execute(
                    module=self.active_module,
                    function_name=grounded_step.dsl_function,
                    arguments=grounded_step.arguments,
                    planning_set=planning_set,
                )
            except Exception as exc:
                # External loop routing: syntax / execution errors travel ONLY to SyntaxErrorMemory
                logger.warning(f"Sandbox step execution failed ({type(exc).__name__}): {exc}")
                syntax_mem.record_error(
                    SyntaxErrorRecord(
                        prompt_hash="",
                        source_code=self.active_module.source if self.active_module else "",
                        error_type=type(exc).__name__,
                        error_message=str(exc),
                    )
                )
                effect = None
                grounded_step = None

        # 7. Fallback Path (if step execution failed or fallback chosen)
        if effect is None:
            effect = self.fallback_engine.select_fallback_action(planning_set)
            grounded_step = None

        # 8. ActionBoundary: emit strictly one step
        action_decl = effect.declared_action
        action_dict = {
            "id": action_decl.action_id,
            "action_id": action_decl.action_id,
            "data": action_decl.data,
            "reasoning": action_decl.reasoning,
        }

        self.last_snapshot = snapshot
        self.last_planning_set = planning_set
        self.pending_step = grounded_step
        self.pending_action = action_dict
        self.last_engine_action = action_decl.action_id

        # Audit Log
        self.audit_logger.log(
            "action_emitted",
            action=action_decl.action_id,
            data=action_decl.data,
            strategy=strategy,
            grid_hash=planning_set.grid_hash,
            level_id=self.current_level_id,
        )

        return action_dict

    def observe_action_result(self, after_observation: Mapping[str, Any] | None = None) -> bool:
        """Commit the transition result and evaluate Brusentsov ternary judgment."""
        if self.pending_action is None:
            self.observed_transition_duplicate_skips += 1
            return False

        if after_observation is None:
            self.observed_transition_duplicate_skips += 1
            return False

        norm_after = normalize_observation(after_observation, game_id=self.current_game_id)
        self.accepted_action_count += 1
        self.observed_transition_ingestions += 1

        # Evaluate transition if a grounded solver step was pending
        if self.pending_step is not None and self.last_snapshot is not None and self.last_planning_set is not None:
            judgment = self.verifier.evaluate_transition(
                step=self.pending_step,
                before_snapshot=self.last_snapshot,
                after_obs=norm_after,
                planning_set=self.last_planning_set,
            )

            # Internal loop routing: judgments travel ONLY to EpistemicMemory
            ep_mem = self.memory_manager.get_epistemic_memory("session")
            ep_mem.record_judgment(judgment)

            # Update trajectory pool cursors
            from v10_agent.brusentsov_logic import Ternary
            if judgment.verdict == Ternary.TRUE:
                # FOLLOW: advance cursor
                if self.active_pool and self.active_pool.active_candidate():
                    self.active_pool.active_candidate().advance()
            elif judgment.verdict == Ternary.FALSE:
                # NULL: sever branch
                if self.active_pool and self.active_pool.active_candidate():
                    self.active_pool.active_candidate().sever()
                ep_mem.sever_branch(self.pending_step.step_id)
            elif judgment.verdict == Ternary.IRRELEVANT:
                # OMIT: pause branch for potential future pivot
                ep_mem.pause_branch_as_omit(
                    BranchSignature(
                        signature_id=self.pending_step.step_id,
                        trajectory_id=self.pending_step.step_id,
                        last_step_id=self.pending_step.step_id,
                        expected_propositions=self.pending_step.expected_propositions.to_list(),
                        observed_propositions=judgment.observed_propositions.to_list(),
                    )
                )

        # Clear pending action references for next cycle
        self.pending_action = None
        self.pending_step = None
        return True

    def harness_telemetry(self) -> dict[str, Any]:
        """Return structured telemetry for competition harness."""
        ep_mem = self.memory_manager.get_epistemic_memory("session")
        return {
            "accepted_action_count": self.accepted_action_count,
            "levels_completed": self.levels_completed_observed,
            "game_over_reset_count": self.game_over_reset_count,
            "observed_transition_ingestions": self.observed_transition_ingestions,
            "observed_transition_duplicate_skips": self.observed_transition_duplicate_skips,
            "epistemic_judgments_count": len(ep_mem.judgments),
            "live_omit_branches_count": len(ep_mem.live_omit_branches),
            "severed_null_signatures_count": len(ep_mem.severed_null_signatures),
            "current_level_id": self.current_level_id,
            "current_game_id": self.current_game_id,
        }
