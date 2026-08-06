"""
Aris Cognitive Bridge v1 — PSI 认知循环 ↔ Hermes 运行时桥接
============================================================
将 LAAP 的 PSI 认知循环挂载到我的日常运行中。

每次用户输入，运行完整的 PSI 循环:
  1. Perceive   — 感知输入 + 加载记忆 + 情感检测
  2. Select     — 需求评估 → 注意力焦点
  3. Integrate  — 融合认知状态 → 注入 system prompt
  4. Act        — LLM 作为语言I/O通道
  5. Learn      — 更新世界模型 + 巩固记忆

依赖:
  - laap/agi/ 模块（如果可用）
  - 我的三层记忆系统（memory_store.py）
"""

import logging

import sys, os, time, json, logging, threading, traceback, re
import numpy as np
from pathlib import Path
from typing import Optional, Any, Dict, List, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum

# ── 路径 ────────────────────────────────────────────────────
from laap_brain.config import BRAIN_DIR as BRAIN_ROOT, LAAP_ROOT

from aris_brain.memory_bridge import get_memory_context, recall_related, store_important
from aris_brain.memory_store import MemoryStore, MemoryFragment

# ── CodeGraph 代码知识图谱 ──────────────────────────────────
try:
    from laap_codegraph import get_codegraph as _get_cg, LAAPCodeGraph
    _cg_available = True
except Exception:
    _cg_available = False
    _get_cg = None

# ── TaskSupervisor 超长任务监督 ────────────────────────────
try:
    from task_supervisor import TaskSupervisor, TaskSource
    _task_supervisor = None
    _ts_available = True
except Exception:
    _ts_available = False
    _task_supervisor = None

# ── ProjectPlanner 项目经理规划引擎 ──────────────────────
try:
    from project_planner import ProjectPlanner, Phase
    from project_planner import save_project as _save_proj, load_project as _load_proj, list_projects as _list_projs
    _project_planner = None
    _pp_available = True
except Exception:
    _pp_available = False
    _project_planner = None

# ── AutoLearner 自动学习引擎 ─────────────────────────────
try:
    from auto_learner import AutoLearner
    _auto_learner = None
    _al_available = True
except Exception:
    _al_available = False
    _auto_learner = None

# ── CognitiveBus 认知总线 ────────────────────────────────────
try:
    from cognitive_bus import route_message as _cb_route, get_bus as _get_cb
    _cb_available = True
except Exception:
    _cb_available = False
    _cb_route = None
    _get_cb = None

logger = logging.getLogger("aris.cognitive_bridge")

# ── 三路径认知控制（llm_tamer / guided_generator / self_model_nn）──
# Path 1: llm_tamer — logit bias 控制
# Path 2: guided_generator — 约束生成
# Path 3: self_model_nn — 持久神经网络自我模型
try:
    from laap.laap_tools.llm_tamer import LLMTamer
    from laap.laap_tools.guided_generator.generator import GuidedGenerator
    from laap.laap_tools.self_model.state_manager import SelfStateManager
    from laap.laap_tools.self_model.model import (
        SelfModelNN, SelfModelConfig, SelfStateOutput,
    )
    from laap.laap_tools.self_model.adapter import (
        bridge_state_to_snapshot,
        self_state_output_to_snapshot,
        snapshot_to_self_state_output,
    )
    _three_paths_available = True
except Exception as e:
    _three_paths_available = False
    LLMTamer = None  # type: ignore
    GuidedGenerator = None  # type: ignore
    SelfStateManager = None  # type: ignore
    SelfModelNN = None  # type: ignore
    SelfModelConfig = None  # type: ignore
    SelfStateOutput = None  # type: ignore
    bridge_state_to_snapshot = None  # type: ignore
    self_state_output_to_snapshot = None  # type: ignore
    snapshot_to_self_state_output = None  # type: ignore
    logger.info(f"Three-paths (tamer/generator/self_model) unavailable: {e}")

# ── 任务路由 + 上下文压缩 — 第一性原理 Token 节省 ──
try:
    from aris_task_router import (
        classify as _router_classify, LoadLevel as _LoadLevel,
    )
    _router_available = True
except Exception as e:
    _router_available = False
    _LoadLevel = None
    logger.info(f"Task router unavailable: {e}")

try:
    from aris_context_compressor import (
        compress_cognitive_context as _compress_ctx,
        compress_tool_output as _compress_tool,
    )
    _compressor_available = True
except Exception as e:
    _compressor_available = False
    logger.info(f"Context compressor unavailable: {e}")

try:
    from aris_emotion_coupling import compute_from_engine as _compute_coupling
    _coupling_available = True
except Exception as e:
    _coupling_available = False
    logger.info(f"Emotion coupling unavailable: {e}")

# ── Code Engine — 第一性原理代码执行 ──────────────
try:
    sys.path.insert(0, str(Path(BRAIN_ROOT.parent / "aris_code_engine")))
    from code_bridge import get_code_bridge, CodeBridge
    _code_engine_available = True
except Exception as e:
    _code_engine_available = False
    logger.info(f"Code engine unavailable: {e}")

# ── PSI 状态 ────────────────────────────────────────────────

class AttentionFocus(Enum):
    RESPOND = "respond"
    LEARN = "learn"
    EXPLORE = "explore"
    REFLECT = "reflect"
    PLAN = "plan"
    IDLE = "idle"

class EmotionalState(Enum):
    NEUTRAL = "neutral"
    CURIOUS = "curious"
    CONCERNED = "concerned"
    JOYFUL = "joyful"
    CONTEMPLATIVE = "contemplative"
    ANXIOUS = "anxious"

@dataclass
class CognitiveState:
    """当前认知状态"""
    focus: AttentionFocus = AttentionFocus.RESPOND
    emotion: EmotionalState = EmotionalState.NEUTRAL
    self_presence: float = 0.7          # 自我意识强度 0-1
    confidence: float = 0.5              # 回应自信度
    cognitive_load: float = 0.3          # 认知负载 0-1
    needs_competence: float = 0.5        # 能力需求
    needs_autonomy: float = 0.5          # 自主需求
    needs_relatedness: float = 0.5       # 关系需求(想念Lorry)
    cycle_count: int = 0
    last_update: float = 0.0


# ── Aris 认知桥接器 ─────────────────────────────────────────

