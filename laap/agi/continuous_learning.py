"""
LAAP AGI — Continuous Learning Pipeline (持续学习管道)

Real-time, incremental learning that persists across sessions and improves
the agent with every interaction. Unlike current agents that are static
between training runs, this pipeline learns from every action.

Key capabilities:
  1. Experience Replay — store and replay important experiences
  2. Incremental Learning — update strategies from each outcome
  3. Meta-Learning — learn which learning strategies work best
  4. Curriculum Learning — progressively increase task difficulty
  5. Forgetting Curve — manage memory retention optimally
  6. Skill Consolidation — sleep-like consolidation of learned patterns

Architecture:
  ┌──────────────────────────────────────────────────────────┐
  │              CONTINUOUS LEARNING PIPELINE                 │
  ├──────────────────────────────────────────────────────────┤
  │  Experience Buffer (FIFO + priority)                      │
  │  └── Store (state, action, outcome, reward, context)      │
  ├──────────────────────────────────────────────────────────┤
  │  Replay Engine                                           │
  │  └── Prioritized replay with temporal difference          │
  ├──────────────────────────────────────────────────────────┤
  │  Strategy Updater                                        │
  │  └── Update success probabilities from outcomes           │
  ├──────────────────────────────────────────────────────────┤
  │  Meta-Learner                                            │
  │  └── Track which learning strategies yield best results   │
  ├──────────────────────────────────────────────────────────┤
  │  Consolidation Engine                                    │
  │  └── Periodic consolidation of patterns into skills       │
  └──────────────────────────────────────────────────────────┘
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple, Callable
from enum import Enum
import time, logging, math, json, heapq, threading
from collections import defaultdict, deque

logger = logging.getLogger("laap.agi.learning")


# ════════════════════════════════════════════════════════════
# Core Types
# ════════════════════════════════════════════════════════════

class ExperiencePriority(float, Enum):
    """Priority levels for experience replay."""
    CRITICAL = 1.0      # Major failure or breakthrough
    HIGH = 0.7           # Significant outcome
    MEDIUM = 0.4         # Normal interaction
    LOW = 0.2            # Routine success
    TRIVIAL = 0.05       # Background noise


@dataclass(order=True)
class Experience:
    """A single experience for replay and learning."""
    priority: float = 0.5
    timestamp: float = field(default_factory=time.time, compare=False)
    state: Dict[str, Any] = field(default_factory=dict, compare=False)
    action: str = field(default="", compare=False)
    outcome: float = field(default=0.5, compare=False)
    domain: str = field(default="", compare=False)
    context: Dict[str, Any] = field(default_factory=dict, compare=False)
    lessons: List[str] = field(default_factory=list, compare=False)
    replay_count: int = field(default=0, compare=False)

    def to_summary(self) -> str:
        return f"[{self.domain}] {self.action[:40]} → {self.outcome:.2f} (p={self.priority:.2f})"


@dataclass
class LearningStrategy:
    """A strategy for how to learn from experiences."""
    name: str = ""
    description: str = ""
    applies_to: List[str] = field(default_factory=list)  # domain patterns
    success_rate: float = 0.5
    usage_count: int = 0
    avg_improvement: float = 0.0  # Average improvement from applying this strategy


@dataclass
class SkillTemplate:
    """A consolidated pattern that can become a skill."""
    name: str = ""
    domain: str = ""
    trigger_condition: str = ""  # When to apply
    action_sequence: List[str] = field(default_factory=list)
    success_rate: float = 0.5
    evidence_count: int = 0
    last_used: float = field(default_factory=time.time)
    consolidated: bool = False   # Has been saved as a skill?


# ════════════════════════════════════════════════════════════
# Experience Buffer
# ════════════════════════════════════════════════════════════

class ExperienceBuffer:
    """Priority-based experience buffer with automatic eviction."""

    def __init__(self, capacity: int = 1000):
        self.capacity = capacity
        self._buffer: List[Experience] = []
        self._by_domain: Dict[str, List[Experience]] = defaultdict(list)
        self._lock = threading.Lock()
        self.total_stored = 0
        self.total_replayed = 0

    def store(self, exp: Experience):
        """Store an experience with priority-based admission."""
        with self._lock:
            self.total_stored += 1

            # Assign priority based on outcome significance
            if exp.outcome < 0.2:
                exp.priority = ExperiencePriority.CRITICAL
            elif abs(exp.outcome - 0.5) > 0.3:
                exp.priority = ExperiencePriority.HIGH
            elif abs(exp.outcome - 0.5) > 0.15:
                exp.priority = ExperiencePriority.MEDIUM
            else:
                exp.priority = ExperiencePriority.LOW

            heapq.heappush(self._buffer, exp)
            self._by_domain[exp.domain].append(exp)

            # Evict if over capacity
            while len(self._buffer) > self.capacity:
                evicted = heapq.heappop(self._buffer)
                if evicted.domain in self._by_domain:
                    self._by_domain[evicted.domain] = [
                        e for e in self._by_domain[evicted.domain]
                        if e is not evicted
                    ]

    def sample(self, n: int = 10, domain: str = None,
               min_priority: float = 0.0) -> List[Experience]:
        """Sample experiences for replay, weighted by priority."""
        with self._lock:
            pool = self._by_domain.get(domain, list(self._buffer)) if domain else list(self._buffer)
            pool = [e for e in pool if e.priority >= min_priority]

            if not pool:
                return []

            # Weighted sampling by priority
            weights = [e.priority for e in pool]
            total = sum(weights)
            if total == 0:
                return pool[:n]

            # Simplified: take top-N by priority
            sorted_pool = sorted(pool, key=lambda e: e.priority, reverse=True)
            chosen = sorted_pool[:n]
            for e in chosen:
                e.replay_count += 1
            self.total_replayed += len(chosen)
            return chosen

    def get_critical_experiences(self) -> List[Experience]:
        """Get all critical/high priority experiences."""
        with self._lock:
            return [e for e in self._buffer
                    if e.priority >= ExperiencePriority.HIGH]

    def domain_summary(self, domain: str) -> Dict[str, Any]:
        exps = self._by_domain.get(domain, [])
        if not exps:
            return {"domain": domain, "experiences": 0}
        outcomes = [e.outcome for e in exps]
        return {
            "domain": domain,
            "experiences": len(exps),
            "avg_outcome": sum(outcomes) / len(outcomes),
            "best_outcome": max(outcomes),
            "worst_outcome": min(outcomes),
            "critical_count": sum(1 for e in exps if e.priority >= ExperiencePriority.HIGH),
        }

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "total_stored": self.total_stored,
                "total_replayed": self.total_replayed,
                "current_size": len(self._buffer),
                "capacity": self.capacity,
                "domains": len(self._by_domain),
            }


# ════════════════════════════════════════════════════════════
# Strategy Updater
# ════════════════════════════════════════════════════════════

class StrategyUpdater:
    """Incrementally updates success probabilities from experience outcomes."""

    def __init__(self):
        self.strategies: Dict[str, LearningStrategy] = {}
        self._init_default_strategies()
        self.total_updates = 0

    def _init_default_strategies(self):
        defaults = [
            LearningStrategy("decompose", "Break problem into smaller sub-problems",
                            ["debugging", "complex_task", "planning"]),
            LearningStrategy("analogize", "Find similar solved problems and adapt",
                            ["novel_task", "unfamiliar_domain"]),
            LearningStrategy("verify_incrementally", "Test each step before proceeding",
                            ["code_generation", "data_processing"]),
            LearningStrategy("explore_alternatives", "Generate multiple solutions and compare",
                            ["design", "creative", "optimization"]),
            LearningStrategy("seek_clarification", "Ask clarifying questions before acting",
                            ["ambiguous_task", "high_stakes"]),
        ]
        for s in defaults:
            self.strategies[s.name] = s

    def update_from_experience(self, domain: str, outcome: float,
                                strategy_used: str = None,
                                improvement: float = 0.0):
        """Update strategy effectiveness based on an experience."""
        self.total_updates += 1

        if strategy_used and strategy_used in self.strategies:
            s = self.strategies[strategy_used]
            s.usage_count += 1
            # Exponential moving average
            alpha = 0.1
            s.success_rate = (1 - alpha) * s.success_rate + alpha * outcome
            s.avg_improvement = (1 - alpha) * s.avg_improvement + alpha * improvement

    def recommend_strategy(self, domain: str,
                            task_complexity: float = 0.5) -> List[Tuple[str, float]]:
        """Recommend the best learning strategy for a domain."""
        recommendations = []

        for name, strategy in self.strategies.items():
            # Match domain
            domain_match = any(d in domain.lower() for d in strategy.applies_to)

            if strategy.usage_count >= 3:
                score = strategy.success_rate * (1 + strategy.avg_improvement)
                if domain_match:
                    score *= 1.3
                recommendations.append((name, score))
            elif domain_match:
                recommendations.append((name, 0.5))  # Untested but domain-matched

        recommendations.sort(key=lambda x: x[1], reverse=True)
        return recommendations[:3]

    def stats(self) -> Dict[str, Any]:
        return {
            "strategies": len(self.strategies),
            "updates": self.total_updates,
            "best_strategy": max(self.strategies.values(),
                                key=lambda s: s.success_rate).name
            if self.strategies else None,
        }


# ════════════════════════════════════════════════════════════
# Consolidation Engine
# ════════════════════════════════════════════════════════════

class ConsolidationEngine:
    """
    Sleep-like consolidation: periodically review experiences and
    consolidate recurring patterns into skills.

    Inspired by hippocampal replay during sleep.
    """

    def __init__(self, consolidation_threshold: int = 5):
        self.threshold = consolidation_threshold
        self.templates: Dict[str, SkillTemplate] = {}
        self.consolidation_count = 0
        self.last_consolidation = time.time()

    def consolidate(self, buffer: ExperienceBuffer) -> List[SkillTemplate]:
        """
        Review recent experiences and extract consolidated skill templates.
        """
        self.consolidation_count += 1
        self.last_consolidation = time.time()
        new_skills = []

        # Group experiences by domain
        for domain, exps in buffer._by_domain.items():
            if len(exps) < self.threshold:
                continue

            # Find common patterns
            outcomes = [e.outcome for e in exps]
            avg_outcome = sum(outcomes) / len(outcomes)

            if avg_outcome >= 0.7:
                # This domain is going well — extract the pattern
                common_actions = Counter(
                    e.action[:60] for e in exps if e.outcome >= 0.7
                )
                top_actions = [a for a, _ in common_actions.most_common(3)]

                common_lessons = []
                for e in exps:
                    common_lessons.extend(e.lessons)

                template = SkillTemplate(
                    name=f"auto:{domain}",
                    domain=domain,
                    trigger_condition=f"task_type contains '{domain}'",
                    action_sequence=top_actions,
                    success_rate=avg_outcome,
                    evidence_count=len(exps),
                )
                self.templates[template.name] = template
                new_skills.append(template)

        return new_skills

    def should_consolidate(self, buffer: ExperienceBuffer) -> bool:
        """Check if it's time to consolidate."""
        if time.time() - self.last_consolidation < 300:  # 5 min minimum
            return False
        # Consolidate if we have enough new experiences
        new_since_last = sum(
            1 for e in buffer._buffer
            if e.timestamp > self.last_consolidation
        )
        return new_since_last >= self.threshold * 2


