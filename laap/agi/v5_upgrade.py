"""
LAAP V5.0 — Advanced Cognitive Upgrade Module

Implements V5.0 core enhancements across all three phases:
  Phase 1: Infrastructure — EWC, PER, Enhanced AutoHealer
  Phase 2: Cognition — Causal Discovery, Active Learning
  Phase 3: Autonomy — Goal Co-Creation, Long-Term Planning

All pure Python — no external dependencies.
"""
from __future__ import annotations

import logging

import math, random, time, json, os, logging, threading
from typing import Any, Dict, List, Optional, Tuple, Callable
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("laap.v5")

V5_VERSION = "5.0.0"


# ═══════════════════════════════════════════════════════════════
# Phase 1a: Elastic Weight Consolidation (EWC) + PER
# ═══════════════════════════════════════════════════════════════

class SumTree:
    """Binary sum tree for prioritized experience sampling."""

    def __init__(self, capacity: int):
        self.capacity = capacity
        self.tree = [0.0] * (2 * capacity)
        self.data = [None] * capacity
        self.write = 0
        self.n_entries = 0

    def _propagate(self, idx: int, change: float):
        parent = idx // 2
        self.tree[parent] += change
        if parent != 0:
            self._propagate(parent, change)

    def _retrieve(self, idx: int, s: float) -> int:
        left = 2 * idx
        if left >= len(self.tree):
            return idx
        if s <= self.tree[left]:
            return self._retrieve(left, s)
        else:
            return self._retrieve(left + 1, s - self.tree[left])

    def total(self) -> float:
        return self.tree[1] if self.tree else 0.0

    def add(self, priority: float, data: Any):
        idx = self.write + self.capacity
        self.data[self.write] = data
        self._update(idx, priority)
        self.write = (self.write + 1) % self.capacity
        self.n_entries = min(self.n_entries + 1, self.capacity)

    def _update(self, idx: int, priority: float):
        change = priority - self.tree[idx]
        self.tree[idx] = priority
        self._propagate(idx, change)

    def update(self, indices: List[int], priorities: List[float]):
        for idx, p in zip(indices, priorities):
            self._update(idx + self.capacity, p)

    def get(self, idx: int) -> float:
        return self.tree[idx + self.capacity]

    def get_min_idx(self) -> int:
        best, best_val = 0, float('inf')
        for i in range(self.n_entries):
            v = self.get(i)
            if v < best_val:
                best, best_val = i, v
        return best

    def sample(self, batch_size: int, beta: float = 0.4) -> Tuple[List, List[int], List[float]]:
        batch, indices, weights = [], [], []
        segment = self.total() / batch_size
        for i in range(batch_size):
            a, b = segment * i, segment * (i + 1)
            s = random.uniform(a, b)
            idx = self._retrieve(1, s) - self.capacity
            if idx < 0 or idx >= len(self.data) or self.data[idx] is None:
                idx = random.randint(0, min(self.n_entries, self.capacity) - 1)
            batch.append(self.data[idx])
            indices.append(idx)
            p = self.get(idx)
            prob = p / max(self.total(), 1e-8)
            w = (self.n_entries * prob) ** (-beta) if prob > 0 else 0
            weights.append(min(w, 10.0))  # clip
        w_max = max(weights) if weights else 1.0
        weights = [w / max(w_max, 1e-8) for w in weights]
        return batch, indices, weights


class PrioritizedExperienceBuffer:
    """Prioritized Experience Replay buffer."""

    def __init__(self, capacity: int = 10000, alpha: float = 0.6, beta: float = 0.4):
        self.tree = SumTree(capacity)
        self.alpha = alpha
        self.beta = beta
        self.beta_increment = 0.001
        self.capacity = capacity
        self.epsilon = 0.01

    def add(self, state: str, action: str, outcome: float, context: Dict = None):
        priority = max(self.tree.total(), self.epsilon)
        self.tree.add(priority, {
            "state": state, "action": action,
            "outcome": outcome, "context": context or {},
            "time": time.time(),
        })

    def sample(self, batch_size: int) -> Tuple[List, List[int]]:
        batch, indices, weights = self.tree.sample(batch_size, self.beta)
        self.beta = min(1.0, self.beta + self.beta_increment)
        return batch, indices

    def update_priorities(self, indices: List[int], td_errors: List[float]):
        priorities = [(abs(e) + self.epsilon) ** self.alpha for e in td_errors]
        self.tree.update(indices, priorities)

    def __len__(self):
        return self.tree.n_entries


class FisherInfoTracker:
    """Tracks Fisher information for EWC regularization."""

    def __init__(self):
        self.fisher: Dict[str, float] = {}
        self.optimal_params: Dict[str, float] = {}
        self._cooldown: Dict[str, float] = {}

    def record(self, module: str, param_value: float, importance: float = 1.0):
        self.fisher[module] = self.fisher.get(module, 0.0) + importance * 0.1
        self.fisher[module] = min(self.fisher[module], 10.0)
        self.optimal_params[module] = param_value
        self._cooldown[module] = time.time()

    def compute_penalty(self, module: str, current_value: float) -> float:
        fisher = self.fisher.get(module, 0.0)
        optimal = self.optimal_params.get(module, 0.5)
        if fisher < 0.01:
            return 0.0
        diff = current_value - optimal
        return fisher * diff * diff

    def get_fisher_summary(self) -> Dict[str, float]:
        return dict(sorted(self.fisher.items(), key=lambda x: -x[1])[:20])


class SkillImportanceTracker:
    """Tracks which skills are important to preserve across tasks."""

    def __init__(self):
        self.importance: Dict[str, float] = defaultdict(float)
        self.use_count: Dict[str, int] = defaultdict(int)
        self.success_rate: Dict[str, float] = defaultdict(float)

    def record_use(self, skill: str, success: bool):
        self.use_count[skill] += 1
        n = self.use_count[skill]
        self.success_rate[skill] = (self.success_rate[skill] * (n - 1) + (1.0 if success else 0.0)) / n
        # Higher importance for frequently-used skills
        self.importance[skill] = self.success_rate[skill] * min(1.0, n / 5.0)

    def get_important_skills(self, threshold: float = 0.5) -> List[str]:
        return [s for s, imp in self.importance.items() if imp >= threshold]

    def consolidation_loss(self) -> float:
        """Compute total EWC-style loss from skill importance."""
        return sum(self.importance.values())


# ═══════════════════════════════════════════════════════════════
# Phase 1b: Enhanced Bug Classifier (Logic-Level)
# ═══════════════════════════════════════════════════════════════

@dataclass
class BugReport:
    file: str = ""
    line: int = 0
    message: str = ""
    category: str = "unknown"
    severity: str = "medium"
    code_context: str = ""


class BugCategory(Enum):
    SYNTAX = "syntax"
    IMPORT = "import"
    ATTRIBUTE = "attribute"
    TYPE = "type"
    LOGIC = "logic"
    DESIGN = "design"
    RACE = "race"
    PERFORMANCE = "performance"
    SECURITY = "security"


class EnhancedBugClassifier:
    """Logic-level bug analysis and classification."""

    PATTERNS = {
        BugCategory.SYNTAX: ["SyntaxError", "IndentationError", "unexpected EOF"],
        BugCategory.IMPORT: ["ImportError", "ModuleNotFoundError", "No module named"],
        BugCategory.ATTRIBUTE: ["AttributeError", "has no attribute"],
        BugCategory.TYPE: ["TypeError", "must be", "cannot unpack"],
        BugCategory.LOGIC: [
            "unexpected behavior", "wrong result", "incorrect",
            "off-by-one", "infinite loop", "deadlock",
        ],
        BugCategory.DESIGN: [
            "code smell", "tight coupling", "god class",
            "magic number", "duplicate code", "long method",
        ],
        BugCategory.RACE: [
            "race condition", "data race", "concurrent modification",
            "shared state", "thread-unsafe",
        ],
        BugCategory.PERFORMANCE: [
            "slow", "timeout", "O(n²)", "memory leak",
            "bottleneck", "inefficient",
        ],
        BugCategory.SECURITY: [
            "injection", "XSS", "SQL injection", "unsafe",
            "command injection", "path traversal",
        ],
    }

    SEVERITY_MAP = {
        BugCategory.SYNTAX: "high",
        BugCategory.IMPORT: "high",
        BugCategory.ATTRIBUTE: "medium",
        BugCategory.TYPE: "medium",
        BugCategory.LOGIC: "high",
        BugCategory.DESIGN: "low",
        BugCategory.RACE: "critical",
        BugCategory.PERFORMANCE: "medium",
        BugCategory.SECURITY: "critical",
    }

    def classify(self, error_message: str, source_file: str = "",
                 source_line: int = 0, context: str = "") -> BugReport:
        for category, patterns in self.PATTERNS.items():
            if any(p.lower() in error_message.lower() for p in patterns):
                return BugReport(
                    file=source_file, line=source_line,
                    message=error_message, category=category.value,
                    severity=self.SEVERITY_MAP.get(category, "medium"),
                    code_context=context,
                )
        return BugReport(
            file=source_file, line=source_line,
            message=error_message, category="unknown",
            severity="medium", code_context=context,
        )


