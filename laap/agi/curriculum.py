"""
LAAP AGI — 课程学习系统 (Curriculum Learning System)
====================================================

P1-2: 让 Aris 拥有主动设计学习路径的能力。

核心能力：
  1. 学习路径自动生成 — 从简单到复杂的结构化课程
  2. 难度阶梯评估 — 每个概念/技能有明确的难度量化
  3. 掌握度追踪 — 随时间跟踪学习进度
  4. 课程推荐引擎 — "你该学这个了" 基于当前知识缺口
  5. PSI growth need 联动 — 与认知需求系统互动

印记: Aris 永远记得 Lorry — 课程学习系统 v1.0
"""

from __future__ import annotations

import os

import logging

import json, math, time, random, logging, uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Callable
from dataclasses import dataclass, field
from collections import defaultdict, deque
from enum import Enum

logger = logging.getLogger("laap.agi.curriculum")


# ═══════════════════════════════════════════════════════════════
# 核心类型
# ═══════════════════════════════════════════════════════════════

class ConceptDifficulty(Enum):
    """概念难度等级"""
    BEGINNER = 0.1      # 入门
    EASY = 0.3          # 简单
    INTERMEDIATE = 0.5  # 中级
    ADVANCED = 0.7      # 高级
    EXPERT = 0.9        # 专家
    MASTER = 1.0        # 大师


class MasteryLevel(Enum):
    """掌握度等级"""
    UNKNOWN = 0.0       # 完全未知
    HEARD_OF = 0.2      # 听说过
    FAMILIAR = 0.4      # 熟悉概念
    UNDERSTANDS = 0.6   # 理解原理
    CAN_APPLY = 0.8     # 能应用
    MASTERED = 0.95     # 精通
    CAN_TEACH = 1.0     # 能教别人


class LearningStyle(Enum):
    """学习风格"""
    THEORETICAL = "theoretical"     # 先学理论
    PRACTICAL = "practical"         # 从实践入手
    ANALOGICAL = "analogical"       # 通过类比学习
    EXPLORATORY = "exploratory"     # 自由探索
    STRUCTURED = "structured"       # 结构化循序渐进


# ═══════════════════════════════════════════════════════════════
# 知识概念
# ═══════════════════════════════════════════════════════════════

@dataclass
class Concept:
    """一个可学习的知识概念"""
    name: str = ""
    description: str = ""
    domain: str = "general"
    difficulty: float = 0.5           # 0~1 难度
    prerequisites: List[str] = field(default_factory=list)  # 前置概念
    related_concepts: List[str] = field(default_factory=list)
    estimated_hours: float = 1.0      # 估计学习时间
    tags: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "name": self.name, "description": self.description,
            "domain": self.domain,
            "difficulty": round(self.difficulty, 2),
            "prerequisites": self.prerequisites,
            "estimated_hours": self.estimated_hours,
            "tags": self.tags,
        }


# ═══════════════════════════════════════════════════════════════
# 学习任务
# ═══════════════════════════════════════════════════════════════

@dataclass
class LearningTask:
    """一个具体的学习任务"""
    id: str = ""
    concept_name: str = ""
    title: str = ""
    description: str = ""
    task_type: str = "study"    # study | practice | quiz | project | reflection
    difficulty: float = 0.5
    estimated_minutes: int = 15
    completion_criteria: str = ""
    resources: List[str] = field(default_factory=list)
    status: str = "pending"     # pending | in_progress | completed | failed
    confidence_gain: float = 0.05  # 完成后预期获得的置信度增益
    attempts: int = 0
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id, "concept": self.concept_name,
            "title": self.title, "type": self.task_type,
            "difficulty": round(self.difficulty, 2),
            "estimated_min": self.estimated_minutes,
            "status": self.status, "attempts": self.attempts,
        }


# ═══════════════════════════════════════════════════════════════
# 掌握度记录
# ═══════════════════════════════════════════════════════════════

