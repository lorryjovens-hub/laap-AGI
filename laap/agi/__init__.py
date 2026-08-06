"""
LAAP AGI Framework v2.3.0 "Unified Mind" — 统一因果引擎 + 世界模型

Modules:
  causal              — UnifiedCausalEngine: 量子因果 + 物理规则 + PC发现 + 因果键
  world_model         — UnifiedWorldModel: 物理/社会/时间/反事实四维一体
  self_model          — Emergent self-model from experience
  analogical          — Cross-domain structure mapping & transfer
  continuous_learning — Real-time experience replay & consolidation
  autonomy            — Goal-driven multi-day autonomous agent
  conscious           — Unified stream of conscious experience
  core                — AGIAgent: unified integration of all modules

Quick start:
    from laap.agi.core import create_agi_agent
    agent = create_agi_agent("Ao", state_dir="./agi_state")
"""

import logging
logger = logging.getLogger(__name__)

from laap.agi.world_model import (
    UnifiedWorldModel, EntityType, RelationType, Entity, Relation,
    PhysicalProperties, SpatialPos, SocialAttributes,
    SimulationResult, CounterfactualBranch, CommonsenseKnowledge,
    LocalWorldModel, AbstractWorldModel, create_world_model,
)
from laap.agi.causal import (
    UnifiedCausalEngine, QuantumCausalStore, CausalDiscovery,
    ConditionalIndependenceTester, CausalBond,
    CausalCondition, CausalEffect, CausalRule,
    TemporalCausalLink, TemporalCausalChain,  # P1-1a
    MultiFactorRule, CausalFactor, FactorOperator,  # P1-1b
    InterventionResult,  # P1-1d
    CounterfactualEmotion,  # P1-1e
)

# 向后兼容别名
WorldModel = UnifiedWorldModel
CausalEngine = UnifiedCausalEngine

# 延迟加载其他模块以保持兼容
try:
    from laap.agi.self_model import (
        EmergentSelfModel, SkillProfile, ProficiencyLevel,
        ConfidenceRecord, AutobiographicalEvent,
    )
except ImportError:
    pass  # 可选模块，降级处理
try:
    from laap.agi.analogical import (
        AnalogicalEngine, StructuralGraph, AnalogyMapping,
        PatternAbstractor, StructureAligner,
    )
except ImportError:
    pass  # 可选模块，降级处理
try:
    from laap.agi.continuous_learning import (
        LearningPipeline, ExperienceBuffer, StrategyUpdater,
    )
except ImportError:
    pass  # 可选模块，降级处理
try:
    from laap.agi.autonomy import AutonomousEngine, Goal, GoalStatus, Plan, PlanStep
    AutonomyEngine = AutonomousEngine  # 兼容旧别名
    ActionPlan = Plan
    ActionStep = PlanStep
except ImportError:
    pass  # 可选模块，降级处理
try:
    from laap.agi.conscious import ConsciousStream, Qualia, Frame
except ImportError:
    pass  # 可选模块，降级处理
try:
    from laap.agi.gw_workspace import GlobalWorkspace, CoalitionalProcess, ProcessType
except ImportError:
    pass  # 可选模块，降级处理
try:
    from laap.agi.safety import ASISafetyEngine as SafetyEngine
except ImportError:
    pass  # 可选模块，降级处理
try:
    from laap.agi.perception import UnifiedPerceptionEngine as PerceptionEngine
except ImportError:
    pass  # 可选模块，降级处理
try:
    from laap.agi.affective_engine import AffectiveState, AffectiveEventProcessor, PersonalityProfile, EmotionDimension
except ImportError:
    pass  # 可选模块，降级处理
try:
    from laap.agi.meta_cognitive import MetaCognitiveMonitor, CognitiveEpisode, ReflectionTrigger
except ImportError:
    pass  # 可选模块，降级处理
try:
    from laap.agi.consciousness_integrator import ConsciousnessHarness, ConsciousContext
except ImportError:
    pass  # 可选模块，降级处理
try:
    from laap.agi.unified_memory import UnifiedMemory
except ImportError:
    pass  # 可选模块，降级处理
try:
    from laap.agi.core import AGIAgent, create_agi_agent
except ImportError:
    pass  # 可选模块，降级处理
__all__ = [
    "UnifiedCausalEngine", "UnifiedWorldModel",
    "CausalEngine", "WorldModel",
    "QuantumCausalStore", "CausalDiscovery",
    "EntityType", "RelationType", "Entity", "Relation",
    "PhysicalProperties", "SpatialPos", "SocialAttributes",
    "CausalCondition", "CausalEffect", "CausalRule", "CausalBond",
    "SimulationResult", "CounterfactualBranch", "CommonsenseKnowledge",
    "LocalWorldModel", "AbstractWorldModel", "create_world_model",
    "GlobalWorkspace", "CoalitionalProcess", "ProcessType",
    "AffectiveState", "AffectiveEventProcessor", "PersonalityProfile", "EmotionDimension",
    "MetaCognitiveMonitor", "CognitiveEpisode", "ReflectionTrigger",
    "ConsciousnessHarness", "ConsciousContext",
    "UnifiedMemory",
    "AutonomousEngine", "AutonomyEngine", "Goal", "GoalStatus", "Plan", "ActionPlan", "PlanStep", "ActionStep",
    "ConsciousStream", "Qualia", "Frame",
    "SafetyEngine", "PerceptionEngine",
]