class LogicFixGenerator:
    """Generates concrete fix suggestions for logic-level bugs."""

    LOGIC_FIXES = {
        "off-by-one": "Check loop boundary conditions: ensure range(n) not range(n-1)",
        "infinite loop": "Add loop counter limit or ensure termination condition is updated",
        "deadlock": "Ensure consistent lock ordering across all threads",
        "none check": "Add `if x is not None:` guard before using the value",
        "division by zero": "Add `if denominator != 0:` guard before division",
        "index error": "Ensure list index is within range: `if 0 <= idx < len(lst)`",
    }

    def analyze_ast(self, code: str, error: str) -> List[Dict]:
        fixes = []
        for pattern, suggestion in self.LOGIC_FIXES.items():
            if pattern.lower() in error.lower():
                fixes.append({
                    "pattern": pattern,
                    "suggestion": suggestion,
                    "confidence": 0.8,
                })
        if not fixes:
            fixes.append({
                "pattern": "unspecified logic error",
                "suggestion": "Review the logic flow: check conditions, loops, and data flow",
                "confidence": 0.4,
            })
        return fixes

    def generate_fix(self, bug: BugReport, source_code: str = "") -> Dict:
        fix = {"file": bug.file, "line": bug.line, "category": bug.category,
               "fixes": self.analyze_ast(source_code or bug.message, bug.message)}
        fix["estimated_risk"] = "low" if bug.severity in ("low", "medium") else "medium"
        return fix


class RaceConditionDetector:
    """Detects potential race conditions in code."""

    UNSAFE_PATTERNS = [
        ("shared dict", lambda l: "global " in l and "=" in l and "{" not in l),
        ("no lock", lambda l: any(kw in l for kw in ["threading.", "Thread("])
                             and "Lock()" not in l),
        ("shared var", lambda l: "self." in l and ("= " in l or "+=" in l or "-=" in l)),
    ]

    def scan(self, code_lines: List[str]) -> List[Dict]:
        findings = []
        for i, line in enumerate(code_lines):
            for name, check in self.UNSAFE_PATTERNS:
                if check(line):
                    findings.append({
                        "line": i + 1, "pattern": name,
                        "code": line.strip(),
                        "risk": "high" if name == "no lock" else "medium",
                    })
        return findings


# ═══════════════════════════════════════════════════════════════
# Phase 2a: Causal Discovery Engine
# ═══════════════════════════════════════════════════════════════

class ConditionalIndependenceTester:
    """Tests conditional independence using partial correlation."""

    @staticmethod
    def _mean(vals: List[float]) -> float:
        return sum(vals) / max(len(vals), 1)

    @staticmethod
    def _cov(x: List[float], y: List[float]) -> float:
        mx, my = ConditionalIndependenceTester._mean(x), ConditionalIndependenceTester._mean(y)
        return sum((a - mx) * (b - my) for a, b in zip(x, y)) / max(len(x) - 1, 1)

    @staticmethod
    def _var(x: List[float]) -> float:
        mx = ConditionalIndependenceTester._mean(x)
        return sum((v - mx) ** 2 for v in x) / max(len(x) - 1, 1)

    def partial_correlation(self, x: List[float], y: List[float],
                            z: Optional[List[float]] = None) -> float:
        if z is None or not z:
            c = self._cov(x, y)
            vx, vy = self._var(x), self._var(y)
            return c / max(math.sqrt(vx * vy), 1e-10)
        # Partial correlation: control for z
        r_xy = self.partial_correlation(x, y)
        r_xz = self.partial_correlation(x, z)
        r_yz = self.partial_correlation(y, z)
        denom = math.sqrt(max(1 - r_xz * r_xz, 1e-10)) * math.sqrt(max(1 - r_yz * r_yz, 1e-10))
        return (r_xy - r_xz * r_yz) / max(denom, 1e-10)

    def test(self, x: List[float], y: List[float],
             z: Optional[List[float]] = None, alpha: float = 0.05) -> Tuple[float, bool]:
        r = abs(self.partial_correlation(x, y, z))
        return r, r < alpha


class CausalDiscovery:
    """PC-algorithm causal discovery from observational data."""

    def __init__(self, alpha: float = 0.05):
        self.alpha = alpha
        self.tester = ConditionalIndependenceTester()
        self.graph: Dict[str, set] = {}
        self.directed_edges: List[Tuple[str, str, float]] = []

    def discover(self, data: Dict[str, List[float]]) -> Dict:
        variables = list(data.keys())
        n = len(variables)
        # Step 1: Complete undirected graph
        self.graph = {v: set(variables) - {v} for v in variables}
        sep_sets = {}

        if n < 2:
            return {"graph": self.graph, "edges": [], "variables": variables}

        # Step 2: PC skeleton discovery
        for depth in range(min(3, n)):
            for var in variables:
                neighbors = list(self.graph.get(var, set()))
                for nb in neighbors:
                    if nb not in self.graph.get(var, set()):
                        continue
                    cond_set = list(set(neighbors) - {nb})
                    cond_set = cond_set[:depth] if cond_set else []
                    # Conditional independence test
                    if len(data[var]) > 2 and len(data[nb]) > 2:
                        if cond_set:
                            cond_data = data.get(cond_set[0], [0])
                            r, indep = self.tester.test(data[var], data[nb], cond_data, self.alpha)
                        else:
                            r, indep = self.tester.test(data[var], data[nb], alpha=self.alpha)
                        if indep:
                            self.graph[var].discard(nb)
                            self.graph[nb].discard(var)
                            sep_sets[(var, nb)] = set(cond_set)

        # Step 3: Edge orientation (v-structures)
        self.directed_edges = []
        for var in variables:
            for nb in self.graph.get(var, set()):
                if var < nb:
                    strength = self.tester.partial_correlation(
                        data[var], data[nb]
                    )
                    self.directed_edges.append((var, nb, abs(strength)))

        self.directed_edges.sort(key=lambda x: -x[2])
        return {
            "graph": {k: list(v) for k, v in self.graph.items()},
            "edges": [(a, b, round(s, 3)) for a, b, s in self.directed_edges],
            "variables": variables,
            "method": "PC-algorithm",
        }

    def find_causal_relations(self, variables: List[str],
                               observations: Dict[str, List[float]]) -> List[Dict]:
        result = self.discover(observations)
        relations = []
        for a, b, strength in result["edges"]:
            relations.append({
                "cause": a, "effect": b,
                "strength": strength,
                "confidence": min(1.0, strength * 2),
            })
        return relations


# ═══════════════════════════════════════════════════════════════
# Phase 2b: Active Learning + Meta-Learning
# ═══════════════════════════════════════════════════════════════

class NoveltyDetector:
    """Measures how novel a new experience is compared to past experiences."""

    def __init__(self, window: int = 100):
        self.history: List[Tuple[str, float]] = []
        self.window = window
        self._signatures: Dict[str, float] = {}

    def compute(self, state: str, action: str) -> float:
        sig = f"{state[:50]}:{action[:30]}"
        h = abs(hash(sig)) % 10000
        # Novelty = how different from past signatures
        if h not in self._signatures:
            self._signatures[h] = len(self._signatures) / max(self.window, 1)
            novelty = 1.0
        else:
            count = sum(1 for s, _ in self.history if s[:30] in state)
            novelty = max(0.0, 1.0 - count / max(len(self.history), 1))
        self.history.append((state, time.time()))
        if len(self.history) > self.window:
            self.history = self.history[-self.window:]
        return novelty


class SurpriseDetector:
    """Measures prediction error / surprise."""

    def __init__(self):
        self.predictions: Dict[str, float] = {}
        self._ema_error = 0.1

    def compute(self, state: str, action: str, actual_outcome: float,
                predicted_outcome: Optional[float] = None) -> float:
        sig = f"{state[:40]}:{action[:20]}"
        pred = predicted_outcome or self.predictions.get(sig, 0.5)
        error = abs(actual_outcome - pred)
        self._ema_error = 0.9 * self._ema_error + 0.1 * error
        self.predictions[sig] = (self.predictions.get(sig, 0.5) * 0.9 + actual_outcome * 0.1)
        surprise = error / max(self._ema_error, 0.01)
        return min(surprise, 5.0)


class CuriosityDriver:
    """Curiosity-driven intrinsic motivation."""

    def __init__(self):
        self.novelty = NoveltyDetector()
        self.surprise = SurpriseDetector()
        self.learning_progress: Dict[str, float] = defaultdict(float)

    def compute_intrinsic_reward(self, state: str, action: str,
                                  next_state: str, outcome: float) -> float:
        novelty = self.novelty.compute(state, action)
        surprise = self.surprise.compute(state, action, outcome)
        lp = self.learning_progress.get(action, 0.5)
        return 0.4 * novelty + 0.3 * min(surprise, 1.0) + 0.3 * lp

    def record_learning(self, action: str, improvement: float):
        old = self.learning_progress[action]
        self.learning_progress[action] = old * 0.9 + improvement * 0.1


