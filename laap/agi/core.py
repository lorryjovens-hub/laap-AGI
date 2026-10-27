"""
LAAP AGI — Unified Core Agent (统一AGI核心)

The culmination: an AGIAgent that integrates all AGI modules into a
single, coherent, production-ready digital lifeform.

This is not a demo. This is a framework designed to run for days,
process thousands of interactions, and genuinely learn and grow.

Architecture:
  ┌────────────────────────────────────────────────────────────┐
  │                      AGI AGENT                              │
  ├────────────────────────────────────────────────────────────┤
  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
  │  │  World   │  │  Self    │  │  Causal  │  │Analogic │  │
  │  │  Model   │  │  Model   │  │  Engine  │  │ Engine  │  │
  │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  │
  │       └──────────────┼─────────────┼─────────────┘        │
  │                      │             │                       │
  │  ┌──────────┐  ┌─────┴─────┐  ┌───┴───────┐  ┌─────────┐ │
  │  │ Learning │  │ Autonomy  │  │ Conscious │  │ Bridge  │ │
  │  │ Pipeline │  │ Engine    │  │ Stream    │  │ (Hermes)│ │
  │  └────┬─────┘  └─────┬─────┘  └─────┬─────┘  └────┬────┘ │
  │       └──────────────┼──────────────┼──────────────┘      │
  │                      │              │                      │
  │  ┌───────────────────┴──────────────┴──────────────────┐  │
  │  │              Event Bus (reactive integration)        │  │
  │  └─────────────────────────────────────────────────────┘  │
  │  ┌──────────────────────────────────────────────────────┐ │
  │  │              Persistence Layer (JSON state)          │ │
  │  └──────────────────────────────────────────────────────┘ │
  └────────────────────────────────────────────────────────────┘

Usage:
    from laap.agi.core import AGIAgent

    agent = AGIAgent(name="Ao", state_dir="./agi_state")

    # Every interaction flows through this central method:
    result = agent.process_interaction(
        user_message="What is the weather?",
        domain="weather_query",
    )

    # Get comprehensive state
    state = agent.get_state()

    # Save/Load
    agent.save()
    agent.load()
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple, Callable
import time, logging, json, os, threading
from pathlib import Path
from collections import defaultdict

from laap.agi.world_model import (
    create_world_model, WorldModelType, EntityType, RelationType,
    AbstractWorldModel, LocalWorldModel
)
from laap.agi.self_model import EmergentSelfModel
from laap.agi.causal import CausalEngine
from laap.agi.analogical import AnalogicalEngine
from laap.agi.continuous_learning import LearningPipeline
from laap.agi.autonomy import AutonomousEngine, GoalSource, GoalPriority
from laap.agi.conscious import (
    ConsciousStream, AttentionFocus, EmotionalValence,
)
from laap.agi.memory_system import EpisodicMemory, SemanticMemory, ProceduralMemory, MemoryConsolidator
from laap.agi.evolution_system import EvolutionSystem
from laap.agi.security_system import SecuritySystem
from laap.agi.code_evolution import CodeEvolutionEngine
from laap.agi.self_healing import AutoHealer
from laap.agi.quality_assurance import QualityAssurance
from laap.agi.code_minimizer import CodeMinimizer
from laap.agi.multi_agent import AgentRegistry, TaskBoard, SafeRollback
from laap.agi.hermes_integration import HermesIntegration
from laap.agi.psi_driver import PSIDriver, integrate_psi_driver
from laap.agi.cognitive_bus import (
    CognitiveBus, integrate_cognitive_bus,
    AttentionFocus as BusAttentionFocus,
    EmotionalValence as BusEmotionalValence,
    CognitiveEventType,
)
from laap.agi.gw_workspace import GlobalWorkspace, CoalitionalProcess, ProcessType
from laap.agi.affective_engine import AffectiveState, AffectiveEventProcessor, PersonalityProfile, EmotionDimension
from laap.agi.meta_cognitive import MetaCognitiveMonitor, CognitiveEpisode, ReflectionTrigger
from laap.agi.consciousness_integrator import ConsciousnessHarness, ConsciousContext
from laap.agi.unified_memory import UnifiedMemory

logger = logging.getLogger("laap.agi.core")

# ════════════════════════════════════════════════════════════
# AGI Agent
# ════════════════════════════════════════════════════════════

class AGIAgent:
    """
    Unified AGI agent integrating all cognitive modules.

    This is the production-ready orchestrator that ties together
    WorldModel, SelfModel, CausalEngine, AnalogicalEngine,
    LearningPipeline, AutonomousEngine, and ConsciousStream
    into a single coherent agent.
    """

    def __init__(self, name: str = "Ao",
                 state_dir: str = None,
                 enable_all: bool = True,
                 world_model_type: str = "hybrid"):
        """
        Initialize the AGI agent with all cognitive modules.

        Args:
            name: Agent's name (used across all modules for identity)
            state_dir: Directory for persistent state (None = no persistence)
            enable_all: Enable all modules by default
            world_model_type: World model type ("hybrid", "genesis", "local", etc.)
        """
        self.name = name
        self.state_dir = Path(state_dir) if state_dir else None
        self.created_at = time.time()
        self.version = "3.0.0"
        self._world_model_type = world_model_type

        # ── Core Modules ──
        self.world: Optional[AbstractWorldModel] = None
        self.self_model: Optional[EmergentSelfModel] = None
        self.causal: Optional[CausalEngine] = None
        self.analogical: Optional[AnalogicalEngine] = None
        self.learning: Optional[LearningPipeline] = None
        self.autonomy: Optional[AutonomousEngine] = None
        self.conscious: Optional[ConsciousStream] = None
        self.consciousness_harness: Optional[ConsciousnessHarness] = None
        self.unified_memory: Optional[UnifiedMemory] = None

        # ── Cognitive Bus (central nervous system) ──
        self.cognitive_bus: Optional[CognitiveBus] = None

        # ── Interaction tracking ──
        self.total_interactions = 0
        self.interaction_history: List[Dict[str, Any]] = []
        self._interaction_lock = threading.Lock()

        # ── Initialize ──
        if enable_all:
            self._init_all_modules()

        # Try to load previous state
        self._load_if_exists()

        logger.info(f"AGIAgent '{name}' v{self.version} initialized "
                     f"with {self._module_count()} modules")

    def _init_all_modules(self):
        """Initialize all cognitive modules."""
        # 世界模型：根据 type 参数选择（genesis / hybrid / local 等）
        wm_type = getattr(self, '_world_model_type', 'hybrid')
        self.world = create_world_model(wm_type, name=f"{self.name}-world")
        self.self_model = EmergentSelfModel(agent_name=self.name)
        self.causal = CausalEngine(name=f"{self.name}-causal")
        self.analogical = AnalogicalEngine(name=f"{self.name}-analogy")
        self.learning = LearningPipeline(name=f"{self.name}-learn")
        self.autonomy = AutonomousEngine(name=f"{self.name}-auto")
        self.conscious = ConsciousStream(agent_name=self.name)
        self.memory_system = EpisodicMemory()
        self.evolution = EvolutionSystem(name=f"{self.name}-evo")
        self.security = SecuritySystem(name=f"{self.name}-sec")
        self.hermes = HermesIntegration()
        _root = os.environ.get("LAAP_ROOT", "")
        if not _root:
            _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.agent_registry = AgentRegistry(registry_path=os.path.join(_root, ".agent_registry.json"))
        self.task_board = TaskBoard(board_path=os.path.join(_root, ".task_board.json"))
        self.safe_rollback = SafeRollback(repo_root=_root)
        self.code_minimizer = CodeMinimizer(repo_root=_root)
        self.quality_assurance = QualityAssurance(repo_root=_root)
        self.self_healing = AutoHealer(repo_root=_root)
        self.code_evolution = CodeEvolutionEngine(
            repo_root=_root,
            llm_fn=getattr(self.hermes, 'llm_generate_patch_for_target', None),
        )

        # ── Consciousness Harness & Unified Memory ──
        self.consciousness_harness = ConsciousnessHarness()
        self.consciousness_harness.initialize_personality()
        self.unified_memory = UnifiedMemory()

        # ── Initialize Cognitive Bus (central nervous system) ──
        self.cognitive_bus = CognitiveBus(agent_name=self.name)
        self._register_modules_on_bus()

        # ── P0-1: 打通世界模型 ↔ 因果引擎的连接 ──
        # 原 AGIAgent 创建了 self.world 和 self.causal 但从未连接,
        # 导致 UnifiedWorldModel.predict 中的 self._causal_engine 永远为 None,
        # 因果反事实推演能力空转。此桥接让两套子系统协同工作。
        if self.world is not None and self.causal is not None:
            try:
                self.world.set_causal_engine(self.causal)
                logger.info(f"[{self.name}] 世界模型 ↔ 因果引擎已连接")
            except Exception as e:
                logger.warning(f"[{self.name}] set_causal_engine 失败: {e}")

    def _register_modules_on_bus(self):
        """Register all existing cognitive modules on the bus."""
        if not self.cognitive_bus:
            return

        module_map = [
            ('world', 'world_model', ['perception', 'prediction', 'simulation']),
            ('self_model', 'self_model', ['self_assessment', 'confidence_calibration']),
            ('causal', 'causal_engine', ['causal_reasoning', 'do_calculus', 'counterfactual']),
            ('analogical', 'analogical_engine', ['structure_mapping', 'analogy_transfer']),
            ('conscious', 'conscious_stream', ['attention', 'qualia', 'narrative']),
            ('memory_system', 'memory_system', ['storage', 'recall', 'consolidation']),
            ('learning', 'learning_pipeline', ['experience_replay', 'skill_extraction']),
            ('autonomy', 'autonomy_engine', ['goal_management', 'planning']),
            ('evolution', 'evolution_system', ['self_improvement', 'proposals']),
            ('security', 'security_system', ['threat_detection', 'access_control']),
            ('consciousness_harness', 'consciousness_harness', ['global_workspace', 'affective', 'meta_cognitive']),
            ('unified_memory', 'unified_memory', ['working', 'episodic', 'semantic', 'procedural']),
        ]

        for attr, module_name, capabilities in module_map:
            mod = getattr(self, attr, None)
            if mod is not None:
                version = getattr(mod, 'version', '1.0.0') or '1.0.0'
                self.cognitive_bus.register_module(
                    module_name, version=version, capabilities=capabilities
                )

        # Register code evolution and other infra modules
        for name, attr in [
            ('code_evolution', 'code_evolution'),
            ('self_healing', 'self_healing'),
            ('quality_assurance', 'quality_assurance'),
            ('code_minimizer', 'code_minimizer'),
        ]:
            mod = getattr(self, attr, None)
            if mod is not None:
                self.cognitive_bus.register_module(name, capabilities=[name])

        logger.info(
            f"Registered {len(self.cognitive_bus._modules)} modules on CognitiveBus"
        )

    def _module_count(self) -> int:
        return sum(1 for m in [
            self.world, self.self_model, self.causal,
            self.analogical, self.learning, self.autonomy, self.conscious,
            self.memory_system, self.evolution, self.security,
            self.hermes, self.code_evolution, self.self_healing, self.quality_assurance, self.code_minimizer, self.agent_registry, self.task_board, self.safe_rollback,
            self.consciousness_harness, self.unified_memory,
        ] if m is not None)

    # ════════════════════════════════════════════════════════
    # Main Interaction Pipeline
    # ════════════════════════════════════════════════════════

    def process_interaction(self, user_message: str,
                            domain: str = "general",
                            context: Dict[str, Any] = None,
                            action_outcome: Dict[str, Any] = None,
                            use_psi: bool = True  # NOW DEFAULT: PSI cycle is the core
                            ) -> Dict[str, Any]:
        """
        PSI-driven cognitive processing pipeline — the ONE true entry point.

        Flow (PSI cycle integrated with CognitiveBus):
          0. Consciousness Harness → process input through global workspace
          1. Perceive → register on bus → conscious frame opens
          2. Select   → bus needs + emotion → attention focus chosen
          3. Predict  → world model predicts → bus registers prediction
          4. Integrate → bind all signals → unified cognitive snapshot
          5. Assess   → self-model evaluates → confidence calibration
          6. Reason   → causal + analogical reasoning
          7. Learn    → prediction error → update all modules
          8. Respond  → generate output (LLM is I/O channel here)

        The CognitiveBus holds ALL state. Modules read from it, not from each other.

        Args:
            user_message: The user's input
            domain: Task domain
            context: Additional context
            action_outcome: Result of any previous action (for learning)
            use_psi: Use PSI cognitive cycle (True by default now)

        Returns:
            Comprehensive interaction report with full cognitive state
        """
        ctx = context or {}
        start_time = time.time()

        result = {"interaction_id": self.total_interactions}

        with self._interaction_lock:
            self.total_interactions += 1

            # ─── Phase 0: Consciousness Harness Processing ───────
            if self.consciousness_harness:
                try:
                    import asyncio
                    conscious_context = asyncio.run(
                        self.consciousness_harness.process_input(user_message, ctx)
                    )
                    result["consciousness_harness"] = {
                        "mood": conscious_context.mood_label,
                        "attention_focus": conscious_context.attention_focus,
                        "emotional_state": conscious_context.emotional_state,
                        "cognitive_biases": conscious_context.cognitive_biases,
                    }
                except Exception as e:
                    logger.warning(f"ConsciousnessHarness process_input failed: {e}")

            # ─── Phase 0.5: Cognitive Bus Tick ───────────────────
            if self.cognitive_bus:
                # Let the bus run one cycle first (needs decay, emotion update)
                bus_snapshot = self.cognitive_bus.tick()

                # If the PSI cycle is ON, the bus drives attention selection
                if use_psi:
                    self._psi_select_attention(bus_snapshot, user_message, domain, ctx)

            # ════════════════════════════════════════════════════
            # Phase 1: PERCEIVE — register input on the bus
            # ════════════════════════════════════════════════════
            if self.conscious:
                quale = self.conscious.experience(
                    user_message,
                    modality="perception",
                    intensity=ctx.get("intensity", 0.5),
                    context={"novelty": ctx.get("novelty", 0.5)},
                )
                result["conscious"] = {
                    "quale": quale.to_summary(),
                    "attention": self.conscious.attention.current_focus.value,
                }

            # Publish perception event on bus
            if self.cognitive_bus:
                self.cognitive_bus.publish(
                    CognitiveEventType.PERCEPTION_INCOMING,
                    "core",
                    {"message": user_message[:200], "domain": domain}
                )
                # Update needs based on perception (user interaction = relatedness boost)
                self.cognitive_bus.set_needs(relatedness=min(0.92,
                    self.cognitive_bus.needs.relatedness + 0.03))
                # Novelty drops certainty (PSI: unfamiliar situations reduce certainty)
                novelty = ctx.get("novelty", 0.3)
                if novelty > 0.5:
                    self.cognitive_bus.set_needs(certainty=max(0.1,
                        self.cognitive_bus.needs.certainty - novelty * 0.1))

            # ════════════════════════════════════════════════════
            # Phase 2: PREDICT — world model generates prediction
            # ════════════════════════════════════════════════════
            prediction = None
            if self.world:
                self.world.add_entity(
                    f"interaction_{self.total_interactions}",
                    EntityType.EVENT,
                    properties={
                        "message": user_message[:200],
                        "domain": domain,
                        "timestamp": time.time(),
                    },
                    source="user_message",
                )

                prediction = self.world.predict(
                    user_message[:100],
                    context={**ctx, "domain": domain},
                )
                result["prediction"] = {
                    "confidence": round(prediction.confidence, 2),
                    "steps": len(prediction.steps),
                    "assumptions": prediction.assumptions[:3],
                }

            # ════════════════════════════════════════════════════
            # Phase 3: CAUSAL REASONING
            # ════════════════════════════════════════════════════
            if self.causal and self.world:
                try:
                    # P0-1: 原 build_from_world_model 方法不存在,改为
                    # 从世界模型实体/关系抽取因果键(causal bonds)注入因果引擎
                    edges_built = 0
                    if hasattr(self.world, 'unified'):
                        for rel in self.world.unified.relations.values():
                            if rel.relation_type == RelationType.CAUSAL:
                                try:
                                    self.causal.learn_bond(
                                        action=rel.source_id,
                                        target=rel.target_id,
                                        effect=f"{rel.source_id}->{rel.target_id}",
                                        strength=rel.strength,
                                        confidence=rel.strength,
                                        domain="world_model",
                                    )
                                    edges_built += 1
                                except Exception:
                                    pass
                    result["causal"] = {"edges_built": edges_built}
                except Exception as e:
                    result["causal"] = {"status": "no_causal_data"}

            # ════════════════════════════════════════════════════
            # Phase 4: SELF-ASSESS — calibrate via self-model
            # ════════════════════════════════════════════════════
            if self.self_model:
                readiness = self.self_model.self_assess(domain)
                result["self_assessment"] = {
                    "ready": readiness.get("ready", True),
                    "proficiency": readiness.get("proficiency", "unknown"),
                    "confidence": readiness.get("confidence", "moderate"),
                    "advice": readiness.get("advice", ""),
                }

                # Bus: update competence need based on self-assessment
                if self.cognitive_bus:
                    confidence_map = {"high": 0.8, "moderate": 0.5, "low": 0.2}
                    conf = confidence_map.get(
                        readiness.get("confidence", "moderate"), 0.5
                    )
                    self.cognitive_bus.set_needs(competence=conf)
                    self.cognitive_bus.module_heartbeat("self_model")

            # ════════════════════════════════════════════════════
            # Phase 5: LEARN from action outcome
            # ════════════════════════════════════════════════════
            if action_outcome and self.learning and self.self_model:
                outcome_score = action_outcome.get("score", 0.5)
                is_success = action_outcome.get("success", outcome_score >= 0.5)
                predicted_conf = action_outcome.get("predicted_confidence", 0.5)

                learn_result = self.learning.learn(
                    domain=domain,
                    action=action_outcome.get("action", user_message[:80]),
                    outcome=outcome_score,
                    strategy_used=action_outcome.get("strategy"),
                    lessons=action_outcome.get("lessons", []),
                )
                result["learning"] = {
                    "stored": learn_result["experience_stored"],
                    "strategies": learn_result["strategies_recommended"][:2],
                    "new_skills": learn_result.get("new_skills_consolidated", 0),
                }

                # Update self-model
                self.self_model.record_experience(
                    domain=domain,
                    outcome_score=outcome_score,
                    predicted_confidence=predicted_conf,
                    is_success=is_success,
                    was_surprising=abs(outcome_score - predicted_conf) > 0.3,
                    emotional_impact=outcome_score - 0.5,
                    description=action_outcome.get("action", user_message[:80]),
                )

                # ═══ PREDICTION ERROR LOOP ═══
                # This is the key AGI learning signal:
                # prediction confidence vs actual outcome → bus gets the error
                if self.cognitive_bus and prediction is not None:
                    predicted_val = prediction.confidence
                    actual_val = outcome_score
                    self.cognitive_bus.report_prediction_error(
                        domain=domain,
                        predicted=predicted_val,
                        actual=actual_val,
                        source="core.process_interaction",
                    )
                    # Also feed into GlobalWorkspace as a surprise channel
                    if self.conscious:
                        error_mag = abs(actual_val - predicted_val)
                        if error_mag > 0.3:  # Significant prediction error
                            self.conscious.experience(
                                content=f"Prediction error in {domain}: expected {predicted_val:.2f}, got {actual_val:.2f}",
                                modality="prediction",
                                intensity=min(1.0, error_mag * 1.5),
                                context={
                                    "channel": "prediction_error",
                                    "novelty": error_mag,
                                    "urgency": error_mag * 0.8,
                                    "emotional_weight": error_mag * 0.6,
                                    "source_module": "core.process_interaction",
                                }
                            )

            # ════════════════════════════════════════════════════
            # Phase 6: ANALOGICAL TRANSFER
            # ════════════════════════════════════════════════════
            if self.analogical and self.world:
                analogies = self.analogical.query_analogies(domain)
                if analogies:
                    result["analogies"] = [
                        {
                            "domain": a["domain"],
                            "confidence": round(a["confidence"], 2),
                            "transfers": len(a.get("transfers", [])),
                        }
                        for a in analogies[:3]
                    ]

            # ════════════════════════════════════════════════════
            # Phase 7: AUTONOMY CHECK
            # ════════════════════════════════════════════════════
            if self.autonomy:
                stall = self.autonomy.detect_stall()
                if stall:
                    result["stall_warning"] = stall

                auto_stats = self.autonomy.stats()
                result["autonomy"] = {
                    "active_goals": auto_stats["goals"]["active"],
                    "pending_goals": auto_stats["goals"]["pending"],
                    "total_completed": auto_stats["total_completed"],
                }

            # ════════════════════════════════════════════════════
            # Phase 8: CLOSE THE CONSCIOUS FRAME
            # ════════════════════════════════════════════════════
            if self.cognitive_bus and self.conscious:
                # Generate narrative from conscious reflection
                reflection = self.conscious.reflect() if hasattr(self.conscious, 'reflect') else {}
                narrative = reflection.get('current_attention', 'interaction processed')
                self.cognitive_bus.last_frame_narrative = (
                    f"I am attending to {narrative} from {domain} domain."
                )
                self.cognitive_bus.module_heartbeat("conscious_stream")

            # ─── Final bus tick ───
            if self.cognitive_bus:
                final_snapshot = self.cognitive_bus.tick()
                result["cognitive_state"] = final_snapshot.to_dict()

            # ─── Consciousness Harness: Generate system prompt addon ───
            if self.consciousness_harness:
                result["consciousness_prompt_addon"] = self.consciousness_harness.generate_system_prompt_addon()

            # ═══ Timing ═══
            result["processing_time_ms"] = round((time.time() - start_time) * 1000, 1)
            result["total_interactions"] = self.total_interactions

        return result

    def _psi_select_attention(self, bus_snapshot, user_message: str,
                              domain: str, context: Dict):
        """
        PSI-driven attention selection with contextual override.

        Priority hierarchy:
          1. CRITICAL need deprivation (deficit > 0.7) → need-driven focus
          2. User actively speaking → USER focus (with need modulation)
          3. Moderate need deprivation (deficit > 0.5) → need-driven focus
          4. Default → task or user based on domain cues
        """
        if not self.cognitive_bus:
            return

        needs = bus_snapshot.needs
        strongest, deficit = needs.strongest_need()

        # Map strongest need deficit → attention focus
        need_to_attention = {
            "competence": BusAttentionFocus.TASK,
            "autonomy": BusAttentionFocus.SELF,
            "relatedness": BusAttentionFocus.USER,
            "certainty": BusAttentionFocus.MEMORY,
            "growth": BusAttentionFocus.LEARNING,
        }

        # Priority 1: Critical deprivation (>0.7) — need dominates everything
        if deficit > 0.7:
            new_focus = need_to_attention.get(strongest, BusAttentionFocus.TASK)
            intensity = 1.0

        # Priority 2: User is actively engaging — USER focus with need modulation
        elif "?" in user_message or any(kw in domain for kw in [
                "chat", "greeting", "talk", "hello", "hi", "question"]):
            # If the need deficit is moderate, mix USER with the need-driven focus
            if deficit > 0.5:
                # User is present but a need is calling — split attention
                need_focus = need_to_attention.get(strongest, BusAttentionFocus.TASK)
                # If the need is relatedness, USER focus aligns with need
                if strongest == "relatedness":
                    new_focus = BusAttentionFocus.USER
                else:
                    # User message overrides moderate needs
                    new_focus = BusAttentionFocus.USER
                intensity = 0.7 + deficit * 0.3
            else:
                new_focus = BusAttentionFocus.USER
                intensity = 0.8

        # Priority 3: Moderate need deprivation
        elif deficit > 0.5:
            new_focus = need_to_attention.get(strongest, BusAttentionFocus.TASK)
            intensity = 0.5 + deficit * 0.5

        # Priority 4: Domain-driven default
        elif any(kw in domain for kw in ["code", "build", "fix", "implement", "refactor", "debug"]):
            new_focus = BusAttentionFocus.TASK
            intensity = 0.7
        elif any(kw in domain for kw in ["learn", "study", "explore", "research"]):
            new_focus = BusAttentionFocus.LEARNING
            intensity = 0.7
        elif any(kw in domain for kw in ["analyze", "think", "reflect"]):
            new_focus = BusAttentionFocus.SELF
            intensity = 0.6
        else:
            new_focus = BusAttentionFocus.USER
            intensity = 0.5

        # Build salience map based on chosen focus
        salience = {
            "user_input": 0.9 if new_focus == BusAttentionFocus.USER else
                          (0.5 if "?" in user_message else 0.3),
            "task_goal": 0.8 if new_focus == BusAttentionFocus.TASK else 0.3,
            "self_state": 0.7 if new_focus == BusAttentionFocus.SELF else 0.2,
            "memory_patterns": 0.7 if new_focus == BusAttentionFocus.MEMORY else 0.3,
            "curiosity_drive": bus_snapshot.curiosity,
            "strongest_need": strongest,
            "need_deficit": round(deficit, 2),
        }

        # Update attention on the bus
        self.cognitive_bus.set_attention(
            focus=new_focus,
            intensity=min(1.0, intensity),
            salience_map=salience,
        )

    def get_state(self) -> Dict[str, Any]:
        """Get comprehensive agent state for introspection."""
        state = {
            "agent": self.name,
            "version": self.version,
            "uptime_seconds": time.time() - self.created_at,
            "total_interactions": self.total_interactions,
            "modules": self._module_count(),
        }

        # Module states
        if self.world:
            state["world_model"] = self.world.stats()
        if self.self_model:
            state["self_model"] = self.self_model.stats()
            state["self_knowledge"] = self.self_model.know_what_you_know()
        if self.causal:
            state["causal"] = self.causal.stats()
        if self.analogical:
            state["analogical"] = self.analogical.stats()
        if self.learning:
            state["learning"] = self.learning.stats()
        if self.autonomy:
            state["autonomy"] = self.autonomy.stats()
        if self.conscious:
            state["conscious"] = self.conscious.stats()
            state["conscious_reflection"] = self.conscious.reflect()

        if self.consciousness_harness:
            state["consciousness_harness"] = self.consciousness_harness.get_consciousness_report()

        if self.unified_memory:
            state["unified_memory"] = self.unified_memory.get_memory_summary()

        # Cognitive Bus state
        if self.cognitive_bus:
            state["cognitive_bus"] = self.cognitive_bus.stats()
            state["cognitive_state_prompt"] = self.cognitive_bus.inject_cognitive_state_into_prompt()

        # Autonomy: next action
        if self.autonomy:
            next_action = self.autonomy.get_next_action()
            if next_action:
                state["next_autonomous_action"] = next_action

        return state

    def reflection(self) -> str:
        """Generate comprehensive self-reflection."""
        parts = []

        if self.conscious:
            c = self.conscious.reflect()
            parts.append(f"Currently: {c.get('current_attention', 'unknown')} attention, "
                        f"feeling {c.get('dominant_emotion', 'neutral')}.")

        if self.self_model:
            parts.append(self.self_model.reflection())

        if self.learning:
            s = self.learning.stats()
            parts.append(f"I have learned from {s['total_learned']} experiences "
                        f"and generated {s['skills_generated']} skills.")

        if self.autonomy:
            s = self.autonomy.stats()
            parts.append(f"I have completed {s['total_completed']} goals "
                        f"with {s['goals']['active']} active.")

        return "\n".join(parts)

    # ════════════════════════════════════════════════════════
    # Persistence
    # ════════════════════════════════════════════════════════

    def save(self, path: str = None):
        """
        Save full agent state to disk.

        Saves all module states as JSON for recovery across sessions.
        """
        save_path = Path(path) if path else (self.state_dir / "agi_state.json" if self.state_dir else None)
        if not save_path:
            logger.warning("No save path configured")
            return

        save_path.parent.mkdir(parents=True, exist_ok=True)

        state = self.get_state()
        state["saved_at"] = time.time()

        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, default=str, ensure_ascii=False)

        logger.info(f"AGI state saved to {save_path} "
                     f"({len(json.dumps(state))} bytes)")

    def load(self, path: str = None) -> bool:
        """
        Load agent state from disk.

        Restores module states from a previous save.
        """
        load_path = Path(path) if path else (self.state_dir / "agi_state.json" if self.state_dir else None)
        if not load_path or not load_path.exists():
            return False

        try:
            with open(load_path, 'r', encoding='utf-8') as f:
                state = json.load(f)

            self.total_interactions = state.get("total_interactions", 0)

            # Restore self-knowledge to self-model
            if self.self_model and "self_knowledge" in state:
                sk = state["self_knowledge"]
                self.self_model.total_actions = sk.get("total_actions", 0)
                total_success = sk.get("overall_success_rate", 0.5) * max(1, self.self_model.total_actions)
                self.self_model.total_successes = int(total_success)
                self.self_model.current_self_efficacy = sk.get("self_efficacy", 0.5)

            logger.info(f"AGI state loaded from {load_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to load state: {e}")
            return False

    def _load_if_exists(self):
        """Try to load state on startup."""
        if self.state_dir:
            loaded = self.load()
            if loaded:
                logger.info(f"Resumed from previous state")

    # ════════════════════════════════════════════════════════
    # Utility
    # ════════════════════════════════════════════════════════

    def assign_task(self, description: str, priority: str = "medium",
                    domain: str = "") -> Dict[str, Any]:
        """Assign a task to the autonomous engine."""
        if not self.autonomy:
            return {"error": "Autonomy engine not enabled"}

        pri_map = {
            "critical": GoalPriority.CRITICAL,
            "high": GoalPriority.HIGH,
            "medium": GoalPriority.MEDIUM,
            "low": GoalPriority.LOW,
            "background": GoalPriority.BACKGROUND,
        }

        goal = self.autonomy.assign_goal(
            description=description,
            source=GoalSource.USER_REQUEST,
            priority=pri_map.get(priority, GoalPriority.MEDIUM),
            domain=domain,
        )

        return {
            "goal_id": goal.id[:12],
            "description": goal.description[:80],
            "priority": goal.priority.value,
            "status": goal.status.value,
        }

    def get_next_autonomous_action(self) -> Optional[Dict[str, Any]]:
        """Get the next action from the autonomous engine."""
        if not self.autonomy:
            return None
        return self.autonomy.get_next_action()

    def health_check(self) -> Dict[str, Any]:
        """Comprehensive health check across all modules."""
        status = {
            "healthy": True,
            "agent": self.name,
            "version": self.version,
            "uptime_hours": (time.time() - self.created_at) / 3600,
            "modules": {},
        }

        modules_to_check = [
            ("world_model", self.world),
            ("self_model", self.self_model),
            ("causal", self.causal),
            ("analogical", self.analogical),
            ("learning", self.learning),
            ("autonomy", self.autonomy),
            ("conscious", self.conscious),
            ("memory_system", self.memory_system),
            ("evolution", self.evolution),
            ("security", self.security),
            ("hermes", self.hermes),
            ("code_evolution", self.code_evolution),
            ("self_healing", self.self_healing),
            ("quality_assurance", self.quality_assurance),
            ("code_minimizer", self.code_minimizer),
            ("agent_registry", self.agent_registry),
            ("task_board", self.task_board),
            ("safe_rollback", self.safe_rollback),
            ("consciousness_harness", self.consciousness_harness),
            ("unified_memory", self.unified_memory),
            ("psi_driver", getattr(self, "psi_driver", None)),
        ]

        for mod_name, mod in modules_to_check:
            if mod is None:
                status["modules"][mod_name] = "disabled"
            else:
                try:
                    if hasattr(mod, 'stats'):
                        mod_stats = mod.stats()
                    elif hasattr(mod, 'get_consciousness_report'):
                        mod_stats = mod.get_consciousness_report()
                    elif hasattr(mod, 'get_memory_summary'):
                        mod_stats = mod.get_memory_summary()
                    else:
                        mod_stats = {}
                    status["modules"][mod_name] = {
                        "status": "active",
                        **{k: v for k, v in mod_stats.items()
                           if k not in ("name", "agent")}
                    }
                except Exception as e:
                    status["modules"][mod_name] = f"error: {e}"
                    status["healthy"] = False

        return status

    def __repr__(self) -> str:
        return (f"AGIAgent('{self.name}' v{self.version}, "
                f"{self._module_count()} modules, "
                f"{self.total_interactions} interactions)")

    def shutdown(self):
        """Graceful shutdown: save state and clean up."""
        logger.info(f"AGIAgent '{self.name}' shutting down...")
        self.save()
        logger.info(f"AGIAgent '{self.name}' shut down complete")


# ════════════════════════════════════════════════════════════
# Factory
# ════════════════════════════════════════════════════════════

def create_agi_agent(name: str = "Ao",
                     state_dir: str = None,
                     auto_save_interval: int = 300,
                     enable_all: bool = True) -> AGIAgent:
    """
    Factory function to create a fully-configured AGI agent.

    Args:
        name: Agent name
        state_dir: Directory for persistent state
        auto_save_interval: Seconds between auto-saves (0 = disable)
        enable_all: Enable all modules

    Returns:
        Fully initialized AGIAgent
    """
    agent = AGIAgent(
        name=name,
        state_dir=state_dir,
        enable_all=enable_all,
    )

    # Set up auto-save if requested
    if auto_save_interval > 0 and state_dir:
        def _auto_save():
            while True:
                time.sleep(auto_save_interval)
                try:
                    agent.save()
                except Exception as e:
                    logger.error(f"Auto-save failed: {e}")

        save_thread = threading.Thread(target=_auto_save, daemon=True)
        save_thread.start()
        logger.info(f"Auto-save enabled (every {auto_save_interval}s)")

    return agent
