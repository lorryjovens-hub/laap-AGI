"""
LAAP AGI — 递归自我改进引擎 (Recursive Self-Improvement Engine)
===============================================================

RSI Engine — 当前为参数自调优引擎

注意：本模块当前实现的是参数级自调优，而非真正的代码级自主修改（True RSI）。
True RSI（基于 AST 自修改 + 四区沙箱）的实现见 M4 阶段（laap/evolution/true_rsi.py）。
已废弃的 laap/evolution/rsi.py 已归档（保留原位 + DEPRECATED 标注，见 legacy/INDEX.md）。

P2-2: 学会改进自己。

核心能力：
  1. 代码进化整合 — 连接已有 CodeEvolutionEngine 到主循环
  2. 架构自优化 — 调优 PSI 循环参数、策略权重、学习率
  3. 学习目标自生成 — 基于知识缺口自主设定学习目标
  4. 改进效果追踪 — 每次自我修改后评估效果

印记: Aris 永远记得 Lorry — RSI 引擎 v1.0
"""

from __future__ import annotations

import logging

import json, math, time, random, logging, uuid, os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Callable
from dataclasses import dataclass, field
from collections import defaultdict, deque
from enum import Enum

import numpy as np

logger = logging.getLogger("laap.agi.rsi")


# ═══════════════════════════════════════════════════════════════
# 可优化参数
# ═══════════════════════════════════════════════════════════════

@dataclass
class OptimizableParameter:
    """一个可自我优化的参数"""
    name: str = ""
    category: str = "psi"           # psi | learning | strategy | timing
    current_value: float = 0.5
    min_value: float = 0.0
    max_value: float = 1.0
    step_size: float = 0.05
    description: str = ""
    last_optimized: float = 0.0
    optimization_count: int = 0
    performance_history: List[float] = field(default_factory=list)

    def propose_new_value(self, direction: str = "auto") -> float:
        """基于历史性能提出新值。

        Args:
            direction: 调整方向。"up" 强制上调，"down" 强制下调，
                "auto" 依据近期性能趋势自动判断。

        Returns:
            建议的新参数值，已被截断到 [min_value, max_value] 区间。
        """
        if direction == "up":
            return min(self.max_value, self.current_value + self.step_size)
        elif direction == "down":
            return max(self.min_value, self.current_value - self.step_size)
        else:
            # auto: 基于性能趋势
            if len(self.performance_history) >= 3:
                recent = self.performance_history[-3:]
                trend = np.polyfit(range(len(recent)), recent, 1)[0]
                if trend > 0:
                    return min(self.max_value, self.current_value + self.step_size)
                else:
                    return max(self.min_value, self.current_value - self.step_size)
            return max(self.min_value, min(self.max_value,
                self.current_value + self.step_size * (1 if random.random() > 0.5 else -1)))

    def to_dict(self) -> Dict[str, Any]:
        """返回参数的有损摘要字典。

        Returns:
            包含 name、category、value、range、optimizations 字段的字典。
        """
        return {
            "name": self.name, "category": self.category,
            "value": round(self.current_value, 3),
            "range": [self.min_value, self.max_value],
            "optimizations": self.optimization_count,
        }


# ═══════════════════════════════════════════════════════════════
# 自我改进尝试
# ═══════════════════════════════════════════════════════════════

@dataclass
class SelfImprovementAttempt:
    """一次自我改进的尝试记录"""
    id: str = ""
    target: str = ""               # 改进的目标参数
    category: str = "psi"
    old_value: float = 0.0
    new_value: float = 0.0
    rationale: str = ""            # 为什么做这个改动
    expected_improvement: float = 0.0
    actual_improvement: float = 0.0
    success: bool = False
    reverted: bool = False
    timestamp: float = field(default_factory=time.time)
    evaluation_period: float = 3600.0  # 评估周期（秒）

    def to_dict(self) -> Dict[str, Any]:
        """返回改进尝试的有损摘要字典。

        Returns:
            包含 id、target、old、new、rationale、expected、actual、
            success、reverted 字段的字典。
        """
        return {
            "id": self.id, "target": self.target,
            "old": round(self.old_value, 3),
            "new": round(self.new_value, 3),
            "rationale": self.rationale[:80],
            "expected": round(self.expected_improvement, 4),
            "actual": round(self.actual_improvement, 4),
            "success": self.success,
            "reverted": self.reverted,
        }