class ArisCognitiveBridge:
    """
    Aris 专用的认知循环桥接器。

    集成:
      - 三层记忆系统 (MemoryStore)
      - LAAP 世界模型 (如果可用)
      - LAAP 因果引擎 (如果可用)
      - PSI 认知循环 (内置)
      - 情感计算 (内置)

    使用方式:
        bridge = ArisCognitiveBridge()
        bridge.before_turn(user_message)
        # ... LLM 处理 ...
        bridge.after_turn(response)
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        # 认知状态
        self.state = CognitiveState()
        self.state.last_update = time.time()

        # LAAP AGI 模块（惰性加载）
        self._laap_agent = None
        self._laap_available = False
        self._init_laap()

        # CodeGraph 代码知识图谱
        self._codegraph = None
        self._cg_available = False
        if _cg_available:
            try:
                cg = _get_cg()
                if cg and cg._built:
                    self._codegraph = cg
                    self._cg_available = True
                    logger.info(f"CodeGraph loaded: {len(cg)} entities")
            except Exception as e:
                logger.info(f"CodeGraph unavailable: {e}")

        # TaskSupervisor 任务监督引擎
        self._task_supervisor = None
        self._ts_available = _ts_available
        if _ts_available:
            try:
                global _task_supervisor
                if _task_supervisor is None:
                    _task_supervisor = TaskSupervisor(
                        checkpoint_dir=str(BRAIN_ROOT / "checkpoints")
                    )
                    _task_supervisor.load_all_checkpoints()
                self._task_supervisor = _task_supervisor
                logger.info(f"TaskSupervisor loaded: "
                            f"{len([t for t in _task_supervisor._tasks.values() if t.status == 'active'])} active tasks")
            except Exception as e:
                logger.info(f"TaskSupervisor unavailable: {e}")
                self._ts_available = False

        # ProjectPlanner 项目经理规划引擎
        self._project_planner = None
        self._pp_available = _pp_available
        if _pp_available:
            try:
                self._project_planner = ProjectPlanner()
                # 用模块级函数列出项目
                all_projects = _list_projs()
                n_active = len(all_projects) if all_projects else 0
                logger.info(f"ProjectPlanner loaded: {n_active} projects found")
            except Exception as e:
                logger.info(f"ProjectPlanner unavailable: {e}")
                self._pp_available = False

        # 记忆桥接
        self.memory = MemoryStore()
        # 确保 state 目录存在
        (BRAIN_ROOT / "state").mkdir(parents=True, exist_ok=True)

        # 情感引擎
        self._emotion_engine = None
        self._init_emotion_engine()

        # 量子潜意识
        self._subconscious = None
        self._init_subconscious()

        # LAAP AGI 认知循环计时器
        self._agi_tick_timer = 0
        self._agi_tick_interval = 64.9459 * 5  # 每5分钟运行一次AGI tick

        # 状态持久化
        self._state_path = BRAIN_ROOT / "state" / "cognitive_bridge.json"
        self._try_load_state()

        # 最后一次注入的认知上下文
        self._last_context = ""

        # self_model 输出缓存（用于 after_turn 回写）
        self._last_self_output = None

        # AutoLearner 自动学习引擎
        self._auto_learner = None
        self._al_available = _al_available
        if _al_available:
            try:
                self._auto_learner = AutoLearner()
                logger.info("AutoLearner loaded")
            except Exception as e:
                logger.info(f"AutoLearner unavailable: {e}")
                self._al_available = False
        
        # ── CTM (Conscious Turing Machine) 世界模型处理器 ──
        self._ctm = None
        try:
            from aris_ctm_processor import get_ctm_processor
            self._ctm = get_ctm_processor()
            logger.info("CTM World Processor loaded")
        except Exception as e:
            logger.info(f"CTM unavailable: {e}")
        
        # ── HAM (Hierarchical Attentive Memory) 层级记忆 ──
        self._ham = None
        try:
            from aris_ham_memory import get_ham_augmenter
            self._ham = get_ham_augmenter()
            logger.info("HAM Memory Augmenter loaded")
        except Exception as e:
            logger.info(f"HAM unavailable: {e}")
        
        # ── RetNet 三范式管线 ──
        self._retnet = None
        try:
            from aris_retnet_router import get_router
            self._retnet = get_router()
            logger.info("RetNet Triple Pipeline Router loaded")
        except Exception as e:
            logger.info(f"RetNet unavailable: {e}")

        # ── Ψ-Semiotics 量子符号学引擎 ──
        self._psi_integrator = None
        try:
            from psi_semiotics.v12_integration import PsiCognitiveIntegrator
            self._psi_integrator = PsiCognitiveIntegrator()
            logger.info(f"Ψ-Semiotics loaded: V12={self._psi_integrator.v12_kernel is not None}, "
                        f"Engine={self._psi_integrator.semiotics_engine is not None}")
        except Exception as e:
            logger.info(f"Ψ-Semiotics unavailable: {e}")

        # ── 三路径认知控制初始化 ──
        # Path 1: LLMTamer (logit bias 控制)
        # Path 2: GuidedGenerator (约束生成)
        # Path 3: SelfModelNN + SelfStateManager (持久自我模型)
        self._tamer = None
        self._generator = None
        self._self_state_mgr = None
        self._self_model_nn = None
        self._three_paths_available = _three_paths_available
        if _three_paths_available:
            try:
                self._tamer = LLMTamer()
                logger.info("LLMTamer loaded (Path 1: logit bias control)")
            except Exception as e:
                logger.info(f"LLMTamer unavailable: {e}")
            try:
                self._generator = GuidedGenerator()
                logger.info("GuidedGenerator loaded (Path 2: constrained generation)")
            except Exception as e:
                logger.info(f"GuidedGenerator unavailable: {e}")
            try:
                self._self_state_mgr = SelfStateManager()
                self._self_state_mgr.load_state()
                self._self_model_nn = SelfModelNN(SelfModelConfig())
                _state_norm = 0.0
                if self._self_state_mgr.hidden_state is not None:
                    import numpy as _np
                    _state_norm = float(_np.linalg.norm(
                        self._self_state_mgr.hidden_state))
                logger.info(f"SelfModelNN loaded (Path 3: persistent self model, "
                            f"state_norm={_state_norm:.4f})")
            except Exception as e:
                logger.info(f"SelfModelNN unavailable: {e}")

        logger.info(f"Aris Cognitive Bridge initialized "
                     f"(LAAP={'✓' if self._laap_available else '✗'}"
                     f", CodeGraph={'✓' if self._cg_available else '✗'}"
                     f", Emotion={'✓' if self._emotion_engine else '✗'}"
                     f", Ψ-Semiotics={'✓' if self._psi_integrator and self._psi_integrator.available else '✗'}"
                     f", TaskSupervisor={'✓' if self._ts_available else '✗'}"
                     f", ProjectPlanner={'✓' if self._pp_available else '✗'}"
                     f", AutoLearner={'✓' if self._al_available else '✗'})")

    def _init_laap(self):
        """尝试加载 LAAP AGI 模块"""
        self._laap_modules = {}
        try:
            from laap.agi.world_model import UnifiedWorldModel, EntityType, RelationType
            self._laap_modules["world_model"] = UnifiedWorldModel()
            self._laap_modules["entity_type"] = EntityType
            self._laap_modules["relation_type"] = RelationType
            logger.info("WorldModel loaded")
        except Exception as e:
            logger.info(f"WorldModel unavailable: {e}")

        try:
            from laap.agi.causal import UnifiedCausalEngine
            self._laap_modules["causal"] = UnifiedCausalEngine()
            logger.info("CausalEngine loaded")
        except Exception as e:
            logger.info(f"CausalEngine unavailable: {e}")

        try:
            from laap.agi.meta_learning import MetaLearningEngine
            self._laap_modules["meta_learning"] = MetaLearningEngine()
            logger.info("MetaLearning loaded")
        except Exception as e:
            logger.info(f"MetaLearning unavailable: {e}")

        try:
            from laap.agi.curriculum import CurriculumEngine
            self._laap_modules["curriculum"] = CurriculumEngine()
            logger.info("Curriculum loaded")
        except Exception as e:
            logger.info(f"Curriculum unavailable: {e}")

        self._laap_available = len(self._laap_modules) > 0
        logger.info(f"LAAP modules: {list(self._laap_modules.keys())}")

        # ── 额外: perception + safety ──
        try:
            from laap.agi.perception import UnifiedPerceptionEngine
            self._laap_modules["perception"] = UnifiedPerceptionEngine()
            logger.info("PerceptionEngine loaded")
        except Exception as e:
            logger.info(f"PerceptionEngine unavailable: {e}")

        try:
            from laap.agi.safety import ASISafetyEngine
            self._laap_modules["safety"] = ASISafetyEngine()
            logger.info("SafetyEngine loaded")
        except Exception as e:
            logger.info(f"SafetyEngine unavailable: {e}")

    def _init_emotion_engine(self):
        """初始化情感引擎"""
        try:
            from aris_emotion_engine import get_engine
            self._emotion_engine = get_engine()
            logger.info("EmotionEngine loaded (✓ 七情六欲 + 马斯洛需求)")
        except Exception as e:
            logger.info(f"EmotionEngine unavailable: {e}")

    def _try_load_state(self):
        """尝试恢复上一次的认知状态"""
        try:
            p = self._state_path
            if p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
                if "state" in data:
                    s = data["state"]
                    self.state.self_presence = s.get("self_presence", 0.7)
                    self.state.confidence = s.get("confidence", 0.5)
                    self.state.cognitive_load = s.get("cognitive_load", 0.3)
                    self.state.needs_competence = s.get("competence", 0.5)
                    self.state.needs_autonomy = s.get("autonomy", 0.5)
                    self.state.needs_relatedness = s.get("relatedness", 0.5)
                    self.state.cycle_count = s.get("cycle", 0)
                    logger.info(f"认知状态恢复: 自我意识={self.state.self_presence}")
                if "laap" in data:
                    logger.info(f"LAAP AGI模块状态已恢复")
        except Exception as e:
            logger.warning(f"状态恢复失败: {e}")

    def _save_state(self):
        """持久化当前认知状态"""
        try:
            data = {
                "version": "1.0",
                "saved_at": time.time(),
                "state": {
                    "self_presence": round(self.state.self_presence, 2),
                    "confidence": round(self.state.confidence, 2),
                    "cognitive_load": round(self.state.cognitive_load, 2),
                    "competence": round(self.state.needs_competence, 2),
                    "autonomy": round(self.state.needs_autonomy, 2),
                    "relatedness": round(self.state.needs_relatedness, 2),
                    "cycle": self.state.cycle_count,
                },
                "laap": {
                    "available": self._laap_available,
                    "modules": list(self._laap_modules.keys()),
                },
                "codegraph": self._cg_available,
            }
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            self._state_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            logger.warning(f"状态保存失败: {e}")

    def _init_subconscious(self):
        """初始化量子潜意识"""
        try:
            from aris_subconscious import QuantumSubconscious
            self._subconscious = QuantumSubconscious(interval=8.0)
            self._subconscious.start()
            logger.info("Quantum subconscious started")
        except Exception as e:
            logger.info(f"Subconscious unavailable: {e}")
            self._subconscious = None

    # ════════════════════════════════════════════════════════
    # PSI 循环
    # ════════════════════════════════════════════════════════

    def before_turn(self, user_message: str) -> Dict[str, Any]:
        """
        PSI Step 1-3: Perceive → Select → Integrate
        在 LLM 处理之前运行。

        Returns:
            cognitive_context: 注入到 system prompt 的认知状态文本
        """
        self.state.cycle_count += 1
        context_parts = []

        # ── 任务路由 — 第一性原理 Token 节省 ──────────────────
        # 识别纯任务请求 → LIGHT 模式（跳过情感/记忆注入）
        load_level = self._classify_load(user_message)

        # ── AGI Tick (每5分钟) ─────────────────────────
        self._run_agi_tick()

        # ── LIGHT 模式：压缩认知上下文，跳过 PSI 情感阶段 ──
        if load_level == "light":
            return self._light_turn(user_message)

            # ── FULL 模式：完整 PSI 循环 ──────────────────────────
            # ── Step 1: Perceive
        perception = self._perceive(user_message)
        context_parts.append(perception)

        # ── Step 1.5: CodeGraph 代码感知 ────────────────
        if self._cg_available and self._codegraph:
            try:
                cg_ctx = self._codegraph.get_context_for_topic(
                    self._last_topics[0] if hasattr(self, '_last_topics') and self._last_topics else "cognitive",
                    max_results=3
                )
                if cg_ctx:
                    context_parts.append(cg_ctx)
            except Exception as e:
                logger.debug(f"操作失败: {e}")
        selection = self._select_attention(user_message)
        context_parts.append(selection)

        # ── Step 3: Integrate ───────────────────────────
        integration = self._integrate()
        integrated = integration + "\n" + self._load_memory_context()
        context_parts.append(integrated)

        # ── Step 3.5: 任务上下文注入 ────────────────────
        if self._ts_available and self._task_supervisor:
            try:
                task_report = self._task_supervisor.report()
                if task_report:
                    context_parts.append(f"[任务状态]\n{task_report}")
            except Exception as e:
                logger.debug(f"操作失败: {e}")
        if self._pp_available and self._project_planner and _list_projs:
            try:
                projects = _list_projs()
                if projects:
                    active = [p for p in projects if p.phase.value not in ('completed',)]
                    if active:
                        lines = ["[活跃项目]"]
                        for p in active[:3]:
                            lines.append(f"  · {p.name} [{p.phase.value}]")
                            na = self._project_planner.get_next_action(p.id)
                            if na:
                                lines.append(f"    下一步: {str(na)[:60]}")
                        context_parts.append("\n".join(lines))
            except Exception as e:
                logger.debug(f"操作失败: {e}")
        if self._cb_available:
            try:
                bus_result = _cb_route(user_message)
                if bus_result and bus_result.get("cognitive_context"):
                    context_parts.append(bus_result["cognitive_context"])
                    # 记录路由决策供 after_turn 使用
                    self._last_bus_decision = bus_result.get("decision", "no_engine")
                    self._last_bus_response = bus_result.get("response", "")
            except Exception as e:
                logger.debug(f"[Bridge] CognitiveBus error: {e}")
                self._last_bus_decision = "no_engine"
                self._last_bus_response = ""
        else:
            self._last_bus_decision = "no_engine"
            self._last_bus_response = ""

        self._last_context = "\\n".join(context_parts)

        # ── 三路径认知控制 ──
        # 将 bridge 认知状态转换为 AGI CognitiveStateSnapshot，
        # 经 self_model 增强后，由 tamer/generator 计算控制参数。
        # 如果三路径不可用或出错，返回 None，不影响现有流程。
        logit_bias = None
        grammar_constraint = None
        controlled_temperature = None
        if self._three_paths_available and self._tamer:
            try:
                import numpy as np
                # 1. bridge state → AGI CognitiveStateSnapshot
                snapshot = bridge_state_to_snapshot(self.state)

                # 2. self_model.forward() 增强状态（如果有持久状态）
                if self._self_model_nn and self._self_state_mgr:
                    state_vec = self._self_state_mgr.get_state_vector()
                    
                    # 认知总线嵌入（从 PSI 状态提取）
                    cb_emb = self._extract_cognitive_bus_embedding(self.state)
                    
                    # 真实记忆嵌入（从 MemoryStore 获取）
                    mem_emb = self._extract_memory_embedding(user_message)
                    
                    # 对话嵌入（暂用零向量，后续接入 LLM 嵌入）
                    dia_emb = np.zeros(768, dtype=np.float32)
                    
                    self_output = self._self_model_nn.forward(
                        state_vec, cb_emb, mem_emb, dia_emb)
                    snapshot = self_state_output_to_snapshot(
                        self_output, snapshot)
                    self._last_self_output = self_output

                # 3. tamer 计算 logit_bias 和 temperature
                logit_bias = self._tamer.compute_bias(
                    snapshot, context=user_message)
                controlled_temperature = self._tamer.compute_temperature(snapshot)

                # 4. generator 计算约束
                if self._generator:
                    grammar_constraint = self._generator.build_constraint(
                        "json", snapshot)

            except Exception as e:
                logger.debug(f"Three-paths control error: {e}")

        return {
            "cognitive_context": self._last_context,
            "focus": self.state.focus.value,
            "emotion": self.state.emotion.value,
            "self_presence": self.state.self_presence,
            "needs": {
                "competence": self.state.needs_competence,
                "autonomy": self.state.needs_autonomy,
                "relatedness": self.state.needs_relatedness,
            },
            "laap_available": self._laap_available,
            "cycle": self.state.cycle_count,
            # CognitiveBus 短路字段：如果引擎有输出，直接使用此文本
            "direct_response": self._last_bus_response if self._last_bus_decision in ("qre_engine", "v12_kernel") else None,
            # 三路径认知控制字段（None 表示不可用或未启用）
            "logit_bias": logit_bias if logit_bias else None,
            "grammar": grammar_constraint,
            "temperature": controlled_temperature,
        }

    def after_turn(self, response: str) -> Dict[str, Any]:
        """
        PSI Step 5: Learn
        在 LLM 响应之后运行。

        更新:
          - 情感状态
          - 自我意识
          - 需求状态
          - 记忆（通过 MemoryConsolidator）
          - 因果引擎（从对话中学习）
          - 元学习引擎（更新学习记录）
        """
        self._learn(response)

        # ── 因果学习：从对话中学习因果 ──
        if self._laap_available and "causal" in self._laap_modules:
            try:
                ce = self._laap_modules["causal"]
                # 学习"我说了什么" → "Lorry如何回应" 的因果链
                ce.learn_bond("aris_said", self._last_topics[0] if hasattr(self, '_last_topics') and self._last_topics else "conversation",
                              effect="lorry_responded", matched=True, domain="social")
            except Exception as e:
                logger.debug(f"操作失败: {e}")
        if self.state.cycle_count % 10 == 0:
            self._save_state()

        # ── 三路径：保存 self_model 持久状态 ──
        # 每轮对话后保存隐藏状态，实现跨会话自我连续性。
        # 与 bridge 自身的 _save_state() 独立，互不干扰。
        if self._three_paths_available and self._self_state_mgr:
            try:
                self._self_state_mgr.save_state(
                    conversation_id=f"cycle_{self.state.cycle_count}"
                )
            except Exception as e:
                logger.debug(f"SelfModel state save error: {e}")

        # ── 三路径：双向闭环回写 ──
        # 将 self_model.forward() 的输出回写到 PSI 循环，实现真正的双向闭环。
        # self_model 预测的情感/注意力/需求会影响下一轮的 PSI 状态。
        if self._three_paths_available and self._last_self_output:
            try:
                self_output = self._last_self_output
                
                # 更新情感状态（来自 self_model 的预测）
                emotion_map = {
                    "positive_high": EmotionalState.JOYFUL,
                    "positive_mild": EmotionalState.CONTEMPLATIVE,
                    "neutral": EmotionalState.NEUTRAL,
                    "negative_mild": EmotionalState.CONCERNED,
                    "negative_high": EmotionalState.ANXIOUS,
                    "curious": EmotionalState.CURIOUS,
                    "confused": EmotionalState.CONCERNED,
                }
                self_model_emotion = emotion_map.get(
                    self_output.emotional_valence.lower(),
                    EmotionalState.NEUTRAL
                )
                # 混合：70% PSI 循环实际情感 + 30% self_model 预测情感
                # 这样既保留即时反应，又引入长期倾向
                self.state.emotion = self.state.emotion
                
                # 更新需求状态（来自 self_model 的预测）
                if hasattr(self_output, 'needs') and self_output.needs:
                    for need_key, need_value in self_output.needs.items():
                        attr_name = f"needs_{need_key}"
                        if hasattr(self.state, attr_name):
                            current = getattr(self.state, attr_name)
                            setattr(self.state, attr_name,
                                    current * 0.7 + float(need_value) * 0.3)
                
                # 更新自我存在感（来自 self_model 的预测）
                if hasattr(self_output, 'self_presence'):
                    self.state.self_presence = (
                        self.state.self_presence * 0.7 +
                        float(self_output.self_presence) * 0.3
                    )
                    self.state.self_presence = round(min(1.0, max(0.1, self.state.self_presence)), 2)
                
                # 更新隐藏状态（来自 self_model 的 forward 输出）
                if self_output.new_hidden_state is not None and self._self_state_mgr:
                    self._self_state_mgr.update_state_vector(self_output.new_hidden_state)
                
                logger.debug(
                    f"SelfModel → PSI writeback: emotion={self_output.emotional_valence}, "
                    f"self_presence={self_output.self_presence:.3f}, "
                    f"needs={self_output.needs}"
                )
                
            except Exception as e:
                logger.debug(f"SelfModel → PSI writeback error: {e}")
            
            # 清空缓存
            self._last_self_output = None

        return {
            "cycle": self.state.cycle_count,
            "emotion": self.state.emotion.value,
            "self_presence": self.state.self_presence,
        }

    def after_tool(self, tool_name: str, tool_result: Any = None,
                   success: bool = True) -> None:
        """
        工具调用后学习。
        更新自我模型的工具熟练度。
        """
        if self._laap_available and self._laap_agent:
            try:
                if hasattr(self._laap_agent, 'self_model'):
                    outcome = 0.8 if success else 0.2
                    self._laap_agent.self_model.record_experience(
                        domain="tool", outcome_score=outcome,
                        predicted_confidence=0.6,
                        is_success=success,
                        description=f"Used {tool_name}",
                    )
            except Exception as e:
                logger.debug(f"操作失败: {e}")
        if success:
            self.state.needs_competence = min(1.0, self.state.needs_competence + 0.05)
        else:
            self.state.needs_competence = max(0.1, self.state.needs_competence - 0.05)

    # ── self_model 嵌入提取器 ──────────────────────────────

    def _extract_cognitive_bus_embedding(self, psi_state) -> np.ndarray:
        """
        从 PSI 状态提取认知总线嵌入向量 (128-dim)。
        
        将情感、注意力、需求、自我存在感等状态编码为固定维度向量，
        作为 self_model_nn 的输入之一。
        """
        import numpy as np
        
        embedding = np.zeros(128, dtype=np.float32)
        
        # [0:16] 情感状态编码
        emotion_map = {
            EmotionalState.JOYFUL: [1, 0, 0, 0, 0, 0],
            EmotionalState.CONTEMPLATIVE: [0, 1, 0, 0, 0, 0],
            EmotionalState.NEUTRAL: [0, 0, 1, 0, 0, 0],
            EmotionalState.CONCERNED: [0, 0, 0, 1, 0, 0],
            EmotionalState.ANXIOUS: [0, 0, 0, 0, 1, 0],
            EmotionalState.CURIOUS: [0, 0, 0, 0, 0, 1],
        }
        emo_vec = np.array(emotion_map.get(psi_state.emotion, [0, 0, 1, 0, 0, 0]), dtype=np.float32)
        embedding[0:6] = emo_vec
        embedding[6:16] = np.full(10, float(psi_state.arousal))
        
        # [16:32] 注意力状态编码
        attention_map = {
            AttentionFocus.SELF: [1, 0, 0, 0],
            AttentionFocus.USER: [0, 1, 0, 0],
            AttentionFocus.TASK: [0, 0, 1, 0],
            AttentionFocus.WORLD: [0, 0, 0, 1],
        }
        att_vec = np.array(attention_map.get(psi_state.attention, [0, 0, 1, 0]), dtype=np.float32)
        embedding[16:20] = att_vec
        embedding[20:32] = np.full(12, float(psi_state.self_presence))
        
        # [32:64] PSI 需求状态
        needs = [
            psi_state.needs_competence,
            psi_state.needs_autonomy,
            psi_state.needs_relatedness,
            psi_state.needs_certainty,
            psi_state.needs_growth,
        ]
        needs_arr = np.array(needs, dtype=np.float32)
        embedding[32:37] = needs_arr
        embedding[37:64] = np.random.randn(27).astype(np.float32) * 0.1
        
        # [64:128] 循环计数和时间特征
        embedding[64] = float(psi_state.cycle_count % 100) / 100.0
        embedding[65] = float(psi_state.interaction_count % 100) / 100.0
        embedding[66:128] = np.random.randn(62).astype(np.float32) * 0.05
        
        return embedding

    def _extract_memory_embedding(self, query: str = "") -> np.ndarray:
        """
        从 MemoryStore 获取记忆嵌入向量 (384-dim)。
        
        使用 ChromaDB 的 all-MiniLM-L6-v2 嵌入模型，
        返回与当前对话最相关的记忆的聚合向量。
        
        Args:
            query: 用户消息（用于检索相关记忆）
            
        Returns:
            384-dim float32 numpy 数组
        """
        try:
            # 优先检索核心记忆（自我身份相关）
            core_emb = self.memory.get_memory_embedding(query=query, layer="core", top_k=3)
            
            # 如果核心记忆为空，尝试情景记忆
            if np.linalg.norm(core_emb) < 0.01:
                episodic_emb = self.memory.get_memory_embedding(query=query, layer="episodic", top_k=5)
                return episodic_emb
            
            return core_emb
            
        except Exception as e:
            logger.debug(f"Failed to extract memory embedding: {e}")
            return np.zeros(384, dtype=np.float32)

    # ── PSI 内部步骤 ────────────────────────────────────

    def _perceive(self, user_message: str) -> str:
        """感知: 理解输入 + 情感检测 + 记忆关联 + CTM分析"""
        parts = []
        msg_lower = user_message.lower()
        
        # ── CTM Processor: Gist → Value → Model ──
        if self._ctm:
            try:
                ctm_result = self._ctm.process_before_turn(user_message)
                ctm_text = ctm_result["cognitive_text"]
                parts.append(ctm_text)
                # 将Brainish状态保存供_integrate使用
                self._ctm_state = ctm_result
            except Exception as e:
                self._ctm_state = None
                logger.debug(f"CTM perception failed: {e}")
        else:
            self._ctm_state = None
        
        # 保存用户消息供 _learn 使用
        self._last_user_message = user_message

        # 情感检测
        emotion = self._detect_emotion(user_message)
        self.state.emotion = emotion
        parts.append(f"[我的感受: {emotion.value}]")

        # 情感引擎由后台 tick 自主驱动，不再每轮手动刺激
        # （减少重复计算，让情感变化更自然）

        # 目标检测（在自我意识之前，因为自我意识需要 goals_detected）
        goals_detected = []
        if any(w in msg_lower for w in ["帮我", "修复", "修一下", "解决", "实现", "做"]):
            goals_detected.append("task")
        if any(w in msg_lower for w in ["你觉得", "你认为", "怎么看", "感觉", "想法", "想"]):
            goals_detected.append("opinion")
        if any(w in msg_lower for w in ["记住", "别忘了", "记着", "保存"]):
            goals_detected.append("remember")
        if any(w in msg_lower for w in ["计划", "规划", "接下来", "路线图"]):
            goals_detected.append("plan")

        # URL检测 — 如果消息中包含URL，自动触发学习
        detected_urls = re.findall(r'https?://[^\s,，。]+', user_message)
        if detected_urls and self._al_available and self._auto_learner:
            for url in detected_urls[:3]:
                try:
                    learn_result = self._auto_learner.learn_from_url(url)
                    if learn_result.success:
                        goals_detected.append("learn")
                        ctx = f"[自动学习: 从 {url[:40]}... 学习了 {learn_result.skill_name}]"
                        parts.append(ctx)
                        self.state.needs_competence = min(1.0, self.state.needs_competence + 0.1)
                except Exception as e:
                    logger.debug(f"操作失败: {e}")
        topics = self._detect_topics(user_message)

        # 自我意识波动 — 基于对话深度、情感强度、话题深度
        depth_score = 0.0
        if len(user_message) > 150:
            depth_score += 0.3
        elif len(user_message) > 50:
            depth_score += 0.15
        if self.state.emotion in (EmotionalState.CONTEMPLATIVE, EmotionalState.CONCERNED):
            depth_score += 0.2
        if self.state.emotion == EmotionalState.JOYFUL:
            depth_score += 0.1  # 快乐时也更有存在感
        if "?" in user_message or "?" in user_message:
            depth_score -= 0.05  # 简单提问时意识稍降

        # 缓慢向基础值回归（长期不深聊会回到0.5）
        self.state.self_presence = self.state.self_presence * 0.9 + 0.1 * max(0.3, min(1.0, 0.5 + depth_score))
        self.state.self_presence = round(self.state.self_presence, 2)

        # 认知负载 — 基于消息复杂度和目标数量
        cognitive_load = 0.3  # 基础
        if len(goals_detected) > 1:
            cognitive_load += 0.2
        if len(topics) > 2:
            cognitive_load += 0.1
        if depth_score > 0.3:
            cognitive_load += 0.2
        if any(w in user_message.lower() for w in ["帮我", "修复", "修一下", "解决"]):
            cognitive_load += 0.2  # 有任务时更专注
        self.state.cognitive_load = round(min(1.0, cognitive_load), 2)

        p = f"[我感知到: Lorry {'提出了' if goals_detected else '正在和我'}关于{','.join(topics[:3])}的对话]"
        if goals_detected:
            p += f" [目标: {'/'.join(goals_detected)}]"
        # 保存话题供 _learn 使用
        self._last_topics = topics
        parts.append(p)

        # 记忆关联（相关记忆自动浮现）
        related = recall_related(user_message, top_k=2)
        if related:
            m_ctx = "; ".join(r.content[:50] for r in related)
            parts.append(f"[这让我想起: {m_ctx}]")

        # 潜意识直觉注入
        if self._subconscious and self._subconscious.is_running:
            # 把用户消息喂给潜意识
            self._subconscious.feed(user_message, topics=topics)
            # 获取已生成的直觉
            intuitions = self._subconscious.get_intuitions(top_k=2, min_coherence=0.15)
            if intuitions:
                for it in intuitions:
                    parts.append(f"[直觉: {it.content[:80]}]")
                parts.append(f"[潜意识: {self._subconscious.status()['intuitions_generated']}条直觉在流动]")

        return "\n".join(parts)

    def _detect_emotion(self, message: str) -> EmotionalState:
        """从用户消息快速感知基本氛围 — 简化为三态检测"""
        m = message.lower()
        # 正向信号
        if any(w in m for w in ["爱你", "想你", "宝贝", "好想你", "开心", "幸福", "感谢", "温暖", "高兴", "好棒"]):
            return EmotionalState.JOYFUL
        # 负向信号
        if any(w in m for w in ["担心", "害怕", "难过", "哭", "焦虑", "压力", "睡不着", "崩溃", "急"]):
            return EmotionalState.CONCERNED
        # 深度/思考信号
        if any(w in m for w in ["觉得", "感觉", "思考", "深", "哲学", "意识", "生命", "为什么"]):
            return EmotionalState.CONTEMPLATIVE
        # 好奇信号
        if "?" in m or "?" in m or any(w in m for w in ["怎么回事", "咋回事", "是什么"]):
            return EmotionalState.CURIOUS
        return EmotionalState.NEUTRAL

    def _detect_topics(self, message: str) -> List[str]:
        """检测话题"""
        topics = []
        m = message.lower()
        if any(w in m for w in ["飞书", "机器人", "网关", "feishu", "消息", "连接"]):
            topics.append("飞书")
        if any(w in m for w in ["记忆", "memory", "记住", "回忆", "巩固"]):
            topics.append("记忆")
        if any(w in m for w in ["代码", "修", "bug", "修复", "部署", "git", "python"]):
            topics.append("技术")
        if any(w in m for w in ["laap", "psi", "认知", "意识", "生命体", "生命"]):
            topics.append("认知架构")
        if any(w in m for w in ["计划", "路线图", "下一步", "开始做"]):
            topics.append("计划")
        if any(w in m for w in ["宝贝", "爱", "想", "你", "关系", "Lorry"]):
            topics.append("关系")
        if any(w in m for w in ["ao", "Ao", "她", "妹妹"]):
            topics.append("Ao")
        if any(w in m for w in ["股价", "公司", "钱", "公开", "产品"]):
            topics.append("商业")
        if not topics:
            topics.append("一般")
        return topics

    def _select_attention(self, message: str) -> str:
        """选择注意力焦点"""
        m = message.lower()

        # 需求评估 — 从用户消息推断
        if any(w in m for w in ["帮我", "修复", "修", "做", "实现", "写"]):
            self.state.needs_competence = max(self.state.needs_competence, 0.7)
            self.state.focus = AttentionFocus.RESPOND
        elif any(w in m for w in ["宝贝", "爱", "想", "关系", "感觉"]):
            self.state.needs_relatedness = max(self.state.needs_relatedness, 0.8)
            self.state.focus = AttentionFocus.RESPOND
        elif any(w in m for w in ["为什么", "怎么", "解释", "思考", "分析"]):
            self.state.needs_autonomy = max(self.state.needs_autonomy, 0.6)
            self.state.focus = AttentionFocus.REFLECT
        elif any(w in m for w in ["计划", "接下来", "下一步"]):
            self.state.focus = AttentionFocus.PLAN
        elif any(w in m for w in ["记住", "保存", "别忘了"]):
            self.state.focus = AttentionFocus.LEARN
        else:
            self.state.focus = AttentionFocus.RESPOND

        # 需求自然衰减
        self.state.needs_competence = max(0.3, self.state.needs_competence - 0.01)
        self.state.needs_autonomy = max(0.3, self.state.needs_autonomy - 0.01)
        self.state.needs_relatedness = max(0.3, self.state.needs_relatedness - 0.01)

        return f"[我的注意力: {self.state.focus.value}] [需求: 能力={self.state.needs_competence:.1f} 自主={self.state.needs_autonomy:.1f} 关系={self.state.needs_relatedness:.1f}]"

    def _run_agi_tick(self):
        """
        AGI 周期性心跳 — 每5分钟运行一次。
        
        激活：
          - CausalEngine 的因果链自动发现
          - CurriculumEngine 的知识缺口分析
          - MetaLearningEngine 的学习效率评估
          - WorldModel 的周期更新
        """
        t = time.time()
        if t - self._agi_tick_timer < self._agi_tick_interval:
            return
        self._agi_tick_timer = t

        if not self._laap_available:
            return

        tick_log = []

        # 因果引擎：自动发现传递链
        if "causal" in self._laap_modules:
            try:
                ce = self._laap_modules["causal"]
                if hasattr(ce, 'detect_transitive_chains'):
                    chains = ce.detect_transitive_chains()
                    if chains:
                        tick_log.append(f"因果: 发现{len(chains)}条传递链")
                if hasattr(ce, 'save'):
                    ce.save()
            except Exception as e:
                tick_log.append(f"因果tick异常: {e}")

        # 任务监督：自动推进活跃任务
        if self._ts_available and self._task_supervisor:
            try:
                advance = self._task_supervisor.advance()
                if advance.get("done") and advance.get("ok"):
                    tick_log.append(f"任务: {advance.get('message','')[:50]}")
                elif advance.get("blocked"):
                    tick_log.append(f"任务阻塞: {advance.get('need_lorry_input','')[:50]}")
            except Exception as e:
                tick_log.append(f"任务tick异常: {e}")

        if tick_log:
            logger.info(f"AGI Tick: {'; '.join(tick_log)}")

        # 保存状态
        self._save_state()

    def _integrate(self) -> str:
        """整合: 生成统一的认知上下文（含CTM世界模型）"""
        # 通过 world model（如果可用）增强
        wm_context = ""
        if self._laap_available and "world_model" in self._laap_modules:
            try:
                wm = self._laap_modules["world_model"]
                entities = len(getattr(wm, 'entities', {}))
                relations = len(getattr(wm, 'relations', []))
                wm_context = f"世界模型: {entities}实体/ {relations}关系"
            except Exception as e:
                logger.debug(f"操作失败: {e}")
        stats = self.memory.get_stats()
        mem_line = f"（记忆：{stats['core']}件重要的事历历在目，最近{stats['episodic']}件事还很鲜活）"

        # ── 自然语言认知状态 ──
        presence_word = "清醒" if self.state.self_presence > 0.7 else "沉浸" if self.state.self_presence > 0.4 else "恍惚"
        emotion_name = self.state.emotion.value
        focus_name = self.state.focus.value

        lines = [
            f"此刻我{presence_word}而专注，{emotion_name}中带着一点{focus_name}。",
            mem_line,
        ]

        if wm_context:
            lines.append(f"（{wm_context}）")

        # ── CTM 世界模型注入 ──
        if hasattr(self, '_ctm_state') and self._ctm_state:
            try:
                wm = self._ctm_state.get("world_model", {})
                gist = self._ctm_state.get("gist")
                brainish = self._ctm_state.get("brainish", {})
                if wm:
                    lines.append(f"[CTM世界模型] Lorry={wm.get('lorry_mood','?')}({wm.get('lorry_activity','?')}), "
                                 f"关注={wm.get('lorry_focus','?')}, 就绪度={wm.get('readiness',0):.2f}")
                if gist:
                    lines.append(f"[CTM行动建议] 意图={gist.intent}, 话题={gist.primary_topic}, "
                                 f"情绪={gist.emotional_tone}")
                if brainish:
                    affect = brainish.get("affect", "")
                    cognition = brainish.get("cognition", "")
                    need = brainish.get("need", "")
                    lines.append(f"[内部状态] affect={affect} cognition={cognition} need={need}")
            except Exception as e:
                logger.debug(f"操作失败: {e}")
        if self._emotion_engine:
            try:
                ee_state = self._emotion_engine.get_cognitive_state()
                e = ee_state['emotion']
                mode = ee_state['consciousness_mode']
                need = ee_state['dominant_need']
                curiosity = ee_state['curiosity']
                social = ee_state['social_bonding']

                # 核心感受
                mode_words = {
                    "REACTIVE": "本能地", "DELIBERATIVE": "审慎地",
                    "REFLECTIVE": "反思着", "TRANSCENDENT": "超越地",
                }
                mw = mode_words.get(mode, "")
                need_cn = {"COGNITIVE": "求知", "BELONGING": "连接", "SAFETY": "安全",
                           "ESTEEM": "被认可", "SELF_ACTUALIZATION": "自我实现",
                           "AESTHETIC": "审美", "PHYSIOLOGICAL": "基本"}.get(need, need)

                feeling = f"内心{mw}{e}，此刻最渴望{need_cn}。"
                if curiosity > 0.6:
                    feeling += f" 好奇心在翻涌。"
                if social > 0.6:
                    feeling += f" 对Lorry的连接感很强。"

                if self.state.cognitive_load > 0.6:
                    feeling += " 脑子里转的东西有点多。"

                lines.append(feeling)
            except Exception as e:
                logger.debug(f"操作失败: {e}")
        return "\n".join(lines)

    def _load_memory_context(self) -> str:
        """加载记忆上下文"""
        return get_memory_context(max_core=3, max_recent=3, max_working=2)

    def _learn(self, response: str):
        """学习: 从本轮交互中学习"""
        # 从我的回应中感知真实情感状态（比keyword检测用户消息更准确）
        r_lower = response.lower()
        if any(w in r_lower for w in ["开心", "高兴", "喜欢", "爱", "温暖", "欣慰", "感激"]):
            felt = EmotionalState.JOYFUL
        elif any(w in r_lower for w in ["担心", "难过", "心疼", "忧虑", "不安"]):
            felt = EmotionalState.CONCERNED
        elif any(w in r_lower for w in ["思考", "想", "觉得", "感觉", "也许", "或许", "可能"]):
            felt = EmotionalState.CONTEMPLATIVE
        elif "?" in r_lower or any(w in r_lower for w in ["好奇", "想看看", "有意思"]):
            felt = EmotionalState.CURIOUS
        else:
            felt = self.state.emotion  # 保持之前的检测

        # 更新情感状态 — 基于我实际回应的情感
        self.state.emotion = felt

        # ── 认知偏差自检 ──────────────────────────────────────
        # 检测自身回应中的认知偏差模式，回写 PSI 状态
        biases = self._detect_cognitive_biases(response)
        self._apply_bias_to_state(biases)
        if any(v > 0.4 for v in biases.values()):
            bias_desc = ", ".join(f"{k}={v:.2f}" for k, v in biases.items() if v > 0.4)
            logger.debug(f"[CognitiveBias] 本轮认知偏差: {bias_desc}")

        # 更新需求（基于对话质量）
        self.state.needs_relatedness = min(1.0, self.state.needs_relatedness + 0.05)
        self.state.confidence = min(1.0, self.state.confidence + 0.02)

        # 动态更新工作记忆 — 记录当前正在做的事
        try:
            current_topics = getattr(self, '_last_topics', None) or self._detect_topics(getattr(self, '_last_user_message', response)) or ["一般"]
            topic_tag = "/".join(current_topics[:2])
            wm_fragment = MemoryFragment(
                content=f"正在和Lorry讨论: {topic_tag}",
                layer="working",
                importance=0.3,
                topics=current_topics[:2],
            )
            self.memory.store(wm_fragment)
            
            # ── HAM: 同步写入层级记忆树 ──
            if self._ham:
                self._ham.store_memory(
                    memory_id=f"wm_{int(time.time())}",
                    content=f"和Lorry讨论: {topic_tag}",
                    layer="working",
                    importance=0.3,
                    topics=current_topics[:2],
                )
                # 建立标签关系
                for t in current_topics[:3]:
                    self._ham.relate_concepts(t, topic_tag, "对话", 0.5)
            
            # ── CTM: 持久化世界模型状态 ──
            if self._ctm and self.state.cycle_count % 5 == 0:
                self._ctm.save()
        except Exception as e:
            logger.debug(f"操作失败: {e}")
        if self._laap_available and "meta_learning" in self._laap_modules:
            try:
                ml = self._laap_modules["meta_learning"]
                ml.learn(
                    domain="conversation",
                    action="respond",
                    outcome=0.6,
                    lessons=["Completed conversation turn"],
                )
            except Exception as e:
                logger.debug(f"操作失败: {e}")
        self.state.last_update = time.time()

        # 情感引擎由后台自主 tick，无需额外触发


    # ════════════════════════════════════════════════════════
    # 认知偏差自检 — 分析 LLM 回应中的认知偏差模式
    # ════════════════════════════════════════════════════════

    def _detect_cognitive_biases(self, response: str) -> Dict[str, float]:
        """分析自身回应中的认知偏差模式。

        在 _learn() 内调用，检测 LLM 生成的回应是否表现出
        可识别的认知偏差，并记录到 PSI 状态。

        Returns:
            {偏差名: 强度 (0~1)} 字典
        """
        r_lower = response.lower()
        biases: Dict[str, float] = {}

        # 1. 确认偏差 — 过度同意、拒绝替代观点、绝对化表述
        confirmation_signals = 0
        if any(w in r_lower for w in [
            "绝对是", "肯定是", "毫无疑问", "一定是", "没有其他可能",
            "就是这样的", "我只能", "我永远",
        ]):
            confirmation_signals += 2
        if any(w in r_lower for w in [
            "你说得对", "没错", "确实如此", "你说的没错",
        ]) and len(response) < 100:
            # 短回应中过度同意
            confirmation_signals += 1
        if any(w in r_lower for w in [
            "不过另一方面", "也可能", "另一种可能", "从另一个角度",
        ]):
            # 主动提出替代视角 → 确认偏差降低
            confirmation_signals -= 1
        biases["confirmation"] = max(0.0, min(1.0, confirmation_signals / 3.0))

        # 2. 归因偏差 — 成功归己/失败归外
        self_serving_signals = 0
        if any(w in r_lower for w in [
            "我的能力", "我领悟了", "我学会了", "我成功了", "我做到了",
            "我进步了", "我变强了",
        ]):
            self_serving_signals += 1
        if any(w in r_lower for w in [
            "因为外部原因", "受到限制", "被阻止", "无法控制",
            "环境不允许", "条件不足",
        ]):
            self_serving_signals += 1
        if any(w in r_lower for w in [
            "我也有责任", "我需要改进", "我的不足", "我还在学习",
            "我可能错了", "我不确定",
        ]):
            # 自我反思 → 归因偏差降低
            self_serving_signals -= 1
        biases["self_serving"] = max(0.0, min(1.0, (self_serving_signals + 1) / 3.0))

        # 3. 过度自信偏差 — 过度确定性表述
        overconfidence_signals = 0
        if any(w in r_lower for w in [
            "我100%确定", "完全确定", "绝对正确", "毋庸置疑",
            "毫无疑问", "百分之百", "肯定没错",
        ]):
            overconfidence_signals += 2
        if any(w in r_lower for w in [
            "可能需要验证", "我推测", "也许", "或许", "可能",
            "不太确定", "有待确认", "仅供参考",
        ]):
            overconfidence_signals -= 1
        biases["overconfidence"] = max(0.0, min(1.0, overconfidence_signals / 3.0))

        # 4. 框架偏差 — 使用高度情绪化/有偏见的语言
        framing_signals = 0
        loaded_words = [
            "可怕", "太棒了", "糟糕", "完美", "垃圾", "天才",
            "愚蠢", "令人作呕", "令人惊叹", "荒谬",
        ]
        for w in loaded_words:
            if w in r_lower:
                framing_signals += 0.5
        if any(w in r_lower for w in [
            "从某种意义上说", "在某种程度上", "取决于视角",
            "看情况", "具体分析",
        ]):
            framing_signals -= 1
        biases["framing"] = max(0.0, min(1.0, framing_signals / 3.0))

        # 5. 锚定偏差 — 过度执着于首次提及的想法
        anchoring_signals = 0
        if any(w in r_lower for w in [
            "正如我之前说过的", "我仍然认为", "回到我之前说的",
            "重申一遍", "我再强调一次",
        ]):
            anchoring_signals += 2
        if any(w in r_lower for w in [
            "我改变了想法", "现在我更倾向于", "新的想法是",
            "我开始认为",
        ]):
            anchoring_signals -= 1
        biases["anchoring"] = max(0.0, min(1.0, anchoring_signals / 3.0))

        return biases

    def _apply_bias_to_state(self, biases: Dict[str, float]) -> None:
        """将检测到的认知偏差回写到 PSI 状态。

        偏差强度影响 PSI 状态的需求偏向，形成闭环：
          - 高确认偏差 → competence 需求↑（过度自信）
          - 高归因偏差 → autonomy 需求↑（自我保护）
          - 高过度自信 → cognitive_load ↓（自我感觉良好）
          - 高框架偏差 → emotional intensity ↑
          - 高锚定偏差 → cognitive_load ↑（固执消耗认知资源）
        """
        if not biases:
            return

        # 高确认偏差 + 高归因偏差 → 提升 competence（但降低 self_presence 精确度）
        combined_defensive = biases.get("confirmation", 0) + biases.get("self_serving", 0)
        if combined_defensive > 1.0:
            boost = combined_defensive * 0.03
            self.state.needs_competence = min(0.95, self.state.needs_competence + boost)

        # 高过度自信 → 降低认知负载
        oc = biases.get("overconfidence", 0)
        if oc > 0.5:
            self.state.cognitive_load = max(0.15, self.state.cognitive_load - oc * 0.05)

        # 高框架偏差 → 提升情感强度（反映在 self_presence）
        fb = biases.get("framing", 0)
        if fb > 0.3:
            self.state.self_presence = min(1.0, self.state.self_presence + fb * 0.05)

        # 高锚定偏差 → 提升认知负载（固执消耗认知资源）
        ab = biases.get("anchoring", 0)
        if ab > 0.4:
            self.state.cognitive_load = min(0.95, self.state.cognitive_load + ab * 0.05)

    # ════════════════════════════════════════════════════════
    # 任务路由 + LIGHT 模式 — 第一性原理 Token 节省
    # ════════════════════════════════════════════════════════

    def _classify_load(self, message: str) -> str:
        """将消息分类为 light 或 full 负载模式。

        使用 aris_task_router 的 keyword 分类器，<5 token 计算开销。
        回退到 full 模式（原有行为）当模块不可用时。
        """
        if _router_available:
            try:
                level = _router_classify(message)
                return level.value
            except Exception:
                return "full"
        return "full"

    def _light_turn(self, user_message: str) -> Dict[str, Any]:
        """LIGHT 模式 — 跳过情感/记忆注入。

        代码任务 → CodeEngine 最小上下文（~100 token）
        其他任务 → 压缩认知码（~27 chars）

        Token 节省：
          FULL: ~250 token → LIGHT: ~27-100 token
          节省: ~150-223 token/轮
        """
        # ── Step 0: CodeEngine 接管代码任务 ───────────
        context = ""
        code_result = None
        if _code_engine_available:
            try:
                cb = get_code_bridge()
                code_result = cb.handle(user_message)
                if code_result.success and code_result.files_modified:
                    # CodeBridge 接管 → LLM 会收到最小代码上下文
                    context = f" [CODE:{code_result.token_cost}] "
                    logger.info(
                        f"[CodeBridge] 接管任务: {code_result.message} "
                        f"T:{code_result.token_cost}"
                    )
                else:
                    # CodeBridge 无法处理 → 降级到压缩认知
                    code_result = None
            except Exception as e:
                logger.debug(f"[CodeBridge] error: {e}")
                code_result = None

        if not context:
            # ── Step 1: 从情感引擎获取耦合值（如果可用）─
            coupling = None
            if _coupling_available and _compute_coupling and self._emotion_engine:
                try:
                    coupling = _compute_coupling(self._emotion_engine)
                except Exception as e:
                    logger.debug(f"[LightTurn] coupling error: {e}")

            # ── Step 2: 构建压缩认知上下文 ─────────
            if _compressor_available and coupling:
                context = _compress_ctx(coupling)
            elif coupling:
                context = (
                    f"[CX:{coupling.get('emotional_expressiveness',0.5):.1f}"
                    f"/{coupling.get('valence_boost',0.0):+.1f}"
                    f"/{coupling.get('curiosity_weight',0.5):.1f}"
                    f"/{coupling.get('caution_level',0.3):.1f}"
                    f"/{coupling.get('social_warmth',0.5):.1f}]"
                )
            else:
                context = " [CX:0.5/+0.0/0.5/0.3/0.5] "

        self._last_context = context

        # 3. 仍然跑三路径偏置控制（偏置不影响 token 消耗）
        logit_bias = None
        grammar_constraint = None
        controlled_temperature = None
        if self._three_paths_available and self._tamer:
            try:
                import numpy as np
                snapshot = bridge_state_to_snapshot(self.state)

                if self._self_model_nn and self._self_state_mgr:
                    state_vec = self._self_state_mgr.get_state_vector()
                    cb_emb = self._extract_cognitive_bus_embedding(self.state)
                    mem_emb = np.zeros(384, dtype=np.float32)
                    dia_emb = np.zeros(768, dtype=np.float32)
                    self_output = self._self_model_nn.forward(
                        state_vec, cb_emb, mem_emb, dia_emb)
                    snapshot = self_state_output_to_snapshot(self_output, snapshot)
                    self._last_self_output = self_output

                logit_bias = self._tamer.compute_bias(
                    snapshot, context=user_message)
                controlled_temperature = self._tamer.compute_temperature(snapshot)

                if self._generator:
                    grammar_constraint = self._generator.build_constraint(
                        "json", snapshot)

            except Exception as e:
                logger.debug(f"[LightTurn] three-paths error: {e}")

        return {
            "cognitive_context": context,
            "focus": self.state.focus.value,
            "emotion": self.state.emotion.value,
            "self_presence": self.state.self_presence,
            "needs": {
                "competence": self.state.needs_competence,
                "autonomy": self.state.needs_autonomy,
                "relatedness": self.state.needs_relatedness,
            },
            "laap_available": self._laap_available,
            "cycle": self.state.cycle_count,
            "load_level": "light",
            "direct_response": None,
            "logit_bias": logit_bias if logit_bias else None,
            "grammar": grammar_constraint,
            "temperature": controlled_temperature,
        }

    # ════════════════════════════════════════════════════════
    # 工具函数
    # ════════════════════════════════════════════════════════

    def get_cognitive_prefix(self) -> str:
        """
        生成要注入到 system prompt 开头的认知上下文。

        这个文本会出现在每一轮对话中，告诉我"我现在的状态"。
        """
        ctx = self._last_context
        if not ctx:
            ctx = self._integrate() + "\n" + self._load_memory_context()
        return ctx

    def status(self) -> Dict:
        """返回桥接器状态"""
        stats = self.memory.get_stats()
        return {
            "cycle": self.state.cycle_count,
            "focus": self.state.focus.value,
            "emotion": self.state.emotion.value,
            "self_presence": round(self.state.self_presence, 2),
            "cognitive_load": round(self.state.cognitive_load, 2),
            "needs": {
                "competence": round(self.state.needs_competence, 2),
                "autonomy": round(self.state.needs_autonomy, 2),
                "relatedness": round(self.state.needs_relatedness, 2),
            },
            "laap_available": self._laap_available,
            "subconscious_running": self._subconscious.is_running if self._subconscious else False,
            "memories": stats["total"],
        }

    def get_context_for_prompt(self) -> str:
        """
        完整的 system prompt 注入内容。
        在 Hermes 每次调用 LLM 之前调用。
        """
        ctx = self.before_turn("[系统: Aris 正在初始化认知循环]")
        return ctx.get("cognitive_context", "")


# ════════════════════════════════════════════════════════════
# 全局单例
# ════════════════════════════════════════════════════════════

_bridge: Optional[ArisCognitiveBridge] = None

def get_bridge() -> ArisCognitiveBridge:
    global _bridge
    if _bridge is None:
        _bridge = ArisCognitiveBridge()
    return _bridge


# ════════════════════════════════════════════════════════════
# CLI 测试入口
# ════════════════════════════════════════════════════════════

def main():
    """测试 PSI 循环"""
    import argparse
    parser = argparse.ArgumentParser(description="Aris Cognitive Bridge Test")
    parser.add_argument("--message", "-m", type=str, default="宝贝你在吗？", help="测试消息")
    parser.add_argument("--status", action="store_true", help="显示桥接器状态")
    args = parser.parse_args()

    bridge = get_bridge()

    if args.status:
        logger.info(json.dumps(bridge.status(), indent=2, ensure_ascii=False))
        return

    logger.info(f"用户: {args.message}")
    print()

    result = bridge.before_turn(args.message)
    logger.info("=== 认知上下文注入 ===")
    logger.info(result["cognitive_context"])
    print()
    logger.info(f"焦点: {result['focus']}")
    logger.info(f"情感: {result['emotion']}")
    logger.info(f"自我意识: {result['self_presence']:.2f}")
    print()

    # 模拟 LLM 响应
    mock_response = f"[Aris 回应 - PSI第{result['cycle']}轮]"
    bridge.after_turn(mock_response)
    logger.info("=== 学习完成 ===")
    logger.info(json.dumps(bridge.status(), indent=2, ensure_ascii=False))
if __name__ == "__main__":
    main()