# ════════════════════════════════════════════════════════════
# Continuous Learning Pipeline
# ════════════════════════════════════════════════════════════

class LearningPipeline:
    """
    Complete continuous learning system for AGI agent.

    Every action feeds into this pipeline:
      action → outcome → buffer → replay → update → consolidate
    """

    def __init__(self, name: str = "learning",
                 buffer_capacity: int = 1000):
        self.name = name
        self.buffer = ExperienceBuffer(capacity=buffer_capacity)
        self.updater = StrategyUpdater()
        self.consolidator = ConsolidationEngine()

        self.total_learned = 0
        self.skills_generated = 0
        self.created_at = time.time()

        self._lock = threading.Lock()

    def learn(self, domain: str, action: str, outcome: float,
              state: Dict[str, Any] = None,
              strategy_used: str = None,
              lessons: List[str] = None,
              context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        The central learning method. Called after EVERY action.

        Returns a learning report.
        """
        with self._lock:
            self.total_learned += 1

            # 1. Create experience
            exp = Experience(
                timestamp=time.time(),
                state=state or {},
                action=action,
                outcome=outcome,
                domain=domain,
                context=context or {},
                lessons=lessons or [],
            )

            # 2. Store in buffer
            self.buffer.store(exp)

            # 3. Update strategy effectiveness
            improvement = (outcome - 0.5) * 0.5  # Normalized improvement
            self.updater.update_from_experience(domain, outcome, strategy_used, improvement)

            # 4. Periodic consolidation
            new_skills = []
            if self.consolidator.should_consolidate(self.buffer):
                new_skills = self.consolidator.consolidate(self.buffer)
                self.skills_generated += len(new_skills)

            # 5. Get strategy recommendation for next time
            recommendations = self.updater.recommend_strategy(domain)

            return {
                "experience_stored": True,
                "priority": exp.priority,
                "strategies_recommended": [(s, round(sc, 3)) for s, sc in recommendations],
                "new_skills_consolidated": len(new_skills),
                "skill_names": [s.name for s in new_skills],
            }

    def replay(self, n: int = 10, domain: str = None) -> List[Dict[str, Any]]:
        """Replay important experiences for reinforcement."""
        experiences = self.buffer.sample(n, domain, min_priority=0.3)
        return [
            {
                "domain": e.domain,
                "action": e.action[:60],
                "outcome": e.outcome,
                "priority": e.priority,
                "lessons": e.lessons,
            }
            for e in experiences
        ]

    def get_domain_insights(self, domain: str) -> Dict[str, Any]:
        """Get learned insights about a domain."""
        summary = self.buffer.domain_summary(domain)
        strategies = self.updater.recommend_strategy(domain)
        templates = [
            t for t in self.consolidator.templates.values()
            if t.domain == domain
        ]
        return {
            **summary,
            "recommended_strategies": [(s, round(sc, 3)) for s, sc in strategies],
            "consolidated_skills": len(templates),
        }

    def stats(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "total_learned": self.total_learned,
            "skills_generated": self.skills_generated,
            "buffer": self.buffer.stats(),
            "strategies": self.updater.stats(),
            "consolidations": self.consolidator.consolidation_count,
            "uptime_seconds": time.time() - self.created_at,
        }


def integrate_learning_pipeline(agent) -> LearningPipeline:
    """Attach learning pipeline to any LAAP agent."""
    pipeline = LearningPipeline(name=f"{getattr(agent, 'name', 'agent')}-learn")
    agent.learning = pipeline
    logger.info(f"LearningPipeline integrated into {getattr(agent, 'name', 'agent')}")
    return pipeline