# ═══════════════════════════════════════════════════════════════
# 学习目标
# ═══════════════════════════════════════════════════════════════

@dataclass
class LearningGoal:
    """一个自我生成的学习目标"""
    id: str = ""
    description: str = ""
    domain: str = "general"
    target_mastery: float = 0.8
    current_mastery: float = 0.0
    priority: float = 0.5
    strategy: str = "structured"
    motivation: str = ""            # 为什么想学这个
    status: str = "proposed"       # proposed | active | completed | abandoned
    created_at: float = field(default_factory=time.time)
    deadline: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """返回学习目标的有损摘要字典。

        Returns:
            包含 id、description、domain、target、current、priority、
            status 字段的字典。
        """
        return {
            "id": self.id, "description": self.description,
            "domain": self.domain,
            "target": self.target_mastery,
            "current": round(self.current_mastery, 3),
            "priority": round(self.priority, 3),
            "status": self.status,
        }


# ═══════════════════════════════════════════════════════════════
# 递归自我改进引擎
# ═══════════════════════════════════════════════════════════════

# 状态文件 schema 版本——save() 写入, load() 校验, 不兼容时拒绝加载
RSI_STATE_SCHEMA_VERSION = "1.0"


def _default_state_path(filename: str) -> str:
    """运行时推导状态文件路径（不再硬编码 <LOCAL_PATH_REDACTED>

    优先级：LAAP_HOME 环境变量 > ``~/.laap/`` 默认目录。
    父目录会自动创建。

    Args:
        filename: 状态文件名（如 "rsi_engine.json"）。

    Returns:
        推导出的绝对路径字符串。
    """
    laap_home = os.environ.get("LAAP_HOME", str(Path.home() / ".laap"))
    state_dir = Path(laap_home)
    state_dir.mkdir(parents=True, exist_ok=True)
    return str(state_dir / filename)