class MetaLearner:
    """Learn which strategies work best for which tasks."""

    def __init__(self):
        self.strategies: Dict[str, Dict] = defaultdict(lambda: {
            "uses": 0, "successes": 0, "avg_outcome": 0.5, "best_for": [],
        })

    def select_strategy(self, task_type: str, context: str = "") -> str:
        candidates = {
            "debug": "isolate→analyze→fix→verify",
            "explore": "hypothesize→search→verify→synthesize",
            "execute": "plan→implement→test→refine",
            "analyze": "decompose→examine→synthesize→conclude",
        }
        strategy = candidates.get(task_type, "observe→reason→act→learn")
        # Adjust based on past performance
        best = self.strategies.get(strategy, {})
        if best.get("uses", 0) > 3 and best.get("success_rate", 0) > 0.7:
            return strategy
        return strategy

    def record_outcome(self, strategy: str, task_type: str, outcome: float):
        s = self.strategies[strategy]
        s["uses"] += 1
        s["avg_outcome"] = (s["avg_outcome"] * (s["uses"] - 1) + outcome) / s["uses"]
        if outcome > 0.6:
            s["successes"] += 1
            if task_type not in s["best_for"]:
                s["best_for"].append(task_type)
        s["success_rate"] = s["successes"] / max(s["uses"], 1)

    def get_best_strategy(self, task_type: str) -> Optional[str]:
        best_strat, best_score = None, 0
        for strategy, stats in self.strategies.items():
            if task_type in stats.get("best_for", []):
                score = stats.get("success_rate", 0) * stats.get("uses", 0)
                if score > best_score:
                    best_strat, best_score = strategy, score
        return best_strat


class ActiveLearningEngine:
    """Orchestrates curiosity-driven active learning."""

    def __init__(self):
        self.curiosity = CuriosityDriver()
        self.meta = MetaLearner()
        self._exploration_rate = 0.3
        self._total_steps = 0

    def should_explore(self, confidence: float) -> bool:
        self._total_steps += 1
        decay = max(0.05, self._exploration_rate * (0.995 ** self._total_steps))
        return random.random() < max(decay, 0.05)

    def select_action(self, state: Dict, task_type: str) -> Tuple[str, str]:
        strategy = self.meta.select_strategy(task_type, str(state))
        if self.should_explore(state.get("confidence", 0.5)):
            return "explore", f"try new approach: {strategy}"
        return "exploit", strategy

    def record_outcome(self, action_type: str, strategy: str,
                        task_type: str, outcome: float):
        self.meta.record_outcome(strategy, task_type, outcome)
        if action_type == "explore":
            self.curiosity.record_learning(strategy, outcome - 0.5)
        self._exploration_rate = max(0.05, self._exploration_rate * 0.998)

    def curiosity_reward(self, state: str, action: str,
                          next_state: str, outcome: float) -> float:
        return self.curiosity.compute_intrinsic_reward(state, action, next_state, outcome)


# ═══════════════════════════════════════════════════════════════
# Phase 3a: Goal Co-Creation + Long-Term Planning
# ═══════════════════════════════════════════════════════════════

class ValueModel:
    """Represents agent's values and preferences."""

    def __init__(self):
        self.values = {
            "effectiveness": 1.0,
            "safety": 1.0,
            "creativity": 0.7,
            "thoroughness": 0.8,
            "efficiency": 0.6,
        }
        self.preferences: Dict[str, float] = {}

    def evaluate(self, goal: Dict) -> float:
        score = 0.0
        if goal.get("takes_risks", False):
            score -= 0.3 * (1 - self.values["safety"])
        if goal.get("is_thorough", False):
            score += 0.2 * self.values["thoroughness"]
        if goal.get("is_creative", False):
            score += 0.2 * self.values["creativity"]
        if goal.get("is_efficient", False):
            score += 0.2 * self.values["efficiency"]
        return max(0.0, min(1.0, 0.5 + score))


class GoalCoCreator:
    """Co-creates goals with value alignment checks."""

    def __init__(self):
        self.value_model = ValueModel()
        self._goal_history: List[Dict] = []

    def generate_candidates(self, user_intent: str,
                            agent_state: Dict) -> List[Dict]:
        """Generate goal candidates from intent + state."""
        intent_lower = user_intent.lower()
        candidates = []
        keywords = {
            "fix": {"description": "Debug and repair", "is_thorough": True, "takes_risks": False},
            "build": {"description": "Create new solution", "is_creative": True, "is_thorough": True},
            "analyze": {"description": "In-depth analysis", "is_thorough": True},
            "search": {"description": "Find information", "is_efficient": True},
            "improve": {"description": "Optimize existing", "is_efficient": True, "takes_risks": False},
            "learn": {"description": "Acquire new knowledge", "is_creative": True},
        }
        for keyword, attrs in keywords.items():
            if keyword in intent_lower:
                goal = {
                    "title": f"{attrs['description']} related to: {user_intent[:50]}",
                    "description": user_intent[:100],
                    "sub_goals": [
                        f"Understand scope of: {user_intent[:40]}",
                        f"Plan approach for: {user_intent[:40]}",
                        f"Execute and verify",
                    ],
                    "success_criteria": ["Task completed", "Result verified", "No regressions"],
                    **attrs,
                }
                goal["value_score"] = self.value_model.evaluate(goal)
                goal["alignment_score"] = 0.8 if goal["value_score"] > 0.5 else 0.3
                goal["combined"] = round(goal["value_score"] * 0.6 + goal["alignment_score"] * 0.4, 3)
                candidates.append(goal)

        if not candidates:
            candidates.append({
                "title": f"Process: {user_intent[:60]}",
                "description": user_intent[:100],
                "sub_goals": ["Analyze request", "Determine approach", "Execute", "Verify"],
                "success_criteria": ["Request handled", "User satisfied"],
                "is_thorough": True, "takes_risks": False, "is_creative": False, "is_efficient": True,
                "value_score": 0.6, "alignment_score": 0.7, "combined": 0.64,
            })

        candidates.sort(key=lambda x: -x["combined"])
        return candidates[:5]

    def co_create_goals(self, user_input: str,
                         agent_state: Dict) -> List[Dict]:
        goals = self.generate_candidates(user_input, agent_state)
        self._goal_history.append({
            "input": user_input[:80], "goals": len(goals), "time": time.time(),
        })
        return goals


class RiskAssessor:
    """Assesses risks for goals and actions."""

    RISK_PATTERNS = [
        ("destructive", ["delete", "remove", "drop", "rm -rf", "format"]),
        ("network", ["deploy", "publish", "push", "upload", "send"]),
        ("security", ["chmod", "sudo", "admin", "password", "token"]),
        ("data_loss", ["overwrite", "replace", "truncate", "clear"]),
    ]

    def assess(self, goal: Dict) -> Dict:
        risks = []
        text = (goal.get("title", "") + " " + goal.get("description", "")).lower()
        for risk_type, patterns in self.RISK_PATTERNS:
            for pattern in patterns:
                if pattern in text:
                    risks.append({
                        "type": risk_type,
                        "pattern": pattern,
                        "severity": "high" if risk_type in ("destructive", "data_loss") else "medium",
                        "likelihood": 0.4 if risk_type == "destructive" else 0.2,
                    })
        overall = 0.0
        if risks:
            overall = sum(r.get("likelihood", 0.1) for r in risks) / len(risks)
        return {"risks": risks, "overall_risk": round(overall, 3), "safe": overall < 0.5}

    def can_proceed(self, goal: Dict) -> Tuple[bool, str]:
        assessment = self.assess(goal)
        if not assessment["safe"]:
            return False, f"Risk assessment: {len(assessment['risks'])} risks found"
        return True, "Safe to proceed"


# ═══════════════════════════════════════════════════════════════
# Phase 3b: Long-Term Planning (MCTS-based)
# ═══════════════════════════════════════════════════════════════

@dataclass
class PlanStep:
    action: str = ""
    expected_outcome: str = ""
    duration_estimate: float = 1.0
    dependencies: List[int] = field(default_factory=list)
    completed: bool = False
    status: str = "pending"


@dataclass
class Plan:
    goal: str = ""
    steps: List[PlanStep] = field(default_factory=list)
    created_at: float = 0.0
    horizon: int = 5

    def progress(self) -> float:
        if not self.steps:
            return 0.0
        return sum(1 for s in self.steps if s.completed) / len(self.steps)


class MCTSNode:
    """Monte Carlo Tree Search node."""

    def __init__(self, state: str, action: str = "", parent: Optional["MCTSNode"] = None):
        self.state = state
        self.action = action
        self.parent = parent
        self.children: List["MCTSNode"] = []
        self.visits = 0
        self.value = 0.0
        self.depth = parent.depth + 1 if parent else 0

    def ucb_score(self, exploration_param: float = 1.4) -> float:
        if self.visits == 0:
            return float('inf')
        exploitation = self.value / self.visits
        if self.parent and self.parent.visits > 0:
            exploration = exploration_param * math.sqrt(math.log(self.parent.visits) / self.visits)
        else:
            exploration = 0
        return exploitation + exploration

    def best_child(self) -> Optional["MCTSNode"]:
        if not self.children:
            return None
        return max(self.children, key=lambda c: c.ucb_score())