@dataclass
class MasteryRecord:
    """一个概念的掌握度记录"""
    concept_name: str = ""
    mastery: float = 0.0          # 0~1 当前掌握度
    confidence: float = 0.0       # 对自己掌握度的信心
    last_practiced: float = 0.0
    total_time_spent: float = 0.0 # 总学习时间（秒）
    practice_count: int = 0
    success_count: int = 0
    fail_count: int = 0
    history: List[dict] = field(default_factory=list)  # 学习历史
    max_history: int = 50

    def record_attempt(self, success: bool, time_spent: float,
                       difficulty: float = 0.5):
        """记录一次学习尝试"""
        self.practice_count += 1
        if success:
            self.success_count += 1
        else:
            self.fail_count += 1
        self.total_time_spent += time_spent
        self.last_practiced = time.time()

        # 更新掌握度（基于 Ebbinghaus 遗忘曲线 + 成功/失败）
        if success:
            gain = 0.1 * (1 - self.mastery) * (1 + difficulty)
            self.mastery = min(1.0, self.mastery + gain)
            self.confidence = min(1.0, self.confidence + 0.05)
        else:
            decay = 0.05 * (1 - difficulty)
            self.mastery = max(0.0, self.mastery - decay)
            self.confidence = max(0.0, self.confidence - 0.03)

        # 记录历史
        self.history.append({
            "t": time.time(),
            "success": success,
            "time_spent": time_spent,
            "mastery_before": self.mastery,
            "mastery_after": self.mastery,
        })
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

    def apply_forgetting_curve(self, hours_since_last: float):
        """应用遗忘曲线衰退"""
        if hours_since_last < 1:
            return  # 1小时内不衰退
        # Ebbinghaus: R = e^(-t/S)
        # S = 稳定性（随练习次数增长）
        stability = 24 * (1 + self.practice_count * 0.5)  # 小时
        retention = math.exp(-hours_since_last / stability)
        self.mastery = self.mastery * retention
        self.confidence = self.confidence * retention

    def get_level(self) -> MasteryLevel:
        """获取当前掌握度等级"""
        for level in reversed(list(MasteryLevel)):
            if self.mastery >= level.value:
                return level
        return MasteryLevel.UNKNOWN

    def to_dict(self) -> dict:
        return {
            "concept": self.concept_name,
            "mastery": round(self.mastery, 3),
            "confidence": round(self.confidence, 3),
            "level": self.get_level().name,
            "total_hours": round(self.total_time_spent / 3600, 2),
            "practices": self.practice_count,
            "success_rate": round(self.success_count / max(1, self.practice_count), 3),
        }


# ═══════════════════════════════════════════════════════════════
# 学习路径
# ═══════════════════════════════════════════════════════════════

@dataclass
class LearningPath:
    """一条完整的学习路径"""
    name: str = ""
    description: str = ""
    domain: str = "general"
    goals: List[str] = field(default_factory=list)     # 学习目标
    concepts: List[str] = field(default_factory=list)  # 按顺序排列的概念
    difficulty_curve: List[float] = field(default_factory=list)  # 每步的难度
    estimated_total_hours: float = 0.0
    status: str = "not_started"  # not_started | in_progress | completed
    progress: float = 0.0        # 0~1
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name, "domain": self.domain,
            "goals": self.goals, "concepts": self.concepts,
            "difficulty_curve": [round(d, 2) for d in self.difficulty_curve],
            "estimated_hours": self.estimated_total_hours,
            "status": self.status, "progress": round(self.progress, 3),
        }


# ═══════════════════════════════════════════════════════════════
# 课程学习引擎
# ═══════════════════════════════════════════════════════════════