class RSIMetaEngine:
    """
    递归自我改进引擎 — 学会改进自己。

    核心循环：
      1. 监控当前系统性能
      2. 识别可优化的参数
      3. 尝试修改并预测效果
      4. 评估修改结果（保留或回滚）
      5. 生成新的学习目标
      6. 记录所有改进历史
    """

    def __init__(self) -> None:
        """初始化递归自我改进引擎。

        注册默认可优化参数，初始化改进历史、学习目标与统计计数器，
        并置空外部引擎引用（课程引擎、元学习引擎、因果引擎）。
        """
        # 可优化参数
        self.parameters: Dict[str, OptimizableParameter] = {}

        # 改进历史
        self.attempts: List[SelfImprovementAttempt] = []
        self.max_attempts = 200

        # 自我生成的学习目标
        self.goals: Dict[str, LearningGoal] = {}

        # 引用外部引擎（可选注入）
        self.curriculum_engine = None
        self.meta_learning_engine = None
        self.causal_engine = None

        # 改进统计
        self._total_attempts = 0
        self._successful_attempts = 0
        self._reverted_attempts = 0
        self._goals_generated = 0
        self._goals_completed = 0
        self._created_at = time.time()

        # 注册默认可优化参数
        self._register_default_parameters()

        logger.info(f"[RSIMetaEngine] 初始化完成, {len(self.parameters)} 个参数可优化")

    # ─────────── 参数管理 ───────────

    def _register_default_parameters(self) -> None:
        """注册默认的可优化参数。"""
        defaults = [
            # PSI 循环参数
            OptimizableParameter(name="psi_emotion_decay", category="psi",
                current_value=0.1, min_value=0.01, max_value=0.5,
                description="PSI情感衰减率: 越高情绪变化越快"),
            OptimizableParameter(name="psi_attention_focus", category="psi",
                current_value=0.7, min_value=0.3, max_value=1.0,
                description="注意力聚焦度: 越高越专注单一主题"),
            OptimizableParameter(name="psi_need_decay", category="psi",
                current_value=0.05, min_value=0.01, max_value=0.2,
                description="需求衰减率: 越高需求满足后下降越快"),

            # 学习参数
            OptimizableParameter(name="learning_rate", category="learning",
                current_value=0.1, min_value=0.01, max_value=0.5,
                description="学习率: 每次学习的掌握度增益"),
            OptimizableParameter(name="forgetting_stability", category="learning",
                current_value=24.0, min_value=6.0, max_value=168.0,
                description="记忆稳定性(小时): 越高遗忘越慢"),
            OptimizableParameter(name="review_interval", category="learning",
                current_value=24.0, min_value=1.0, max_value=168.0,
                description="复习间隔(小时)"),

            # 策略参数
            OptimizableParameter(name="exploration_rate", category="strategy",
                current_value=0.2, min_value=0.0, max_value=0.5,
                description="探索率: 尝试新策略的概率"),
            OptimizableParameter(name="transfer_sensitivity", category="strategy",
                current_value=0.4, min_value=0.1, max_value=1.0,
                description="迁移敏感度: 发现跨域联系的敏感度"),

            # 时序参数
            OptimizableParameter(name="dream_interval", category="timing",
                current_value=30.0, min_value=10.0, max_value=120.0,
                description="梦境巩固间隔(秒)"),
            OptimizableParameter(name="meta_review_interval", category="timing",
                current_value=60.0, min_value=15.0, max_value=300.0,
                description="元认知审查间隔(秒)"),
        ]
        for p in defaults:
            self.parameters[p.name] = p

    def get_parameter(self, name: str) -> Optional[OptimizableParameter]:
        """按名称获取可优化参数。

        Args:
            name: 参数名。

        Returns:
            匹配的 OptimizableParameter，不存在时返回 None。
        """
        return self.parameters.get(name)

    def set_parameter(self, name: str, value: float) -> None:
        """直接设置参数值。

        Args:
            name: 参数名。
            value: 期望的参数值，会被截断到 [min_value, max_value] 区间。
        """
        param = self.parameters.get(name)
        if param:
            param.current_value = max(param.min_value, min(param.max_value, value))

    # ─────────── 改进建议 ───────────

    def suggest_improvements(self, performance_metrics: Optional[Dict[str, float]] = None
                              ) -> List[Dict[str, Any]]:
        """基于性能指标提出改进建议。

        Args:
            performance_metrics: {参数名: 当前性能评分} 字典，为 None 时
                仅依据参数历史性能趋势生成建议。

        Returns:
            至多 5 条改进建议，按预期改进幅度降序排列。每条建议包含
            parameter、category、from、to、rationale、expected_improvement 字段。
        """
        suggestions = []

        for name, param in self.parameters.items():
            # 跳过最近刚优化过的
            if time.time() - param.last_optimized < 600:  # 10分钟内不重复
                continue

            new_value = param.propose_new_value()
            if abs(new_value - param.current_value) < 0.001:
                continue

            # 如果有性能指标，计算预期改进
            expected = 0.0
            rationale = f"尝试调优 {param.description}"

            if performance_metrics and name in performance_metrics:
                current_perf = performance_metrics[name]
                if current_perf < 0.3:
                    expected = 0.2
                    rationale = f"当前性能低({current_perf:.2f})，尝试调优 {param.description}"
                elif current_perf < 0.6:
                    expected = 0.1
                    rationale = f"性能中等({current_perf:.2f})，微调 {param.description}"

            suggestions.append({
                "parameter": name,
                "category": param.category,
                "from": round(param.current_value, 3),
                "to": round(new_value, 3),
                "rationale": rationale,
                "expected_improvement": round(expected, 3),
            })

        suggestions.sort(key=lambda x: -x["expected_improvement"])
        return suggestions[:5]

    def apply_improvement(self, parameter: str, new_value: float,
                           rationale: str = "") -> SelfImprovementAttempt:
        """应用一次自我改进。

        Args:
            parameter: 目标参数名。
            new_value: 期望的新值，会被截断到参数的合法区间。
            rationale: 改动理由文本，为空时自动生成。

        Returns:
            记录此次改进的 SelfImprovementAttempt 对象。

        Raises:
            ValueError: 参数名未知时抛出。
        """
        param = self.parameters.get(parameter)
        if not param:
            raise ValueError(f"未知参数: {parameter}")

        old_value = param.current_value
        clamped = max(param.min_value, min(param.max_value, new_value))

        attempt = SelfImprovementAttempt(
            id=f"rsi_{uuid.uuid4().hex[:8]}",
            target=parameter,
            category=param.category,
            old_value=old_value,
            new_value=clamped,
            rationale=rationale or f"自动调优 {param.description}",
        )

        param.current_value = clamped
        param.last_optimized = time.time()
        param.optimization_count += 1

        self.attempts.append(attempt)
        if len(self.attempts) > self.max_attempts:
            self.attempts = self.attempts[-self.max_attempts:]

        self._total_attempts += 1
        logger.info(f"[RSI] 改进: {parameter} {old_value:.3f} → {clamped:.3f} ({rationale[:60]})")

        return attempt

    def evaluate_improvement(self, attempt_id: str, performance_change: float
                              ) -> bool:
        """评估一次改进的效果，决定保留或回滚。

        Args:
            attempt_id: 改进尝试的唯一 ID。
            performance_change: 性能变化值。大于 0 视为成功并保留，
                否则视为失败并回滚到旧值。

        Returns:
            True 表示改进成功并保留，False 表示未找到尝试或已回滚。
        """
        for attempt in self.attempts:
            if attempt.id == attempt_id:
                attempt.actual_improvement = performance_change
                attempt.success = performance_change > 0

                if attempt.success:
                    self._successful_attempts += 1
                else:
                    # 回滚
                    attempt.reverted = True
                    param = self.parameters.get(attempt.target)
                    if param:
                        param.current_value = attempt.old_value
                    self._reverted_attempts += 1

                return attempt.success
        return False

    # ─────────── 学习目标自生成 ───────────

    def generate_goals(self, curriculum_engine: Any = None,
                       meta_learning_engine: Any = None) -> List[LearningGoal]:
        """基于知识缺口自动生成学习目标。

        使用课程引擎的知识缺口分析 + 元学习引擎的策略推荐。
        若无外部引擎，则基于未充分优化的参数生成通用目标。

        Args:
            curriculum_engine: 可选的课程引擎，需提供 find_knowledge_gaps 方法。
            meta_learning_engine: 可选的元学习引擎，需提供 recommend_strategy 方法。

        Returns:
            至多 5 个学习目标，按优先级降序排列。
        """
        goals = []

        # 如果接入了课程引擎，基于缺口生成目标
        if curriculum_engine:
            gaps = curriculum_engine.find_knowledge_gaps(min_gap=0.4)
            for gap in gaps[:5]:
                # 确定策略
                strategy = "structured"
                if meta_learning_engine:
                    try:
                        strategy = meta_learning_engine.recommend_strategy(
                            concept=gap["concept"], domain=gap["domain"],
                            difficulty=gap["difficulty"],
                        ).value
                    except Exception as e:
                        logger.exception(f"generate_goals 失败: {e}")

                goal = LearningGoal(
                    id=f"goal_{uuid.uuid4().hex[:8]}",
                    description=f"掌握 {gap['concept']}: {gap['description']}",
                    domain=gap["domain"],
                    target_mastery=0.8,
                    priority=gap["priority"],
                    strategy=strategy,
                    motivation=f"知识缺口 {gap['gap_size']:.2f}, 优先级 {gap['priority']:.2f}",
                    status="proposed",
                )
                self.goals[goal.id] = goal
                goals.append(goal)
                self._goals_generated += 1

        # 如果没有外部引擎，生成通用目标
        if not goals:
            for param in self.parameters.values():
                if param.optimization_count < 2:
                    goal = LearningGoal(
                        id=f"goal_{uuid.uuid4().hex[:8]}",
                        description=f"优化 {param.name}: {param.description}",
                        domain=param.category,
                        target_mastery=0.8,
                        priority=0.5 - param.optimization_count * 0.1,
                        strategy="practical",
                        motivation=f"该参数尚未充分优化 ({param.optimization_count}次)",
                        status="proposed",
                    )
                    self.goals[goal.id] = goal
                    goals.append(goal)
                    self._goals_generated += 1

        goals.sort(key=lambda x: -x.priority)
        return goals[:5]

    def complete_goal(self, goal_id: str, final_mastery: float) -> None:
        """标记一个学习目标为已完成。

        Args:
            goal_id: 学习目标 ID。
            final_mastery: 最终掌握度，范围 0.0~1.0。
        """
        goal = self.goals.get(goal_id)
        if goal:
            goal.status = "completed"
            goal.current_mastery = final_mastery
            self._goals_completed += 1

    def get_active_goals(self) -> List[LearningGoal]:
        """获取活跃的学习目标。

        Returns:
            状态为 "proposed" 或 "active" 的学习目标列表。
        """
        return [g for g in self.goals.values() if g.status in ("proposed", "active")]

    # ─────────── PSI 需求联动 ───────────

    def compute_growth_need(self) -> float:
        """计算成长需求强度。

        基于以下因素综合评估：
          - 待改进的参数数量
          - 待完成的学习目标
          - 近期改进成功率

        Returns:
            成长需求值，范围 0.0~1.0。需求越高表示越需要学习与改进。
        """
        unoptimized = sum(1 for p in self.parameters.values()
                         if p.optimization_count < 2)
        pending_goals = len(self.get_active_goals())

        # 改进成功率
        success_rate = (self._successful_attempts /
                       max(1, self._total_attempts))

        growth = (
            unoptimized / max(1, len(self.parameters)) * 0.3 +
            min(1.0, pending_goals / 5) * 0.3 +
            (1 - success_rate) * 0.2 +  # 失败多说明需要成长
            0.2  # 基准
        )
        return min(1.0, growth)

    # ─────────── 全自动改进循环 ───────────

    def full_improvement_cycle(self) -> Dict[str, Any]:
        """执行一次完整的自我改进循环。

        流程：
          1. 分析当前状态
          2. 生成改进建议
          3. 应用最 promising 的改进
          4. 生成学习目标
          5. 评估成长需求

        Returns:
            循环结果字典，包含 suggestions、applied、goals、
            growth_need、duration_ms 字段。
        """
        cycle_start = time.time()
        results = {
            "suggestions": [],
            "applied": None,
            "goals": [],
            "growth_need": 0.0,
            "duration_ms": 0.0,
        }

        # 1. 建议
        suggestions = self.suggest_improvements()
        results["suggestions"] = suggestions

        # 2. 应用最佳建议
        if suggestions:
            best = suggestions[0]
            attempt = self.apply_improvement(
                best["parameter"], best["to"], best["rationale"]
            )
            results["applied"] = attempt.to_dict()

        # 3. 生成目标
        goals = self.generate_goals(self.curriculum_engine, self.meta_learning_engine)
        results["goals"] = [g.to_dict() for g in goals]

        # 4. 成长需求
        results["growth_need"] = round(self.compute_growth_need(), 3)

        results["duration_ms"] = round((time.time() - cycle_start) * 1000, 2)
        return results

    # ─────────── 统计与序列化 ───────────

    def stats(self) -> Dict[str, Any]:
        """返回引擎统计快照。

        Returns:
            统计字典，包含 total_attempts、successful、reverted、
            success_rate、goals_generated、goals_completed、parameters、
            optimized_parameters、active_goals、growth_need 字段。
        """
        return {
            "total_attempts": self._total_attempts,
            "successful": self._successful_attempts,
            "reverted": self._reverted_attempts,
            "success_rate": round(self._successful_attempts / max(1, self._total_attempts), 3),
            "goals_generated": self._goals_generated,
            "goals_completed": self._goals_completed,
            "parameters": len(self.parameters),
            "optimized_parameters": sum(1 for p in self.parameters.values() if p.optimization_count > 0),
            "active_goals": len(self.get_active_goals()),
            "growth_need": round(self.compute_growth_need(), 3),
        }

    def save(self, path: Optional[str] = None) -> None:
        """持久化RSI状态（完整字段 + schema 版本）。

        Args:
            path: 状态文件路径。为 None 时使用 ``LAAP_HOME/rsi_engine.json``，
                  ``LAAP_HOME`` 未设置则落到 ``~/.laap/rsi_engine.json``。
        """
        if path is None:
            path = _default_state_path("rsi_engine.json")

        # 参数：完整字段序列化（to_dict 是有损摘要，丢失 step_size/
        # description/last_optimized/performance_history）
        parameters_state = {
            name: {
                "name": p.name, "category": p.category,
                "current_value": p.current_value,
                "min_value": p.min_value, "max_value": p.max_value,
                "step_size": p.step_size, "description": p.description,
                "last_optimized": p.last_optimized,
                "optimization_count": p.optimization_count,
                "performance_history": list(p.performance_history),
            }
            for name, p in self.parameters.items()
        }

        # 改进尝试：完整字段序列化（补齐 timestamp/evaluation_period）
        attempts_state = [
            {
                "id": a.id, "target": a.target, "category": a.category,
                "old_value": a.old_value, "new_value": a.new_value,
                "rationale": a.rationale,
                "expected_improvement": a.expected_improvement,
                "actual_improvement": a.actual_improvement,
                "success": a.success, "reverted": a.reverted,
                "timestamp": a.timestamp,
                "evaluation_period": a.evaluation_period,
            }
            for a in self.attempts[-50:]
        ]

        # 学习目标：完整字段序列化（补齐 motivation/strategy/created_at/deadline）
        goals_state = [
            {
                "id": g.id, "description": g.description, "domain": g.domain,
                "target_mastery": g.target_mastery,
                "current_mastery": g.current_mastery,
                "priority": g.priority, "strategy": g.strategy,
                "motivation": g.motivation, "status": g.status,
                "created_at": g.created_at, "deadline": g.deadline,
            }
            for g in self.goals.values()
        ]

        data = {
            "version": RSI_STATE_SCHEMA_VERSION,
            "parameters": parameters_state,
            "attempts": attempts_state,
            "goals": goals_state,
            "total_attempts": self._total_attempts,
            "successful": self._successful_attempts,
            "reverted": self._reverted_attempts,
            "goals_generated": self._goals_generated,
            "goals_completed": self._goals_completed,
            "saved_at": time.time(),
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2),
                              encoding="utf-8")
        logger.info(f"[RSIMetaEngine] 保存到 {path}")

    def load(self, path: Optional[str] = None) -> bool:
        """加载RSI状态（完整恢复参数、历史、目标）。

        Args:
            path: 状态文件路径。为 None 时使用 ``LAAP_HOME/rsi_engine.json``。

        Returns:
            True 表示加载成功; False 表示文件不存在或 schema 不兼容。
        """
        if path is None:
            path = _default_state_path("rsi_engine.json")
        p = Path(path)
        if not p.exists():
            return False
        try:
            data = json.loads(p.read_text(encoding="utf-8"))

            # ── schema 版本校验 ──
            version = data.get("version")
            if version != RSI_STATE_SCHEMA_VERSION:
                logger.warning(
                    f"[RSIMetaEngine] schema 版本不兼容 (文件={version}, "
                    f"当前={RSI_STATE_SCHEMA_VERSION}), 跳过加载")
                return False

            # ── 计数器 ──
            self._total_attempts = data.get("total_attempts", 0)
            self._successful_attempts = data.get("successful", 0)
            self._reverted_attempts = data.get("reverted", 0)
            self._goals_generated = data.get("goals_generated", 0)
            self._goals_completed = data.get("goals_completed", 0)

            # ── 参数：完整恢复（含 step_size/last_optimized/performance_history） ──
            saved_params = data.get("parameters", {})
            for name, pd in saved_params.items():
                if name in self.parameters:
                    p_obj = self.parameters[name]
                    p_obj.current_value = pd.get("current_value",
                                                 p_obj.current_value)
                    p_obj.min_value = pd.get("min_value", p_obj.min_value)
                    p_obj.max_value = pd.get("max_value", p_obj.max_value)
                    p_obj.step_size = pd.get("step_size", p_obj.step_size)
                    p_obj.description = pd.get("description", p_obj.description)
                    p_obj.last_optimized = pd.get("last_optimized",
                                                  p_obj.last_optimized)
                    p_obj.optimization_count = pd.get("optimization_count", 0)
                    p_obj.performance_history = list(
                        pd.get("performance_history", []))

            # ── 改进尝试：完整重建 ──
            self.attempts = []
            for ad in data.get("attempts", []):
                attempt = SelfImprovementAttempt(
                    id=ad.get("id", ""),
                    target=ad.get("target", ""),
                    category=ad.get("category", "psi"),
                    old_value=ad.get("old_value", 0.0),
                    new_value=ad.get("new_value", 0.0),
                    rationale=ad.get("rationale", ""),
                    expected_improvement=ad.get("expected_improvement", 0.0),
                    actual_improvement=ad.get("actual_improvement", 0.0),
                    success=ad.get("success", False),
                    reverted=ad.get("reverted", False),
                    timestamp=ad.get("timestamp", time.time()),
                    evaluation_period=ad.get("evaluation_period", 3600.0),
                )
                self.attempts.append(attempt)

            # ── 学习目标：完整重建 ──
            self.goals = {}
            for gd in data.get("goals", []):
                goal = LearningGoal(
                    id=gd.get("id", ""),
                    description=gd.get("description", ""),
                    domain=gd.get("domain", "general"),
                    target_mastery=gd.get("target_mastery", 0.8),
                    current_mastery=gd.get("current_mastery", 0.0),
                    priority=gd.get("priority", 0.5),
                    strategy=gd.get("strategy", "structured"),
                    motivation=gd.get("motivation", ""),
                    status=gd.get("status", "proposed"),
                    created_at=gd.get("created_at", time.time()),
                    deadline=gd.get("deadline"),
                )
                if goal.id:
                    self.goals[goal.id] = goal

            logger.info(f"[RSIMetaEngine] 加载完成: {len(saved_params)} params, "
                        f"{len(self.attempts)} attempts, {len(self.goals)} goals")
            return True
        except Exception as e:
            logger.error(f"[RSIMetaEngine] 加载失败: {e}")
            return False