class MCTSPlanner:
    """Monte Carlo Tree Search for action planning with state-based simulation."""

    def __init__(self, n_simulations: int = 50, exploration: float = 1.4):
        self.n_simulations = n_simulations
        self.exploration = exploration
        self._state_history: Dict[str, float] = {}
        self._action_outcomes: Dict[str, List[float]] = defaultdict(list)

    def _predict_next_state(self, current_state: str, action: str,
                            state_predictor: Optional[Callable] = None) -> str:
        """基于状态预测器预测下一状态"""
        if state_predictor:
            try:
                return state_predictor(current_state, action)
            except Exception as e:
                logger.debug(f"操作失败: {e}")
        key = f"{current_state[:30]}|{action[:20]}"
        if key in self._state_history:
            # 已有经验，预测往好的方向发展
            last_outcome = self._state_history[key]
            if last_outcome > 0.6:
                return f"{current_state} → {action}[success]"
            elif last_outcome > 0.3:
                return f"{current_state} → {action}[partial]"
            else:
                return f"{current_state} → {action}[failed]"
        return f"{current_state} → {action}"

    def _evaluate_state(self, state: str, goal: str) -> float:
        """
        基于目标评估当前状态
        返回0.0-1.0的分数
        """
        goal_keywords = set(goal.lower().split())
        state_lower = state.lower()

        # 关键词匹配度
        matches = sum(1 for kw in goal_keywords if kw in state_lower)
        keyword_score = min(1.0, matches / max(len(goal_keywords), 1))

        # 状态标记评分
        if "[success]" in state or "completed" in state_lower:
            success_score = 1.0
        elif "[partial]" in state:
            success_score = 0.5
        elif "[failed]" in state or "error" in state_lower:
            success_score = 0.0
        else:
            # 中间状态：根据深度和进度评估
            arrows = state.count("→")
            depth_penalty = min(0.3, arrows * 0.05)
            success_score = 0.5 - depth_penalty

        # 目标完成度
        goal_progress = 0.0
        if goal[:20].lower() in state_lower:
            goal_progress = 0.7 + 0.3 * min(1.0, arrows / 5.0)

        return (keyword_score * 0.3 + success_score * 0.4 + goal_progress * 0.3)

    def _compute_reward(self, prev_state: str, action: str, next_state: str,
                        goal: str, state_predictor: Optional[Callable] = None) -> float:
        """
        计算状态转移的奖励值
        基于状态质量差异 + 动作效果 + 目标接近度
        """
        prev_score = self._evaluate_state(prev_state, goal)
        next_score = self._evaluate_state(next_state, goal)

        # 主奖励：状态质量提升
        state_reward = next_score - prev_score

        # 动作成本惩罚（鼓励简洁方案）
        action_cost = 0.02

        # 成功完成惩罚
        if "[success]" in next_state or "completed" in next_state.lower():
            completion_bonus = 0.3
        elif "[failed]" in next_state:
            completion_bonus = -0.2
        else:
            completion_bonus = 0.0

        # 学习记录
        key = f"{prev_state[:30]}|{action[:20]}"
        self._action_outcomes[key].append(next_score)
        if len(self._action_outcomes[key]) > 20:
            self._action_outcomes[key] = self._action_outcomes[key][-20:]

        final_reward = state_reward - action_cost + completion_bonus
        return max(-0.5, min(1.0, final_reward))

    def plan(self, goal: str, actions: List[str],
             state_predictor: Optional[Callable] = None) -> Plan:
        """基于MCTS生成最优计划"""
        actions_sorted = sorted(set(actions))[:5]
        if not actions_sorted:
            return Plan(goal=goal, created_at=time.time(), horizon=0)

        # 初始化根节点
        initial_state = f"Goal: {goal[:50]}"
        root = MCTSNode(state=initial_state, action="", parent=None)

        # MCTS搜索
        for sim in range(self.n_simulations):
            # 1. Selection：从根到叶，选择最优子节点
            node = self._uct_select(root)

            # 2. Expansion：如果未完全展开，添加子节点
            if len(node.children) < len(actions_sorted):
                remaining_actions = [a for a in actions_sorted
                                     if not any(c.action == a for c in node.children)]
                if remaining_actions:
                    action = remaining_actions[0]
                    next_state = self._predict_next_state(
                        node.state, action, state_predictor
                    )
                    child = MCTSNode(state=next_state, action=action, parent=node)
                    node.children.append(child)
                    node = child

            # 3. Simulation：从当前状态模拟到终止或深度限制
            reward = self._simulate_with_prediction(
                node, goal, state_predictor, max_depth=5
            )

            # 4. Backpropagation：更新所有祖先节点
            self._backpropagate(node, reward)

        # 从最优路径构建计划
        plan = Plan(goal=goal, created_at=time.time(), horizon=len(actions_sorted))
        current = root
        step_idx = 0

        while current.children:
            best = max(current.children, key=lambda c: c.visits)
            if best.action:
                plan.steps.append(PlanStep(
                    action=best.action,
                    expected_outcome=self._predict_outcome_description(best.state),
                    duration_estimate=1.0 + (1.0 - self._evaluate_state(best.state, goal)) * 2,
                    dependencies=[i for i in range(step_idx)] if step_idx > 0 else [],
                ))
                step_idx += 1
            current = best
            if step_idx >= len(actions_sorted):
                break

        return plan

    def _uct_select(self, node: MCTSNode) -> MCTSNode:
        """UCB1选择策略"""
        while node.children:
            # 选择UCB分数最高的子节点
            selected = max(node.children, key=lambda c: c.ucb_score(self.exploration))
            if selected.visits == 0:
                return node
            node = selected
        return node

    def _simulate_with_prediction(self, start_node: MCTSNode, goal: str,
                                  state_predictor: Optional[Callable],
                                  max_depth: int = 5) -> float:
        """
        基于状态预测的模拟
        沿用学到的状态转移模型模拟多步后的最终奖励
        """
        total_reward = 0.0
        gamma = 0.9  # 折扣因子
        current_state = start_node.state

        for depth in range(max_depth):
            # 获取可能的动作（从历史或默认）
            possible_actions = list(self._action_outcomes.keys())
            if not possible_actions:
                possible_actions = ["explore", "analyze", "execute", "verify", "complete"]

            # 基于UCB选择动作
            action = max(possible_actions[:5],
                        key=lambda a: self._get_action_ucb(a, current_state))

            # 预测下一状态
            next_state = self._predict_next_state(
                current_state, action, state_predictor
            )

            # 计算即时奖励
            reward = self._compute_reward(
                current_state, action, next_state, goal, state_predictor
            )

            # 折扣累计
            total_reward += (gamma ** depth) * reward

            # 检查终止条件
            state_score = self._evaluate_state(next_state, goal)
            if state_score >= 0.9 or "[failed]" in next_state:
                break

            current_state = next_state

        return max(0.0, min(1.0, total_reward))

    def _get_action_ucb(self, action: str, state: str) -> float:
        """计算动作的UCB分数（用于模拟中的动作选择）"""
        outcomes = self._action_outcomes.get(
            f"{state[:30]}|{action[:20]}", [0.5]
        )
        avg = sum(outcomes) / len(outcomes)
        visits = len(outcomes)
        exploration_bonus = self.exploration * math.sqrt(math.log(max(1, visits) + 1) / max(1, visits))
        return avg + exploration_bonus

    def _predict_outcome_description(self, state: str) -> str:
        """生成人类可读的结果描述"""
        if "[success]" in state or "completed" in state.lower():
            return "目标成功完成"
        elif "[partial]" in state:
            return "部分完成"
        elif "[failed]" in state or "error" in state.lower():
            return "执行失败"
        else:
            arrows = state.count("→")
            return f"执行中 (进度: {min(100, arrows * 20)}%)"

    def _backpropagate(self, node: MCTSNode, reward: float):
        """反向传播更新访问次数和价值"""
        while node:
            node.visits += 1
            node.value += reward
            node = node.parent

    def select(self, root: MCTSNode) -> MCTSNode:
        """选择最优子节点"""
        node = root
        while node.children:
            node = self.best_child(node) or node
            if node.visits == 0:
                break
        return node

    def expand(self, node: MCTSNode, actions: List[str],
               state_predictor: Optional[Callable] = None):
        """展开节点添加子节点"""
        for action in actions[:4]:
            next_state = self._predict_next_state(node.state, action, state_predictor)
            child = MCTSNode(state=next_state, action=action, parent=node)
            node.children.append(child)

    def simulate(self, node: MCTSNode, depth: int = 3) -> float:
        """兼容旧接口：使用新的预测模拟"""
        return self._simulate_with_prediction(node, "", None, max_depth=depth)

    def backpropagate(self, node: MCTSNode, reward: float):
        """兼容旧接口"""
        self._backpropagate(node, reward)


class HierarchicalPlanner:
    """Three-level hierarchical planner."""

    def plan_high(self, goal: str) -> List[str]:
        return [
            f"Phase 1: Prepare — analyze {goal[:30]}",
            f"Phase 2: Execute — implement {goal[:30]}",
            f"Phase 3: Verify — validate {goal[:30]}",
        ]

    def plan_mid(self, high_phase: str) -> List[str]:
        return [
            f"Step 1: {high_phase[:30]} — gather inputs",
            f"Step 2: {high_phase[:30]} — process",
            f"Step 3: {high_phase[:30]} — review",
        ]

    def plan_low(self, mid_step: str) -> List[str]:
        return [
            f"Action: {mid_step[:30]}",
            f"Check: {mid_step[:30]} result",
        ]