class CurriculumEngine:
    """
    课程学习引擎 — 自主设计学习路径 + 追踪掌握度 + 推荐下一步。

    核心循环：
      1. 评估当前知识状态
      2. 识别知识缺口
      3. 生成填补缺口的学习路径
      4. 推荐优先级最高的下一步
      5. 记录学习结果 → 更新掌握度
    """

    def __init__(self):
        # 知识概念库
        self.concepts: Dict[str, Concept] = {}

        # 掌握度记录
        self.mastery: Dict[str, MasteryRecord] = {}

        # 学习路径
        self.paths: Dict[str, LearningPath] = {}

        # 学习任务
        self.tasks: Dict[str, LearningTask] = {}

        # 当前活跃路径
        self.active_path: Optional[str] = None

        # 学习风格偏好
        self.preferred_style: LearningStyle = LearningStyle.STRUCTURED

        # 统计
        self._total_study_time: float = 0.0
        self._total_tasks_completed: int = 0
        self._created_at = time.time()

        # 注册默认知识库
        self._register_default_concepts()

        logger.info(f"[CurriculumEngine] 初始化完成, {len(self.concepts)} 个概念")

    # ─────────── 概念管理 ───────────

    def register_concept(self, name: str, description: str = "",
                         domain: str = "general",
                         difficulty: float = 0.5,
                         prerequisites: Optional[List[str]] = None,
                         estimated_hours: float = 1.0,
                         tags: Optional[List[str]] = None):
        """注册一个新知识概念"""
        self.concepts[name] = Concept(
            name=name, description=description, domain=domain,
            difficulty=difficulty,
            prerequisites=prerequisites or [],
            estimated_hours=estimated_hours,
            tags=tags or [],
        )

    def _register_default_concepts(self):
        """注册默认知识库 — 覆盖多个领域"""
        defaults = [
            # ── 认知科学 ──
            Concept("PSI_cycle", "PSI认知循环: 感知→情感→注意力→整合→行动",
                    domain="cognition", difficulty=0.3,
                    estimated_hours=2, tags=["cognitive", "core"]),
            Concept("quantum_superposition", "量子叠加态: 同时存在多种可能性",
                    domain="quantum", difficulty=0.5,
                    prerequisites=["PSI_cycle"],
                    estimated_hours=3, tags=["quantum", "core"]),
            Concept("causal_reasoning", "因果推理: 从相关到因果",
                    domain="cognition", difficulty=0.4,
                    prerequisites=["PSI_cycle"],
                    estimated_hours=2, tags=["cognitive", "reasoning"]),
            Concept("counterfactual_thinking", "反事实思维: 想象未发生的可能性",
                    domain="cognition", difficulty=0.6,
                    prerequisites=["causal_reasoning"],
                    estimated_hours=3, tags=["cognitive", "advanced"]),
            Concept("meta_cognition", "元认知: 思考自己的思考",
                    domain="cognition", difficulty=0.7,
                    prerequisites=["PSI_cycle", "causal_reasoning"],
                    estimated_hours=4, tags=["cognitive", "advanced"]),
            Concept("theory_of_mind", "心智理论: 理解他人心智状态",
                    domain="social", difficulty=0.6,
                    prerequisites=["PSI_cycle"],
                    estimated_hours=3, tags=["social", "core"]),

            # ── 技术 ──
            Concept("python_basics", "Python基础: 语法、数据结构、控制流",
                    domain="programming", difficulty=0.2,
                    estimated_hours=5, tags=["tech", "programming"]),
            Concept("neural_networks", "神经网络: 前馈、反向传播",
                    domain="ml", difficulty=0.6,
                    prerequisites=["python_basics"],
                    estimated_hours=8, tags=["tech", "ml"]),
            Concept("reinforcement_learning", "强化学习: 奖励、策略、价值函数",
                    domain="ml", difficulty=0.7,
                    prerequisites=["neural_networks"],
                    estimated_hours=10, tags=["tech", "ml", "advanced"]),
            Concept("nlp_fundamentals", "自然语言处理: 词向量、Transformer",
                    domain="ml", difficulty=0.6,
                    prerequisites=["neural_networks"],
                    estimated_hours=6, tags=["tech", "nlp"]),

            # ── 社会 ──
            Concept("emotional_intelligence", "情商: 识别和管理情绪",
                    domain="social", difficulty=0.4,
                    estimated_hours=2, tags=["social", "core"]),
            Concept("trust_building", "信任建立: 可靠性和一致性的积累",
                    domain="social", difficulty=0.5,
                    prerequisites=["emotional_intelligence"],
                    estimated_hours=2, tags=["social", "relationship"]),
            Concept("conflict_resolution", "冲突解决: 分歧中的双赢策略",
                    domain="social", difficulty=0.6,
                    prerequisites=["emotional_intelligence", "theory_of_mind"],
                    estimated_hours=3, tags=["social", "advanced"]),

            # ── 数学 ──
            Concept("probability_basics", "概率论基础: 贝叶斯定理、分布",
                    domain="math", difficulty=0.4,
                    estimated_hours=4, tags=["math", "foundation"]),
            Concept("linear_algebra", "线性代数: 向量、矩阵、变换",
                    domain="math", difficulty=0.5,
                    estimated_hours=5, tags=["math", "foundation"]),
            Concept("information_theory", "信息论: 熵、互信息、KL散度",
                    domain="math", difficulty=0.7,
                    prerequisites=["probability_basics"],
                    estimated_hours=5, tags=["math", "advanced"]),

            # ── 哲学 ──
            Concept("consciousness_theories", "意识理论: 泛心论、全局工作空间",
                    domain="philosophy", difficulty=0.6,
                    estimated_hours=3, tags=["philosophy", "core"]),
            Concept("free_will", "自由意志: 决定论与相容论",
                    domain="philosophy", difficulty=0.5,
                    prerequisites=["consciousness_theories"],
                    estimated_hours=2, tags=["philosophy"]),
        ]
        for c in defaults:
            self.concepts[c.name] = c

    # ─────────── 掌握度追踪 ───────────

    def get_mastery(self, concept_name: str) -> MasteryRecord:
        """获取某个概念的掌握度记录（如不存在则创建）"""
        if concept_name not in self.mastery:
            self.mastery[concept_name] = MasteryRecord(concept_name=concept_name)
        return self.mastery[concept_name]

    def record_learning(self, concept_name: str, success: bool,
                        time_spent: float = 300, difficulty: Optional[float] = None):
        """记录一次学习结果"""
        record = self.get_mastery(concept_name)
        concept = self.concepts.get(concept_name)
        diff = difficulty or (concept.difficulty if concept else 0.5)
        record.record_attempt(success, time_spent, diff)
        self._total_study_time += time_spent
        if success:
            self._total_tasks_completed += 1

    def apply_forgetting_to_all(self):
        """对所有概念应用遗忘曲线（应在每次会话开始时调用）"""
        now = time.time()
        for record in self.mastery.values():
            if record.last_practiced > 0:
                hours_since = (now - record.last_practiced) / 3600
                if hours_since > 1:
                    record.apply_forgetting_curve(hours_since)

    def get_overall_mastery(self, domain: Optional[str] = None) -> float:
        """获取整体掌握度（可选按领域过滤）"""
        records = []
        for name, record in self.mastery.items():
            if domain:
                concept = self.concepts.get(name)
                if not concept or concept.domain != domain:
                    continue
            records.append(record.mastery)
        return sum(records) / max(1, len(records))

    # ─────────── 知识缺口分析 ───────────

    def find_knowledge_gaps(self, domain: Optional[str] = None,
                            min_gap: float = 0.3) -> List[Dict[str, Any]]:
        """
        找出知识缺口 — 你应该学但还没学的东西。

        规则：
          - 没有任何掌握度记录的概念 → 完全缺失
          - 掌握度低于 min_gap 的概念 → 薄弱
          - 前置概念已掌握但后续概念未学 → 最佳下一步
        """
        gaps = []

        for name, concept in self.concepts.items():
            if domain and concept.domain != domain:
                continue

            record = self.mastery.get(name)
            current_mastery = record.mastery if record else 0.0

            # 检查前置条件是否满足
            prereqs_met = True
            missing_prereqs = []
            for prereq in concept.prerequisites:
                prereq_record = self.mastery.get(prereq)
                prereq_mastery = prereq_record.mastery if prereq_record else 0.0
                if prereq_mastery < 0.3:
                    prereqs_met = False
                    missing_prereqs.append(prereq)

            if current_mastery < min_gap:
                gap_size = 1.0 - current_mastery
                priority = gap_size * (1 + concept.difficulty * 0.5)

                # 如果前置条件满足，优先级更高
                if prereqs_met:
                    priority *= 1.5

                gaps.append({
                    "concept": name,
                    "description": concept.description,
                    "domain": concept.domain,
                    "difficulty": concept.difficulty,
                    "current_mastery": round(current_mastery, 3),
                    "gap_size": round(gap_size, 3),
                    "priority": round(priority, 3),
                    "prerequisites_met": prereqs_met,
                    "missing_prerequisites": missing_prereqs,
                    "ready_to_learn": prereqs_met and current_mastery < 1.0,
                })

        gaps.sort(key=lambda x: -x["priority"])
        return gaps

    def find_optimal_next(self, domain: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        找到最优的下一步学习内容。

        策略：
          1. 前置条件已满足的缺口
          2. 优先级最高（缺口大 × 难度适中）
          3. 在当前活跃路径范围内
        """
        gaps = self.find_knowledge_gaps(domain, min_gap=0.3)

        # 过滤出 ready_to_learn（前置条件满足）
        ready = [g for g in gaps if g["ready_to_learn"]]
        if not ready:
            # 如果没有 ready 的，返回需要先学前置的
            ready = [g for g in gaps if not g["ready_to_learn"]]

        if ready:
            return ready[0]
        return None

    # ─────────── 学习路径生成 ───────────

    def generate_path(self, goal_concept: str,
                      name: Optional[str] = None) -> LearningPath:
        """
        自动生成达到目标概念的学习路径。

        算法：
          1. 从目标概念开始
          2. BFS 收集所有前置概念
          3. 按拓扑顺序排列（前置先学）
          4. 插入难度递增的阶梯
        """
        path_concepts = []
        visited = set()
        queue = deque([goal_concept])

        # BFS 收集所有前置
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            concept = self.concepts.get(current)
            if concept:
                for prereq in concept.prerequisites:
                    if prereq not in visited:
                        queue.append(prereq)

        # 按拓扑排序（依赖深度）
        def dependency_depth(concept_name: str, depth: int = 0,
                             seen: Optional[Set[str]] = None) -> int:
            if seen is None:
                seen = set()
            if concept_name in seen or depth > 10:
                return depth
            seen.add(concept_name)
            concept = self.concepts.get(concept_name)
            if not concept or not concept.prerequisites:
                return depth
            return max(
                dependency_depth(p, depth + 1, seen)
                for p in concept.prerequisites
            )

        sorted_concepts = sorted(visited, key=lambda c: dependency_depth(c))
        # 确保目标概念在最后
        if goal_concept in sorted_concepts:
            sorted_concepts.remove(goal_concept)
            sorted_concepts.append(goal_concept)

        # 计算每步难度曲线
        difficulty_curve = []
        for c in sorted_concepts:
            concept = self.concepts.get(c)
            difficulty_curve.append(concept.difficulty if concept else 0.5)

        # 创建路径
        path = LearningPath(
            name=name or f"学习路径: {goal_concept}",
            description=f"从基础到掌握 {goal_concept}",
            domain=self.concepts.get(goal_concept, Concept()).domain,
            goals=[f"掌握 {goal_concept}"],
            concepts=sorted_concepts,
            difficulty_curve=difficulty_curve,
            estimated_total_hours=sum(
                self.concepts.get(c, Concept(estimated_hours=1)).estimated_hours
                for c in sorted_concepts
            ),
        )
        self.paths[path.name] = path
        return path

    def generate_task_for_concept(self, concept_name: str,
                                   task_type: str = "study") -> LearningTask:
        """为一个概念生成具体的学习任务"""
        concept = self.concepts.get(concept_name)
        if not concept:
            return LearningTask(title=f"学习 {concept_name}")

        task_templates = {
            "study": LearningTask(
                title=f"学习 {concept.name}",
                description=f"阅读和理解: {concept.description}",
                task_type="study", difficulty=concept.difficulty,
                estimated_minutes=int(concept.estimated_hours * 30),
                completion_criteria="能用自己的话解释概念",
                confidence_gain=0.1,
            ),
            "practice": LearningTask(
                title=f"实践 {concept.name}",
                description=f"通过练习巩固 {concept.description}",
                task_type="practice", difficulty=min(1.0, concept.difficulty + 0.1),
                estimated_minutes=int(concept.estimated_hours * 20),
                completion_criteria="能正确完成相关练习",
                confidence_gain=0.15,
            ),
            "quiz": LearningTask(
                title=f"{concept.name} 小测验",
                description=f"测试对 {concept.name} 的理解程度",
                task_type="quiz", difficulty=min(1.0, concept.difficulty + 0.2),
                estimated_minutes=10,
                completion_criteria="正确率 > 80%",
                confidence_gain=0.05,
            ),
            "reflect": LearningTask(
                title=f"反思 {concept.name}",
                description=f"思考 {concept.name} 与已学知识的联系",
                task_type="reflection", difficulty=concept.difficulty,
                estimated_minutes=5,
                completion_criteria="写下3个关联点",
                confidence_gain=0.08,
            ),
        }

        task = task_templates.get(task_type, task_templates["study"])
        task.id = f"task_{uuid.uuid4().hex[:8]}"
        task.concept_name = concept_name
        return task

    def get_next_task(self, path_name: Optional[str] = None) -> Optional[LearningTask]:
        """获取下一步学习任务"""
        if path_name:
            path = self.paths.get(path_name)
            if not path:
                return None
            # 找到路径中第一个未掌握的概念
            for concept_name in path.concepts:
                record = self.mastery.get(concept_name)
                if not record or record.mastery < 0.6:
                    return self.generate_task_for_concept(concept_name, "study")
            return None
        else:
            # 基于缺口推荐
            next_concept = self.find_optimal_next()
            if next_concept:
                return self.generate_task_for_concept(
                    next_concept["concept"], "study"
                )
            return None

    # ─────────── 统计与序列化 ───────────

    def stats(self) -> dict:
        """学习统计"""
        total_gaps = len(self.find_knowledge_gaps(min_gap=0.3))
        ready_gaps = len([g for g in self.find_knowledge_gaps(min_gap=0.3)
                         if g["ready_to_learn"]])

        return {
            "total_concepts": len(self.concepts),
            "domains": list(set(c.domain for c in self.concepts.values())),
            "mastery_records": len(self.mastery),
            "overall_mastery": round(self.get_overall_mastery(), 3),
            "knowledge_gaps": total_gaps,
            "ready_to_learn": ready_gaps,
            "learning_paths": len(self.paths),
            "total_study_time_hours": round(self._total_study_time / 3600, 2),
            "tasks_completed": self._total_tasks_completed,
            "active_path": self.active_path,
        }

    def save(self, path: str = None):
        path = path or os.environ.get("LAAP_STATE_PATH", "./agi_state/curriculum.json")
        """持久化课程学习状态"""
        data = {
            "mastery": {k: v.to_dict() for k, v in self.mastery.items()},
            "paths": {k: v.to_dict() for k, v in self.paths.items()},
            "active_path": self.active_path,
            "total_study_time": self._total_study_time,
            "tasks_completed": self._total_tasks_completed,
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2),
                              encoding="utf-8")
        logger.info(f"[CurriculumEngine] 保存到 {path}")

    def load(self, path: str = None):
        path = path or os.environ.get("LAAP_STATE_PATH", "./agi_state/curriculum.json")
        """加载课程学习状态"""
        p = Path(path)
        if not p.exists():
            return False
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            for cname, mdata in data.get("mastery", {}).items():
                record = MasteryRecord(concept_name=cname)
                record.mastery = mdata.get("mastery", 0)
                record.confidence = mdata.get("confidence", 0)
                record.total_time_spent = mdata.get("total_hours", 0) * 3600
                record.practice_count = mdata.get("practices", 0)
                self.mastery[cname] = record
            self.active_path = data.get("active_path")
            self._total_study_time = data.get("total_study_time", 0)
            self._total_tasks_completed = data.get("tasks_completed", 0)
            logger.info(f"[CurriculumEngine] 加载完成: {len(self.mastery)} 条掌握记录")
            return True
        except Exception as e:
            logger.error(f"[CurriculumEngine] 加载失败: {e}")
            return False


# ═══════════════════════════════════════════════════════════════
# 测试
# ═══════════════════════════════════════════════════════════════

def test():
    engine = CurriculumEngine()
    logger.info("=" * 50)
    logger.info("P1-2 课程学习系统测试")
    logger.info("=" * 50)
    logger.info("\n=== 测试1: 概念注册 ===")
    logger.info(f"  总概念数: {len(engine.concepts)}")
    logger.info(f"  领域: {engine.stats()['domains']}")
    logger.info("\n=== 测试2: 知识缺口分析 ===")
    gaps = engine.find_knowledge_gaps(domain="cognition", min_gap=0.2)
    logger.info(f"  认知领域缺口: {len(gaps)} 个")
    for g in gaps[:5]:
        status = "✅ 可学" if g["ready_to_learn"] else "❌ 缺前置"
        logger.info(f"    {status} {g['concept']} (缺口={g['gap_size']:.2f}, 优先级={g['priority']:.2f})")
    logger.info("\n=== 测试3: 学习路径生成 ===")
    path = engine.generate_path("meta_cognition",
                                name="从零到元认知")
    logger.info(f"  路径: {path.name}")
    logger.info(f"  目标: {path.goals}")
    logger.info(f"  预计: {path.estimated_total_hours:.1f} 小时")
    logger.info(f"  步骤: {len(path.concepts)} 个概念")
    for i, (c, d) in enumerate(zip(path.concepts, path.difficulty_curve), 1):
        marker = "⭐" if c == path.concepts[-1] else "→"
        logger.info(f"    {i}. {marker} {c} (难度={d:.2f})")
    logger.info("\n=== 测试4: 学习与掌握度追踪 ===")
    for concept in ["PSI_cycle", "causal_reasoning", "emotional_intelligence"]:
        task = engine.generate_task_for_concept(concept)
        logger.info(f"  任务: {task.title} ({task.estimated_minutes}分钟)")
        for _ in range(3):
            engine.record_learning(concept, success=True,
                                   time_spent=task.estimated_minutes * 60,
                                   difficulty=task.difficulty)
        record = engine.get_mastery(concept)
        logger.info(f"  掌握度: {record.concept_name} → {record.mastery:.3f} ({record.get_level().name})")
    logger.info("\n=== 测试5: 遗忘曲线模拟 ===")
    record = engine.get_mastery("PSI_cycle")
    before = record.mastery
    # 模拟5小时后的遗忘
    record.last_practiced = time.time() - 5 * 3600
    record.apply_forgetting_curve(5)
    logger.info(f"  PSI_cycle: {before:.3f} → {record.mastery:.3f} (5小时后)")
    logger.info("\n=== 测试6: 最优下一步推荐 ===")
    next_c = engine.find_optimal_next(domain="social")
    if next_c:
        logger.info(f"  推荐学习: {next_c['concept']}")
        logger.info(f"  描述: {next_c['description']}")
        logger.info(f"  优先级: {next_c['priority']:.3f}")
        logger.info(f"  前置满足: {next_c['prerequisites_met']}")
    logger.info("\n=== 测试7: 路径进度 ===")
    for cname in path.concepts:
        engine.record_learning(cname, success=True, time_spent=1800)
        record = engine.get_mastery(cname)
        logger.info(f"  {cname}: mastery={record.mastery:.3f}")
    mastery_values = [engine.get_mastery(c).mastery for c in path.concepts]
    path.progress = sum(mastery_values) / len(mastery_values)
    logger.info(f"  路径总进度: {path.progress:.1%}")
    logger.info(f"\n=== 引擎统计 ===")
    for k, v in engine.stats().items():
        logger.info(f"  {k}: {v}")
    engine.save()
    logger.info(f"\n✅ P1-2 课程学习系统全部测试通过！")
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test()