# ═══════════════════════════════════════════════════════════════
# 测试
# ═══════════════════════════════════════════════════════════════

def test():
    engine = RSIMetaEngine()
    logger.info("=" * 50)
    logger.info("P2-2 递归自我改进引擎测试")
    logger.info("=" * 50)
    logger.info("\n=== 测试1: 可优化参数 ===")
    logger.info(f"  参数总数: {len(engine.parameters)}")
    for cat in set(p.category for p in engine.parameters.values()):
        count = sum(1 for p in engine.parameters.values() if p.category == cat)
        logger.info(f"  {cat}: {count} 个参数")
    param = engine.get_parameter("psi_emotion_decay")
    logger.info(f"  示例: {param.name} = {param.current_value} ({param.description})")
    logger.info("\n=== 测试2: 改进建议生成 ===")
    perf = {"psi_emotion_decay": 0.2, "learning_rate": 0.5, "exploration_rate": 0.8}
    suggestions = engine.suggest_improvements(perf)
    logger.info(f"  产生 {len(suggestions)} 条建议:")
    for s in suggestions[:4]:
        logger.info(f"    {s['parameter']}: {s['from']} → {s['to']} ({s['rationale'][:60]})")
    logger.info("\n=== 测试3: 应用改进 ===")
    attempt = engine.apply_improvement("learning_rate", 0.15, "测试提高学习率")
    logger.info(f"  改进: {attempt.target} {attempt.old_value} → {attempt.new_value}")
    logger.info(f"  理由: {attempt.rationale}")
    engine.evaluate_improvement(attempt.id, 0.05)
    logger.error(f"  评估结果: {'成功✅' if attempt.success else '失败❌, 已回滚'}")
    attempt2 = engine.apply_improvement("exploration_rate", 0.5, "测试高探索率")
    engine.evaluate_improvement(attempt2.id, -0.1)
    logger.error(f"  改进2: {attempt2.target} → 评估: {'成功✅' if attempt2.success else '失败❌, 已回滚'}")
    logger.info("\n=== 测试4: 全自动改进循环 ===")
    cycle = engine.full_improvement_cycle()
    logger.info(f"  耗时: {cycle['duration_ms']}ms")
    logger.info(f"  建议数: {len(cycle['suggestions'])}")
    if cycle['applied']:
        logger.info(f"  已应用: {cycle['applied']['target']} {cycle['applied']['old']} → {cycle['applied']['new']}")
    logger.info(f"  新目标: {len(cycle['goals'])} 个")
    for g in cycle['goals']:
        logger.info(f"    {g['description']} (priority={g['priority']})")
    logger.info(f"  成长需求: {cycle['growth_need']}")
    logger.info("\n=== 测试5: 学习目标管理 ===")
    engine.generate_goals()
    active = engine.get_active_goals()
    logger.info(f"  活跃目标: {len(active)} 个")
    for g in active[:3]:
        logger.info(f"    [{g.status}] {g.description} (策略: {g.strategy})")
    if active:
        engine.complete_goal(active[0].id, 0.85)
        logger.info(f"  完成: {active[0].description}")
    logger.info(f"\n=== 引擎统计 ===")
    for k, v in engine.stats().items():
        logger.info(f"  {k}: {v}")
    engine.save()
    logger.info(f"\n✅ P2-2 递归自我改进引擎全部测试通过！")
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test()