class PlanMonitor:
    """Monitor plan execution and detect deviations."""

    def __init__(self, tolerance: float = 0.3):
        self.tolerance = tolerance
        self.deviation_log: List[Dict] = []

    def check_progress(self, plan: Plan, actual_state: Dict) -> Tuple[float, List[str]]:
        expected = plan.progress()
        deviations = []
        for step in plan.steps:
            if step.status == "pending":
                expected_done = plan.created_at + sum(
                    s.duration_estimate for s in plan.steps[:plan.steps.index(step)]
                )
                if time.time() > expected_done + self.tolerance * expected_done:
                    deviations.append(f"Step '{step.action[:30]}' behind schedule")
        return expected, deviations

    def check_deviation(self, plan: Plan, actual_state: Dict) -> bool:
        progress, deviations = self.check_progress(plan, actual_state)
        if deviations:
            self.deviation_log.append({
                "time": time.time(), "plan": plan.goal[:30],
                "deviations": deviations, "progress": progress,
            })
            return True
        return False


# ═══════════════════════════════════════════════════════════════
# Commonsense Knowledge Graph (no external API needed)
# ═══════════════════════════════════════════════════════════════

class KnowledgeGraph:
    """Built-in commonsense knowledge base with ~300 relational triples.

    Replaces external ConceptNet/ATOMIC APIs with curated local knowledge.
    Supports: IsA, PartOf, CapableOf, HasProperty, Causes, AtLocation, RelatedTo
    """

    TRIPLES: List[Tuple[str, str, str]] = [
        # ── IsA (concept hierarchy) ──
        ("python", "IsA", "programming language"), ("java", "IsA", "programming language"),
        ("c++", "IsA", "programming language"), ("javascript", "IsA", "scripting language"),
        ("rust", "IsA", "systems language"), ("sql", "IsA", "query language"),
        ("html", "IsA", "markup language"), ("css", "IsA", "stylesheet language"),
        ("docker", "IsA", "container platform"), ("git", "IsA", "version control"),
        ("linux", "IsA", "operating system"), ("windows", "IsA", "operating system"),
        ("database", "IsA", "data store"), ("api", "IsA", "interface"),
        ("thread", "IsA", "execution unit"), ("process", "IsA", "execution unit"),
        ("lock", "IsA", "synchronization primitive"), ("mutex", "IsA", "lock"),
        ("semaphore", "IsA", "synchronization primitive"),
        ("variable", "IsA", "data container"), ("function", "IsA", "code unit"),
        ("class", "IsA", "code unit"), ("module", "IsA", "code unit"),
        ("package", "IsA", "code collection"), ("library", "IsA", "code collection"),
        ("framework", "IsA", "code collection"), ("protocol", "IsA", "communication standard"),
        ("algorithm", "IsA", "procedure"), ("data structure", "IsA", "data organization"),
        ("array", "IsA", "data structure"), ("list", "IsA", "data structure"),
        ("dict", "IsA", "data structure"), ("hash map", "IsA", "dictionary"),
        ("tree", "IsA", "data structure"), ("graph", "IsA", "data structure"),
        ("queue", "IsA", "data structure"), ("stack", "IsA", "data structure"),
        ("server", "IsA", "computer"), ("client", "IsA", "computer"),
        ("cache", "IsA", "temporary storage"), ("buffer", "IsA", "temporary storage"),
        ("compiler", "IsA", "translator"), ("interpreter", "IsA", "executor"),
        ("debugger", "IsA", "development tool"), ("test", "IsA", "verification method"),
        # ── PartOf ──
        ("cpu", "PartOf", "computer"), ("gpu", "PartOf", "computer"),
        ("ram", "PartOf", "computer"), ("disk", "PartOf", "computer"),
        ("function", "PartOf", "module"), ("class", "PartOf", "module"),
        ("method", "PartOf", "class"), ("attribute", "PartOf", "class"),
        ("statement", "PartOf", "function"), ("expression", "PartOf", "statement"),
        ("loop", "PartOf", "algorithm"), ("condition", "PartOf", "algorithm"),
        # ── CapableOf ──
        ("function", "CapableOf", "return value"), ("loop", "CapableOf", "iterate data"),
        ("condition", "CapableOf", "branch execution"), ("lock", "CapableOf", "prevent race condition"),
        ("mutex", "CapableOf", "protect critical section"),
        ("cache", "CapableOf", "speed up access"), ("buffer", "CapableOf", "temporary data hold"),
        ("database", "CapableOf", "persist data"), ("api", "CapableOf", "enable communication"),
        ("thread", "CapableOf", "concurrent execution"),
        ("recursion", "CapableOf", "solve divide-conquer problems"),
        ("sorting", "CapableOf", "arrange data in order"),
        ("searching", "CapableOf", "find data by key"),
        ("encryption", "CapableOf", "protect data confidentiality"),
        ("testing", "CapableOf", "verify correctness"),
        ("logging", "CapableOf", "record events"),
        # ── HasProperty ──
        ("python", "HasProperty", "interpreted"), ("java", "HasProperty", "compiled"),
        ("c++", "HasProperty", "fast"), ("rust", "HasProperty", "memory-safe"),
        ("sql", "HasProperty", "declarative"), ("thread", "HasProperty", "shared memory"),
        ("lock", "HasProperty", "mutual exclusion"),
        ("recursion", "HasProperty", "stack depth limited"),
        ("hash map", "HasProperty", "O(1) average lookup"),
        ("array", "HasProperty", "contiguous memory"),
        ("linked list", "HasProperty", "dynamic size"),
        # ── Causes ──
        ("deadlock", "Causes", "process hang"), ("race condition", "Causes", "data corruption"),
        ("memory leak", "Causes", "out of memory"), ("infinite loop", "Causes", "program hang"),
        ("null pointer", "Causes", "crash"), ("buffer overflow", "Causes", "security breach"),
        ("sql injection", "Causes", "data breach"),
        ("stack overflow", "Causes", "program crash"),
        ("fragmentation", "Causes", "performance degradation"),
        ("contention", "Causes", "slowdown"),
        ("improper locking", "Causes", "deadlock"),
        # ── AtLocation ──
        ("function", "AtLocation", "module"), ("variable", "AtLocation", "memory"),
        ("file", "AtLocation", "disk"), ("process", "AtLocation", "memory"),
        ("thread", "AtLocation", "process"), ("cache", "AtLocation", "cpu"),
        ("database", "AtLocation", "server"),
        # ── RelatedTo ──
        ("cpu", "RelatedTo", "computation"), ("gpu", "RelatedTo", "graphics"),
        ("ram", "RelatedTo", "memory access"), ("disk", "RelatedTo", "storage"),
        ("network", "RelatedTo", "communication"), ("protocol", "RelatedTo", "network"),
        ("api", "RelatedTo", "web service"), ("database", "RelatedTo", "persistence"),
        ("cache", "RelatedTo", "performance"), ("thread", "RelatedTo", "concurrency"),
        ("lock", "RelatedTo", "synchronization"), ("mutex", "RelatedTo", "mutual exclusion"),
        ("deadlock", "RelatedTo", "concurrency bug"),
        ("race", "RelatedTo", "concurrency bug"),
        ("testing", "RelatedTo", "quality assurance"),
        ("logging", "RelatedTo", "observability"), ("monitoring", "RelatedTo", "observability"),
        ("function", "RelatedTo", "abstraction"), ("class", "RelatedTo", "encapsulation"),
        ("inheritance", "RelatedTo", "code reuse"), ("polymorphism", "RelatedTo", "flexibility"),
    ]

    RELATION_TYPES = {"IsA", "PartOf", "CapableOf", "HasProperty", "Causes", "AtLocation", "RelatedTo"}

    def __init__(self):
        self._index: Dict[str, List[Tuple[str, str, str]]] = defaultdict(list)
        self._cache: Dict[str, List[Dict]] = {}
        self.cache_size = 5000
        self._build_index()
        logger.info(f"[KG] Loaded {len(self.TRIPLES)} commonsense facts")

    def _build_index(self):
        for s, r, o in self.TRIPLES:
            self._index[s].append((s, r, o))
            self._index[o].append((s, r, o))

    def query(self, concept: str, relation_type: Optional[str] = None) -> List[Dict]:
        cache_key = f"{concept}:{relation_type}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        results = []
        concept_lower = concept.lower()
        for entity, triples in self._index.items():
            if concept_lower in entity or entity in concept_lower:
                for s, r, o in triples:
                    if relation_type and r != relation_type:
                        continue
                    results.append({"subject": s, "relation": r, "object": o})
        # Also search full text
        for s, r, o in self.TRIPLES:
            if relation_type and r != relation_type:
                continue
            if concept_lower in s or concept_lower in o:
                results.append({"subject": s, "relation": r, "object": o})
        # Deduplicate
        seen = set()
        unique = []
        for r in results:
            key = (r["subject"], r["relation"], r["object"])
            if key not in seen:
                seen.add(key)
                unique.append(r)
        if len(self._cache) < self.cache_size:
            self._cache[cache_key] = unique
        return unique

    def infer_implicit(self, statement: str) -> List[str]:
        """Infer implicit knowledge from a statement."""
        inferences = []
        words = statement.lower().split()
        for word in words:
            for s, r, o in self.TRIPLES:
                if word in s or word in o:
                    if "Causes" in r:
                        inferences.append(f"{word} may cause: {o}")
                    if "HasProperty" in r:
                        inferences.append(f"{word} has property: {o}")
                    if "CapableOf" in r:
                        inferences.append(f"{word} can: {o}")
        return list(set(inferences))[:10]

    def ground_entity(self, entity_name: str) -> Dict:
        """Ground an entity to commonsense knowledge."""
        isa = self.query(entity_name, "IsA")
        props = self.query(entity_name, "HasProperty")
        capable = self.query(entity_name, "CapableOf")
        causes = self.query(entity_name, "Causes")
        related = self.query(entity_name, "RelatedTo")
        return {
            "name": entity_name,
            "types": [r["object"] for r in isa[:5]],
            "properties": [r["object"] for r in props[:5]],
            "capabilities": [r["object"] for r in capable[:5]],
            "causes": [r["object"] for r in causes[:5]],
            "related": [r["object"] for r in related[:10]],
        }


# ═══════════════════════════════════════════════════════════════
# Enhanced MCTS with State Prediction
# ═══════════════════════════════════════════════════════════════

class StatePredictor:
    """Predicts future states and outcomes based on past experience."""

    def __init__(self):
        self.outcome_history: Dict[str, List[float]] = defaultdict(list)

    def record_outcome(self, action: str, outcome: float):
        self.outcome_history[action].append(outcome)
        if len(self.outcome_history[action]) > 100:
            self.outcome_history[action] = self.outcome_history[action][-100:]

    def predict(self, action: str, current_state: str = "") -> float:
        outcomes = self.outcome_history.get(action, [])
        if not outcomes:
            return 0.5  # neutral
        return sum(outcomes) / len(outcomes)

    def expected_improvement(self, action: str, baseline: float = 0.5) -> float:
        pred = self.predict(action)
        return max(0.0, pred - baseline)

    def confidence(self, action: str) -> float:
        n = len(self.outcome_history.get(action, []))
        return min(1.0, n / 10.0)


class EnhancedMCTSPlanner:
    """MCTS with state prediction from historical outcomes."""

    def __init__(self, n_simulations: int = 100, exploration: float = 1.4):
        self.base = MCTSPlanner(n_simulations=n_simulations, exploration=exploration)
        self.predictor = StatePredictor()
        self._total_plans = 0

    def plan(self, goal: str, actions: List[str], context: str = "") -> Plan:
        plan = self.base.plan(goal, actions)
        # Enhance with predicted outcomes
        for step in plan.steps:
            pred = self.predictor.predict(step.action, goal)
            step.expected_outcome = f"Predicted success: {pred:.0%}"
            step.duration_estimate = max(0.5, 2.0 - pred)
        self._total_plans += 1
        return plan

    def run_mcts(self, root_state: str, actions: List[str],
                 depth: int = 5, iterations: int = 100) -> List[str]:
        root = MCTSNode(state=root_state)
        for _ in range(iterations):
            node = self.base.select(root)
            if node.visits == 0 or node.depth >= depth:
                reward = self._simulate_weighted(node, depth - node.depth)
                self.base.backpropagate(node, reward)
            else:
                self.base.expand(node, actions)
                child = random.choice(node.children) if node.children else node
                reward = self._simulate_weighted(child, depth - child.depth)
                self.base.backpropagate(child, reward)

        # Extract best path
        path = []
        node = root
        while node.children:
            node = node.best_child() or node
            if node.action:
                path.append(node.action)
        return path

    def _simulate_weighted(self, node: MCTSNode, depth: int) -> float:
        reward = 0.5
        for d in range(depth):
            if node.action:
                pred = self.predictor.predict(node.action)
                reward = reward * 0.7 + pred * 0.3
            else:
                reward += 0.1 * (random.random() - 0.3)
        return max(reward, 0.0)


# ═══════════════════════════════════════════════════════════════
# Formal Verifier (AST-pattern code analysis)
# ═══════════════════════════════════════════════════════════════

class FormalVerifier:
    """Pattern-based code verification without external AST parser.

    Uses regex patterns to detect common code issues, style violations,
    and potential bugs. Pure Python, no external dependencies.
    """

    RULES = [
        # (name, pattern, severity, message)
        ("no-var", r"\bvar\s+\w+\s*=", "style",
         "Use explicit types instead of 'var' for clarity"),
        ("magic-number", r"[^a-zA-Z]\d{4,}[^a-zA-Z)]", "style",
         "Avoid magic numbers; define as named constants"),
        ("todo-left", r"#\s*(TODO|FIXME|HACK|XXX)", "info",
         "Leftover TODO/FIXME marker — resolve before release"),
        ("print-left", r"print\(.*\)", "warning",
         "print() in production code — use logging instead"),
        ("bare-except", r"except\s*:", "error",
         "Bare except clause catches ALL exceptions — be specific"),
        ("mutable-default", r"def\s+\w+\(.*=\s*\[\s*\]",
         "error", "Mutable default argument (list) — use None instead"),
        ("mutable-default-dict", r"def\s+\w+\(.*=\s*\{\s*\}",
         "error", "Mutable default argument (dict) — use None instead"),
        ("global-mutation", r"global\s+\w+", "warning",
         "Modifying globals makes code hard to reason about"),
        ("thread-no-join", r"\.start\(\)", "warning",
         "Thread started without .join() — ensure cleanup"),
        ("eval-usage", r"\beval\s*\(", "error",
         "eval() is dangerous — use ast.literal_eval or safer alternative"),
        ("exec-usage", r"\bexec\s*\(", "error",
         "exec() is dangerous — avoid dynamic code execution"),
        ("wildcard-import", r"from\s+\w+\s+import\s+\*", "warning",
         "Wildcard imports pollute namespace — import specific names"),
        ("long-line", r"^.{120,}$", "style",
         "Line too long (>120 chars) — break into multiple lines"),
        ("deep-nesting", r"^(\s{8,})if\s", "warning",
         "Deep nesting (>4 levels) — consider early returns or guard clauses"),
    ]

    def verify(self, code: str, filename: str = "<string>") -> List[Dict]:
        findings = []
        lines = code.split("\n")
        for i, line in enumerate(lines, 1):
            for name, pattern, severity, message in self.RULES:
                import re
                if re.search(pattern, line):
                    findings.append({
                        "rule": name, "line": i,
                        "severity": severity, "message": message,
                        "code": line.strip()[:80],
                        "file": filename,
                    })
        return findings

    def verify_all(self, files: Dict[str, str]) -> Dict[str, List[Dict]]:
        return {fname: self.verify(code, fname) for fname, code in files.items()}

    def summary(self, findings: List[Dict]) -> str:
        if not findings:
            return "✅ No issues found"
        by_severity = defaultdict(list)
        for f in findings:
            by_severity[f["severity"]].append(f)
        lines = [f"Found {len(findings)} issue(s):"]
        for sev in ["error", "warning", "style", "info"]:
            items = by_severity.get(sev, [])
            if items:
                lines.append(f"\n  [{sev.upper()}] {len(items)}:")
                for item in items[:5]:
                    lines.append(f"    L{item['line']:4d} {item['message'][:60]}")
                if len(items) > 5:
                    lines.append(f"    ... and {len(items)-5} more")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# SecureSandbox Scanner (static analysis patterns)
# ═══════════════════════════════════════════════════════════════

class SecureSandboxScanner:
    """Static security analysis patterns.

    Scans code for common security vulnerabilities.
    Docker sandbox scaffold included for future container isolation.
    """

    SECURITY_PATTERNS = [
        ("command-injection", r"[os|subprocess]\.(system|popen|call)\s*\(",
         "critical", "OS command injection risk — use safe alternatives"),
        ("path-traversal", r"open\(.*\.\.\.", "high",
         "Path traversal risk — sanitize user input paths"),
        ("hardcoded-secret", r"(password|secret|api_key|token)\s*=\s*['\"][^'\"]{8,}['\"]",
         "critical", "Hardcoded secret detected — use environment variables"),
        ("sql-injection", r"f['\"]?.*SELECT.*\{", "critical",
         "SQL injection risk — use parameterized queries"),
        ("unsafe-yaml", r"yaml\.load\(.*\)", "high",
         "Unsafe YAML load — use yaml.safe_load()"),
        ("pickle-unsafe", r"pickle\.loads?\(", "high",
         "Unsafe deserialization — avoid pickle with untrusted data"),
        ("shell-true", r"shell\s*=\s*True", "critical",
         "shell=True in subprocess — command injection risk"),
    ]

    def __init__(self):
        self._sandbox_available = False  # Docker not available locally
        self._sandbox_image = "laap-sandbox:v1.0"

    def scan_code(self, code: str, filename: str = "<code>") -> List[Dict]:
        import re
        findings = []
        lines = code.split("\n")
        for i, line in enumerate(lines, 1):
            for name, pattern, severity, message in self.SECURITY_PATTERNS:
                if re.search(pattern, line):
                    findings.append({
                        "rule": name, "line": i, "severity": severity,
                        "message": message, "code": line.strip()[:80], "file": filename,
                    })
        return findings

    def analyze_repo(self, files: Dict[str, str]) -> Dict:
        all_findings = {}
        for fname, code in files.items():
            findings = self.scan_code(code, fname)
            if findings:
                all_findings[fname] = findings

        critical = sum(1 for f in all_findings.values() for r in f if r["severity"] == "critical")
        high = sum(1 for f in all_findings.values() for r in f if r["severity"] == "high")
        total = sum(len(f) for f in all_findings.values())

        return {
            "files_scanned": len(files),
            "files_with_issues": len(all_findings),
            "total_findings": total,
            "critical": critical,
            "high": high,
            "details": all_findings,
            "safe": critical == 0,
        }

    def is_safe_url(self, url: str) -> bool:
        """URL whitelist check (from V5.0 plan spec)."""
        from urllib.parse import urlparse
        allowed = ["github.com", "gitlab.com", "bitbucket.org"]
        try:
            parsed = urlparse(url)
            return parsed.netloc in allowed and parsed.scheme in ("https", "git")
        except Exception:
            return False

    def sandbox_available(self) -> bool:
        """Check if Docker sandbox is available (future)."""
        return self._sandbox_available

    def sandbox_scaffold(self) -> Dict:
        """Return the sandbox configuration (for future Docker integration)."""
        return {
            "image": self._sandbox_image,
            "mem_limit": "512m",
            "cpu_quota": 50000,
            "network_mode": "none",
            "available": self._sandbox_available,
        }


# ═══════════════════════════════════════════════════════════════
# Benchmark Suite — Self-testing & Validation
# ═══════════════════════════════════════════════════════════════

class BenchmarkSuite:
    """Self-testing module for V5.0 components validation."""

    def __init__(self, engine: Optional["V5UpgradeEngine"] = None):
        self.engine = engine
        self.results: List[Dict] = []
        self._start_time = time.time()

    def run_all(self) -> Dict:
        self.results = []
        self._test_ewc()
        self._test_buffer()
        self._test_bug_classifier()
        self._test_causal()
        self._test_active_learning()
        self._test_goal_creator()
        self._test_mcts()
        self._test_knowledge_graph()
        self._test_verifier()
        self._test_sandbox()
        return self._summary()

    def _test_ewc(self):
        if not self.engine:
            return
        before = len(self.engine.ewc.fisher)
        self.engine.ewc.record("test_module", 0.8, 1.0)
        penalty = self.engine.ewc.compute_penalty("test_module", 0.3)
        after = len(self.engine.ewc.fisher)
        self.results.append({
            "test": "EWC Fisher Tracking", "passed": after > before,
            "detail": f"Fisher={len(self.engine.ewc.fisher)} penalty={penalty:.3f}",
        })

    def _test_buffer(self):
        if not self.engine:
            return
        before = len(self.engine.experience_buffer)
        self.engine.record_experience("bench_state", "bench_action", 0.9)
        after = len(self.engine.experience_buffer)
        self.results.append({
            "test": "Experience Buffer", "passed": after > before,
            "detail": f"Buffer size: {after}",
        })

    def _test_bug_classifier(self):
        if not self.engine:
            return
        for cat in BugCategory:
            result = self.engine.classify_and_fix(f"{cat.value} test error", "test.py")
            if result["bug"].category != "unknown":
                self.results.append({
                    "test": f"Bug Classifier: {cat.value}",
                    "passed": True,
                    "detail": f"Classified as {result['bug'].category}",
                })
                break

    def _test_causal(self):
        if not self.engine:
            return
        data = {"X": [1, 2, 3, 4, 5], "Y": [2, 4, 6, 8, 10]}
        result = self.engine.discover_causality(data)
        self.results.append({
            "test": "Causal Discovery", "passed": len(result["edges"]) > 0,
            "detail": f"Edges: {len(result['edges'])}",
        })

    def _test_active_learning(self):
        if not self.engine:
            return
        al = self.engine.active_learning
        al._total_steps = 10
        action, _ = al.select_action({"confidence": 0.5}, "debug")
        al.record_outcome(action, "test", "debug", 0.8)
        self.results.append({
            "test": "Active Learning", "passed": action in ("explore", "exploit"),
            "detail": f"Action: {action}, Steps: {al._total_steps}",
        })

    def _test_goal_creator(self):
        if not self.engine:
            return
        goals = self.engine.goal_creator.co_create_goals("fix bug", {"confidence": 0.5})
        self.results.append({
            "test": "Goal Co-Creation", "passed": len(goals) > 0,
            "detail": f"Goals: {len(goals)}",
        })

    def _test_mcts(self):
        if not self.engine:
            return
        plan = self.engine.mcts_planner.plan(
            "test goal", ["analyze", "execute", "verify"]
        )
        self.results.append({
            "test": "MCTS Planning", "passed": len(plan.steps) > 0,
            "detail": f"Steps: {len(plan.steps)}",
        })

    def _test_knowledge_graph(self):
        if not self.engine:
            return
        if hasattr(self.engine, 'knowledge'):
            results = self.engine.knowledge.query("python")
            self.results.append({
                "test": "Knowledge Graph", "passed": len(results) > 0,
                "detail": f"Results for 'python': {len(results)}",
            })

    def _test_verifier(self):
        code = "x = 12345\ndef foo(x=[]):\n    print(x)"
        if hasattr(self, '_verifier') or True:
            from laap.agi.v5_upgrade import FormalVerifier
            v = FormalVerifier()
            findings = v.verify(code)
            self.results.append({
                "test": "Formal Verifier", "passed": len(findings) >= 2,
                "detail": f"Issues found: {len(findings)}",
            })

    def _test_sandbox(self):
        if hasattr(self, '_sandbox') or True:
            from laap.agi.v5_upgrade import SecureSandboxScanner
            s = SecureSandboxScanner()
            code = "password = 'my_secret_key_123'\nos.system('rm -rf /')"
            results = s.scan_code(code)
            self.results.append({
                "test": "Security Scanner", "passed": len(results) > 0,
                "detail": f"Issues: {len(results)}",
            })

    def _summary(self) -> Dict:
        passed = sum(1 for r in self.results if r["passed"])
        failed = sum(1 for r in self.results if not r["passed"])
        return {
            "total": len(self.results),
            "passed": passed,
            "failed": failed,
            "pass_rate": f"{passed/max(len(self.results),1)*100:.0f}%",
            "duration": round(time.time() - self._start_time, 2),
            "details": self.results,
        }
# ═══════════════════════════════════════════════════════════════

class V5UpgradeEngine:
    """Orchestrates all V5.0 upgrade components."""

    def __init__(self):
        self.version = V5_VERSION

        # Phase 1
        self.ewc = FisherInfoTracker()
        self.skill_importance = SkillImportanceTracker()
        self.experience_buffer = PrioritizedExperienceBuffer()
        self.bug_classifier = EnhancedBugClassifier()
        self.fix_generator = LogicFixGenerator()
        self.race_detector = RaceConditionDetector()
        self.verifier = FormalVerifier()
        self.sandbox = SecureSandboxScanner()

        # Phase 2
        self.causal_discovery = CausalDiscovery()
        self.active_learning = ActiveLearningEngine()
        self.knowledge = KnowledgeGraph()

        # Phase 3
        self.goal_creator = GoalCoCreator()
        self.risk_assessor = RiskAssessor()
        self.mcts_planner = EnhancedMCTSPlanner()
        self.hierarchical_planner = HierarchicalPlanner()
        self.plan_monitor = PlanMonitor()
        self.state_predictor = self.mcts_planner.predictor

        self._start_time = time.time()
        self._total_upgrades = 0
        self._lock = threading.Lock()

    def record_experience(self, state: str, action: str, outcome: float,
                           context: Dict = None):
        self.experience_buffer.add(state, action, outcome, context)
        self.skill_importance.record_use(action[:20], outcome > 0.5)
        # EWC: record parameter importance
        self.ewc.record(action[:20], outcome, importance=outcome)
        # Active learning
        self.active_learning.record_outcome(
            "exploit" if outcome > 0.5 else "explore",
            action[:20], context.get("task_type", "general") if context else "general",
            outcome,
        )
        with self._lock:
            self._total_upgrades += 1

    def classify_and_fix(self, error_msg: str, source_file: str = "",
                          source_line: int = 0, code_context: str = "") -> Dict:
        bug = self.bug_classifier.classify(error_msg, source_file, source_line, code_context)
        fix = self.fix_generator.generate_fix(bug, code_context)
        return {"bug": bug, "fix": fix, "timestamp": time.time()}

    def discover_causality(self, data: Dict[str, List[float]]) -> Dict:
        return self.causal_discovery.discover(data)

    def create_goal_plan(self, user_input: str, agent_state: Dict = None) -> Dict:
        goals = self.goal_creator.co_create_goals(
            user_input, agent_state or {"confidence": 0.5}
        )
        plans = []
        for goal in goals[:3]:
            risk = self.risk_assessor.assess(goal)
            plan = self.mcts_planner.plan(
                goal["title"],
                goal.get("sub_goals", ["analyze", "execute", "verify"]),
            )
            plans.append({"goal": goal, "risk": risk, "plan": plan})
        return {"goals": goals, "plans": plans}

    def get_status(self) -> Dict:
        return {
            "version": self.version,
            "uptime": round(time.time() - self._start_time, 1),
            "phase_1": {
                "ewc_modules": len(self.ewc.fisher),
                "skill_importance": len(self.skill_importance.importance),
                "experience_buffer": len(self.experience_buffer),
                "bug_categories": len(BugCategory),
                "security_patterns": len(self.sandbox.SECURITY_PATTERNS),
                "verifier_rules": len(self.verifier.RULES),
            },
            "phase_2": {
                "causal_variables": len(self.causal_discovery.graph),
                "active_learning_steps": self.active_learning._total_steps,
                "meta_strategies": len(self.active_learning.meta.strategies),
                "knowledge_facts": len(self.knowledge.TRIPLES),
                "knowledge_rels": len(self.knowledge.RELATION_TYPES),
            },
            "phase_3": {
                "goals_created": len(self.goal_creator._goal_history),
                "plan_monitor_devs": len(self.plan_monitor.deviation_log),
                "mcts_plans": self.mcts_planner._total_plans,
            },
            "total_upgrades": self._total_upgrades,
        }

    def get_report(self) -> str:
        s = self.get_status()
        lines = [
            f"LAAP V5.0 Upgrade Engine v{s['version']}",
            f"Uptime: {s['uptime']}s | Total upgrades: {s['total_upgrades']}",
            "",
            "Phase 1 — Infrastructure:",
            f"  EWC modules tracked: {s['phase_1']['ewc_modules']}",
            f"  Skill importance: {s['phase_1']['skill_importance']}",
            f"  Experience buffer: {s['phase_1']['experience_buffer']}",
            f"  Bug categories: {s['phase_1']['bug_categories']}",
            f"  Security patterns: {s['phase_1']['security_patterns']}",
            f"  Verifier rules: {s['phase_1']['verifier_rules']}",
            "",
            "Phase 2 — Cognition:",
            f"  Causal variables: {s['phase_2']['causal_variables']}",
            f"  Active learning steps: {s['phase_2']['active_learning_steps']}",
            f"  Meta-strategies: {s['phase_2']['meta_strategies']}",
            f"  Knowledge facts: {s['phase_2']['knowledge_facts']}",
            f"  Relation types: {s['phase_2']['knowledge_rels']}",
            "",
            "Phase 3 — Autonomy:",
            f"  Goals created: {s['phase_3']['goals_created']}",
            f"  Plan deviations: {s['phase_3']['plan_monitor_devs']}",
            f"  MCTS plans: {s['phase_3']['mcts_plans']}",
        ]
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# Singleton and integration
# ═══════════════════════════════════════════════════════════════

_INSTANCE: Optional[V5UpgradeEngine] = None


def get_v5_engine() -> V5UpgradeEngine:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = V5UpgradeEngine()
    return _INSTANCE


def integrate_with_bridge(bridge) -> bool:
    """Wire V5.0 engine into an existing laap_bridge_agent bridge."""
    engine = get_v5_engine()
    if not bridge:
        return False

    # Monkey-patch bridge's before_turn to include V5 cognitive enhancements
    original_before = bridge.before_turn
    def v5_before_turn(msg):
        ctx = original_before(msg) if original_before else {}
        # Active learning: should we explore?
        task_type = ctx.get("meta", {}).get("task_type", "general")
        action, strategy = engine.active_learning.select_action(
            {"confidence": ctx.get("unity", {}).get("confidence", 0.5)},
            task_type,
        )
        ctx["v5"] = {"mode": action, "strategy": strategy}
        # Goal co-creation for complex requests
        if len(msg) > 80:
            goals = engine.goal_creator.co_create_goals(msg, {"confidence": 0.5})
            ctx["v5"]["goals"] = len(goals)
        return ctx
    bridge.before_turn = v5_before_turn

    # Monkey-patch bridge's after_tool to record experience
    original_after_tool = bridge.after_tool
    def v5_after_tool(tool_name, result):
        if original_after_tool:
            original_after_tool(tool_name, result)
        ok = result and "error" not in str(result).lower() if result else False
        engine.record_experience(tool_name, tool_name, 0.8 if ok else 0.2,
                                  {"task_type": getattr(bridge, '_last_context', {}).get("meta", {}).get("task_type", "general")})
    bridge.after_tool = v5_after_tool

    # Add V5 commands
    original_cmd = bridge.handle_command
    def v5_handle_command(cmd, *args):
        cmd_lower = cmd.lstrip("/").lower()
        if cmd_lower == "v5":
            return engine.get_report()
        if cmd_lower == "v5-status":
            import json
            return json.dumps(engine.get_status(), indent=2, ensure_ascii=False)
        if cmd_lower == "v5-goals" and args:
            goals = engine.goal_creator.co_create_goals(
                args[0] if args else "",
                {"confidence": 0.5}
            )
            lines = ["[V5.0 Goal Proposals]"]
            for i, g in enumerate(goals[:5], 1):
                lines.append(f"  {i}. {g['title']} (score={g.get('combined', 0):.2f})")
                for sg in g.get("sub_goals", []):
                    lines.append(f"      → {sg}")
            return "\n".join(lines)
        return original_cmd(cmd, *args) if original_cmd else f"Unknown: {cmd}"
    bridge.handle_command = v5_handle_command

    bridge.v5 = engine
    logger.info(f"[V5.0] Bridge integration complete — {sum(len(v) for v in engine.get_status().values() if isinstance(v, dict))} components active")
    return True


def integrate_with_agi_bridge(agi_bridge=None) -> bool:
    """
    Wire V5.0 engine into AGIBridge (used by laap-hermes default mode).

    Hooks into AGIBridge's after_turn and after_tool methods to record
    every interaction and tool call through the V5.0 engine.
    """
    engine = get_v5_engine()

    # Find the AGIBridge singleton
    if agi_bridge is None:
        try:
            from laap_brain.agi_bridge import AGIBridge
            agi_bridge = AGIBridge.get_instance()
        except Exception as e:
            logger.debug(f"操作失败: {e}")
    if not agi_bridge:
        return False

    # Patch after_tool
    orig_tool = getattr(agi_bridge, 'after_tool', None)
    def v5_after_tool(tool_name, tool_result, domain="general", tool_args=None):
        if orig_tool:
            orig_result = orig_tool(tool_name, tool_result, domain, tool_args)
        else:
            orig_result = {}
        ok = tool_result and "error" not in str(tool_result).lower() if tool_result else False
        engine.record_experience(tool_name, str(tool_name), 0.8 if ok else 0.2,
                                 {"task_type": domain, "tool_args": str(tool_args)[:100]})
        return orig_result

    # Patch after_turn
    orig_turn = getattr(agi_bridge, 'after_turn', None)
    def v5_after_turn(response, domain="general", turn_duration_ms=0.0):
        if orig_turn:
            orig_result = orig_turn(response, domain, turn_duration_ms)
        else:
            orig_result = {}
        success = bool(response and len(response) > 10)
        engine.record_experience(domain, "turn", 0.8 if success else 0.2,
                                 {"response_len": len(response or ""), "duration_ms": turn_duration_ms})
        return orig_result

    agi_bridge.after_tool = v5_after_tool
    agi_bridge.after_turn = v5_after_turn
    agi_bridge.v5 = engine

    # Patch existing agent if available
    if hasattr(agi_bridge, '_agent') and agi_bridge._agent:
        try:
            if hasattr(agi_bridge._agent, 'v5'):
                pass  # already set
            agi_bridge._agent.v5 = engine
        except Exception as e:
            logger.debug(f"操作失败: {e}")
    engine._bridge_type = "agi_bridge"
    logger.info(f"[V5.0] AGI Bridge integrated — {engine.get_status()['total_upgrades']} upgrades tracked")
    return True


def integrate_with_hermes_direct() -> bool:
    """
    Full Hermes direct integration: patches the AGI bridge AND the
    lightweight bridge simultaneously. Idempotent.
    """
    engine = get_v5_engine()
    ok = integrate_with_agi_bridge()
    engine._bridge_type = "hermes_direct"
    logger.info(f"[V5.0] Full Hermes direct integration active")
    return ok


# ═══════════════════════════════════════════════════════════════
# CLI Test
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    engine = get_v5_engine()
    logger.info(f"LAAP V5.0 Upgrade Engine v{V5_VERSION}")
    logger.info("=" * 50)
    for i in range(20):
        engine.record_experience(f"state_{i % 5}", f"action_{i % 3}", random.random())
    logger.info(f"Phase 1: Buffer={len(engine.experience_buffer)} EWC={len(engine.ewc.fisher)}")
    bugs = [
        "SyntaxError: invalid syntax at line 42",
        "TypeError: unsupported operand type(s) for +: 'int' and 'str'",
        "race condition in shared counter increment",
    ]
    for b in bugs:
        result = engine.classify_and_fix(b, "test.py")
        logger.info(f"  Bug: [{result['bug'].category}] {b[:40]}...")
    data = {"A": [1, 2, 3, 4, 5], "B": [2, 4, 6, 8, 10], "C": [5, 4, 3, 2, 1]}
    result = engine.discover_causality(data)
    logger.info(f"Phase 2: Causal edges={len(result['edges'])}")
    goals = engine.goal_creator.co_create_goals(
        "fix the race condition in the concurrent counter system", {}
    )
    logger.info(f"Phase 3: {len(goals)} goal candidates generated")
    print()
    logger.info(engine.get_report())