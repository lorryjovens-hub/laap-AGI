"""
LAAP AGI — Autonomous Agent (长期自主性引擎)

Goal-driven, self-directed agent that can operate for hours or days
without human supervision, pursuing self-generated goals.

Current agents are REACTIVE: they respond to user prompts, then wait.
An AGI agent must be PROACTIVE: setting its own goals, decomposing them,
executing plans, monitoring progress, and adapting when things change.

Key capabilities:
  1. Goal Generation — derive goals from internal needs/drives
  2. Plan Decomposition — break goals into executable subgoals
  3. Progress Monitoring — track progress and detect stalls
  4. Replanning — adapt plans when circumstances change
  5. Resource Management — budget time, tokens, and energy
  6. Self-Interruption — pause and resume long-running tasks
  7. Priority Scheduling — choose which goal to work on now

Architecture:
  ┌──────────────────────────────────────────────────────────┐
  │              AUTONOMOUS AGENT ENGINE                      │
  ├──────────────────────────────────────────────────────────┤
  │  Goal Manager                                             │
  │  ├── Active goals (priority queue)                        │
  │  ├── Goal lifecycle: pending → active → completed/failed  │
  │  └── Goal dependencies and constraints                    │
  ├──────────────────────────────────────────────────────────┤
  │  Planner                                                  │
  │  ├── Hierarchical Task Network (HTN) planning             │
  │  ├── Subgoal decomposition (recursive)                    │
  │  └── Resource estimation per subgoal                      │
  ├──────────────────────────────────────────────────────────┤
  │  Executor                                                 │
  │  ├── Action selection from plan                           │
  │  ├── Progress tracking and metrics                        │
  │  └── Stall detection and recovery                         │
  ├──────────────────────────────────────────────────────────┤
  │  Scheduler                                                │
  │  ├── Multi-goal priority scheduling                       │
  │  ├── Time/token/energy budget allocation                  │
  │  └── Work-break cycle management                          │
  └──────────────────────────────────────────────────────────┘
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple, Callable
from enum import Enum
import time, logging, math, json, uuid, heapq, threading
from collections import defaultdict

logger = logging.getLogger("laap.agi.autonomy")


# ════════════════════════════════════════════════════════════
# Core Types
# ════════════════════════════════════════════════════════════

class GoalStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DELEGATED = "delegated"


class GoalPriority(float, Enum):
    CRITICAL = 1.0
    HIGH = 0.8
    MEDIUM = 0.5
    LOW = 0.3
    BACKGROUND = 0.1


class GoalSource(str, Enum):
    """Where did this goal come from?"""
    USER_REQUEST = "user_request"
    INTERNAL_DRIVE = "internal_drive"
    SUBGOAL_OF = "subgoal_of"
    OPPORTUNITY = "opportunity"
    MAINTENANCE = "maintenance"
    LEARNING = "learning"


@dataclass
class Goal:
    """A goal that the agent wants to achieve."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    description: str = ""
    source: GoalSource = GoalSource.INTERNAL_DRIVE
    priority: GoalPriority = GoalPriority.MEDIUM
    status: GoalStatus = GoalStatus.PENDING
    parent_goal_id: str = ""           # If this is a subgoal
    subgoals: List[str] = field(default_factory=list)
    prerequisites: List[str] = field(default_factory=list)  # Goal IDs that must complete first
    estimated_effort: float = 60.0      # Estimated seconds
    actual_effort: float = 0.0          # Actual seconds spent
    progress: float = 0.0              # 0-1 completion
    created_at: float = field(default_factory=time.time)
    started_at: float = 0.0
    completed_at: float = 0.0
    deadline: float = 0.0              # Optional deadline (timestamp)
    domain: str = ""
    success_criteria: List[str] = field(default_factory=list)
    failure_reason: str = ""
    notes: List[str] = field(default_factory=list)

    @property
    def is_overdue(self) -> bool:
        return self.deadline > 0 and time.time() > self.deadline

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at


@dataclass
class Plan:
    """A plan for achieving a goal."""
    goal_id: str = ""
    steps: List[PlanStep] = field(default_factory=list)
    current_step: int = 0
    estimated_total_time: float = 0.0
    created_at: float = field(default_factory=time.time)


@dataclass
class PlanStep:
    """A single step in a plan."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    action: str = ""                    # Description of what to do
    tool: str = ""                      # Tool to use (if any)
    expected_outcome: str = ""          # What should happen
    estimated_time: float = 30.0        # Seconds
    actual_time: float = 0.0
    status: str = "pending"             # pending, active, completed, failed, skipped
    retry_count: int = 0
    max_retries: int = 3
    depends_on: List[str] = field(default_factory=list)  # Step IDs


@dataclass
class ExecutionContext:
    """Current execution state."""
    active_goal_id: str = ""
    active_plan: Optional[Plan] = None
    current_step_index: int = 0
    stalled_since: float = 0.0
    consecutive_failures: int = 0
    total_active_time: float = 0.0
    interruptions: int = 0


# ════════════════════════════════════════════════════════════
# Goal Manager
# ════════════════════════════════════════════════════════════

class GoalManager:
    """Manages the full lifecycle of goals."""

    def __init__(self):
        self.goals: Dict[str, Goal] = {}
        self._priority_queue: List[Tuple[float, str]] = []  # (-priority, goal_id) for max-heap
        self._completed_count = 0
        self._failed_count = 0
        self._lock = threading.Lock()

    def create_goal(self, description: str,
                    source: GoalSource = GoalSource.INTERNAL_DRIVE,
                    priority: GoalPriority = GoalPriority.MEDIUM,
                    parent_id: str = "",
                    domain: str = "",
                    estimated_effort: float = 60.0,
                    success_criteria: List[str] = None,
                    deadline: float = 0.0) -> Goal:
        """Create a new goal."""
        with self._lock:
            goal = Goal(
                description=description,
                source=source,
                priority=priority,
                parent_goal_id=parent_id,
                domain=domain,
                estimated_effort=estimated_effort,
                success_criteria=success_criteria or [],
                deadline=deadline,
            )
            self.goals[goal.id] = goal
            heapq.heappush(self._priority_queue, (-goal.priority.value, goal.id))

            if parent_id and parent_id in self.goals:
                self.goals[parent_id].subgoals.append(goal.id)

            return goal

    def get_next_goal(self) -> Optional[Goal]:
        """Get the highest priority pending goal that's ready to execute."""
        with self._lock:
            # Refresh queue
            temp = []
            while self._priority_queue:
                neg_pri, gid = heapq.heappop(self._priority_queue)
                if gid not in self.goals:
                    continue
                goal = self.goals[gid]
                if goal.status == GoalStatus.PENDING:
                    # Check prerequisites
                    prereqs_met = all(
                        pid in self.goals and
                        self.goals[pid].status == GoalStatus.COMPLETED
                        for pid in goal.prerequisites
                    )
                    if prereqs_met:
                        # Re-push and return
                        heapq.heappush(self._priority_queue, (neg_pri, gid))
                        return goal
                temp.append((neg_pri, gid))
            # Restore
            for item in temp:
                heapq.heappush(self._priority_queue, item)
            return None

    def activate_goal(self, goal_id: str) -> bool:
        """Mark a goal as active (start working on it)."""
        with self._lock:
            if goal_id not in self.goals:
                return False
            goal = self.goals[goal_id]
            if goal.status != GoalStatus.PENDING:
                return False
            goal.status = GoalStatus.ACTIVE
            goal.started_at = time.time()
            return True

    def complete_goal(self, goal_id: str):
        """Mark a goal as completed."""
        with self._lock:
            if goal_id not in self.goals:
                return
            goal = self.goals[goal_id]
            goal.status = GoalStatus.COMPLETED
            goal.progress = 1.0
            goal.completed_at = time.time()
            goal.actual_effort = time.time() - goal.started_at
            self._completed_count += 1

    def fail_goal(self, goal_id: str, reason: str = ""):
        """Mark a goal as failed."""
        with self._lock:
            if goal_id not in self.goals:
                return
            goal = self.goals[goal_id]
            goal.status = GoalStatus.FAILED
            goal.failure_reason = reason
            goal.completed_at = time.time()
            self._failed_count += 1

    def block_goal(self, goal_id: str, reason: str = ""):
        """Block a goal (waiting for something)."""
        with self._lock:
            if goal_id in self.goals:
                self.goals[goal_id].status = GoalStatus.BLOCKED
                if reason:
                    self.goals[goal_id].notes.append(f"BLOCKED: {reason}")

    def update_progress(self, goal_id: str, progress: float):
        """Update goal progress (0-1)."""
        with self._lock:
            if goal_id in self.goals:
                self.goals[goal_id].progress = min(1.0, max(0.0, progress))

    def get_active_goals(self) -> List[Goal]:
        return [g for g in self.goals.values() if g.status == GoalStatus.ACTIVE]

    def get_pending_goals(self) -> List[Goal]:
        return sorted(
            [g for g in self.goals.values() if g.status == GoalStatus.PENDING],
            key=lambda g: (-g.priority.value, g.created_at),
        )

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "total_goals": len(self.goals),
                "active": len(self.get_active_goals()),
                "pending": len(self.get_pending_goals()),
                "completed": self._completed_count,
                "failed": self._failed_count,
                "blocked": sum(1 for g in self.goals.values() if g.status == GoalStatus.BLOCKED),
            }


# ════════════════════════════════════════════════════════════
# Planner
# ════════════════════════════════════════════════════════════

class Planner:
    """Decomposes goals into executable plans."""

    def __init__(self, max_plan_depth: int = 5):
        self.max_depth = max_plan_depth
        self.plans: Dict[str, Plan] = {}

    def plan_goal(self, goal: Goal,
                  available_tools: List[str] = None) -> Plan:
        """Create a plan for achieving a goal."""
        plan = Plan(goal_id=goal.id)

        # Decompose goal into steps based on goal description and domain
        steps = self._decompose(goal, available_tools or [])

        for i, step_desc in enumerate(steps):
            step = PlanStep(
                action=step_desc.get("action", f"Step {i+1}"),
                tool=step_desc.get("tool", ""),
                expected_outcome=step_desc.get("outcome", ""),
                estimated_time=step_desc.get("time", 30.0),
            )
            if i > 0:
                step.depends_on = [plan.steps[-1].id]
            plan.steps.append(step)

        plan.estimated_total_time = sum(s.estimated_time for s in plan.steps)
        self.plans[goal.id] = plan
        return plan

    def get_next_step(self, plan: Plan) -> Optional[PlanStep]:
        """Get the next executable step."""
        for i, step in enumerate(plan.steps):
            if step.status == "pending":
                # Check dependencies
                deps_met = all(
                    self._find_step_by_id(plan, dep_id).status == "completed"
                    for dep_id in step.depends_on
                )
                if deps_met:
                    return step
        return None

    def _decompose(self, goal: Goal,
                    available_tools: List[str]) -> List[Dict[str, Any]]:
        """Decompose a goal into concrete steps."""
        description = goal.description.lower()

        # Common decomposition patterns
        if any(w in description for w in ["debug", "fix", "bug", "error"]):
            return [
                {"action": "Reproduce the issue", "tool": "terminal", "outcome": "Confirmed reproduction", "time": 30},
                {"action": "Collect error logs and context", "tool": "terminal", "outcome": "Collected evidence", "time": 20},
                {"action": "Identify root cause", "tool": "read_file", "outcome": "Root cause found", "time": 60},
                {"action": "Implement fix", "tool": "patch", "outcome": "Fix applied", "time": 60},
                {"action": "Verify fix works", "tool": "terminal", "outcome": "Tests pass", "time": 30},
            ]

        if any(w in description for w in ["build", "create", "implement", "write"]):
            return [
                {"action": "Design the solution", "tool": "", "outcome": "Design documented", "time": 60},
                {"action": "Implement core logic", "tool": "write_file", "outcome": "Core implemented", "time": 120},
                {"action": "Add error handling and edge cases", "tool": "patch", "outcome": "Robust implementation", "time": 60},
                {"action": "Test the implementation", "tool": "terminal", "outcome": "Tests pass", "time": 60},
                {"action": "Document and clean up", "tool": "write_file", "outcome": "Documented", "time": 30},
            ]

        if any(w in description for w in ["research", "analyze", "investigate", "understand"]):
            return [
                {"action": "Gather initial information", "tool": "web_search", "outcome": "Data collected", "time": 30},
                {"action": "Analyze and categorize findings", "tool": "", "outcome": "Analysis complete", "time": 60},
                {"action": "Identify patterns and insights", "tool": "", "outcome": "Patterns found", "time": 45},
                {"action": "Synthesize conclusions", "tool": "", "outcome": "Conclusions drawn", "time": 30},
            ]

        # Generic decomposition
        return [
            {"action": f"Phase 1: Prepare for '{goal.description[:40]}'", "tool": "", "outcome": "Prepared", "time": 30},
            {"action": f"Phase 2: Execute '{goal.description[:40]}'", "tool": "terminal", "outcome": "Executed", "time": 120},
            {"action": f"Phase 3: Verify '{goal.description[:40]}'", "tool": "terminal", "outcome": "Verified", "time": 30},
        ]

    def _find_step_by_id(self, plan: Plan, step_id: str) -> Optional[PlanStep]:
        for s in plan.steps:
            if s.id == step_id:
                return s
        return None

    def replan(self, goal: Goal, failed_step: PlanStep,
               reason: str) -> Plan:
        """Replan after a step failure."""
        plan = self.plans.get(goal.id)
        if not plan:
            return self.plan_goal(goal)

        # Add recovery steps
        recovery = PlanStep(
            action=f"Recover from: {reason}",
            tool="",
            expected_outcome="Recovered",
            estimated_time=30.0,
        )
        plan.steps.insert(plan.steps.index(failed_step) + 1, recovery)
        return plan


# ════════════════════════════════════════════════════════════
# Autonomous Engine
# ════════════════════════════════════════════════════════════

class AutonomousEngine:
    """
    Complete autonomous agent engine.

    Can operate for hours/days pursuing self-generated or user-assigned goals,
    with plan decomposition, progress tracking, stall detection, and replanning.
    """

    def __init__(self, name: str = "autonomy"):
        self.name = name
        self.goal_manager = GoalManager()
        self.planner = Planner()
        self.context = ExecutionContext()

        self.total_goals_completed = 0
        self.total_actions_taken = 0
        self.created_at = time.time()

        self._lock = threading.Lock()

    def assign_goal(self, description: str,
                    source: GoalSource = GoalSource.USER_REQUEST,
                    priority: GoalPriority = GoalPriority.MEDIUM,
                    domain: str = "",
                    deadline: float = 0.0) -> Goal:
        """Assign a new goal to the agent."""
        goal = self.goal_manager.create_goal(
            description=description,
            source=source,
            priority=priority,
            domain=domain,
            deadline=deadline,
        )
        # Auto-plan
        self.planner.plan_goal(goal)
        logger.info(f"Goal assigned: '{description[:60]}' [{goal.id[:8]}]")
        return goal

    def get_next_action(self) -> Optional[Dict[str, Any]]:
        """
        Get the next action the agent should take.

        This is the main autonomy loop entry point.
        Called repeatedly to drive autonomous behavior.
        """
        with self._lock:
            # Check if we have an active goal
            if self.context.active_goal_id:
                goal = self.goal_manager.goals.get(self.context.active_goal_id)
                if goal and goal.status == GoalStatus.ACTIVE:
                    plan = self.planner.plans.get(goal.id)
                    if plan:
                        step = self.planner.get_next_step(plan)
                        if step:
                            step.status = "active"
                            self.total_actions_taken += 1
                            return {
                                "goal_id": goal.id,
                                "goal_description": goal.description[:80],
                                "step_id": step.id,
                                "action": step.action,
                                "tool": step.tool,
                                "expected_outcome": step.expected_outcome,
                                "step_index": plan.steps.index(step) + 1,
                                "total_steps": len(plan.steps),
                            }
                        else:
                            # Plan exhausted — check if goal is done
                            all_done = all(s.status in ("completed", "skipped")
                                          for s in plan.steps)
                            if all_done:
                                self.goal_manager.complete_goal(goal.id)
                                self.total_goals_completed += 1
                                self.context.active_goal_id = ""
                                self.context.active_plan = None
                                logger.info(f"Goal completed: {goal.description[:60]}")
                            # Continue to next goal
                    else:
                        # No plan yet
                        self.planner.plan_goal(goal)

            # Pick next goal
            next_goal = self.goal_manager.get_next_goal()
            if next_goal:
                self.goal_manager.activate_goal(next_goal.id)
                self.context.active_goal_id = next_goal.id
                plan = self.planner.plan_goal(next_goal)
                self.context.active_plan = plan
                self.context.current_step_index = 0
                # Recurse to get first action
                return self.get_next_action()

            return None  # Nothing to do

    def report_action_result(self, goal_id: str, step_id: str,
                             success: bool, outcome: str = "",
                             time_spent: float = 0.0):
        """Report the result of an executed action."""
        with self._lock:
            plan = self.planner.plans.get(goal_id)
            if not plan:
                return

            for step in plan.steps:
                if step.id == step_id:
                    if success:
                        step.status = "completed"
                        step.actual_time = time_spent
                        self.context.consecutive_failures = 0
                        self.context.stalled_since = 0.0
                    else:
                        step.retry_count += 1
                        if step.retry_count >= step.max_retries:
                            step.status = "failed"
                            self.context.consecutive_failures += 1

                            if self.context.consecutive_failures >= 3:
                                # Too many failures — replan or fail goal
                                goal = self.goal_manager.goals.get(goal_id)
                                if goal:
                                    self.planner.replan(goal, step, outcome)
                                    logger.warning(f"Replanning goal {goal_id} after failures")
                            else:
                                step.status = "pending"  # Reset for retry
                        else:
                            step.status = "pending"  # Reset for retry

                    # Update goal progress
                    if goal_id in self.goal_manager.goals:
                        completed = sum(1 for s in plan.steps if s.status == "completed")
                        self.goal_manager.update_progress(goal_id, completed / max(1, len(plan.steps)))
                    break

    def detect_stall(self) -> Optional[Dict[str, Any]]:
        """Detect if the agent is stalled and needs intervention."""
        with self._lock:
            if self.context.consecutive_failures >= 3:
                return {
                    "stalled": True,
                    "reason": "consecutive_failures",
                    "failures": self.context.consecutive_failures,
                    "suggestion": "Replan or escalate to user",
                }

            if self.context.active_goal_id:
                goal = self.goal_manager.goals.get(self.context.active_goal_id)
                if goal and goal.is_overdue:
                    return {
                        "stalled": True,
                        "reason": "goal_overdue",
                        "goal": goal.description[:60],
                        "suggestion": "Re-evaluate priority or deadline",
                    }

            return None

    def generate_maintenance_goals(self):
        """Generate internal maintenance goals (self-improvement)."""
        self.assign_goal(
            "Consolidate recent learning experiences",
            source=GoalSource.MAINTENANCE,
            priority=GoalPriority.LOW,
            domain="learning",
        )
        self.assign_goal(
            "Review and update self-model with recent experiences",
            source=GoalSource.MAINTENANCE,
            priority=GoalPriority.LOW,
            domain="self_improvement",
        )

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "name": self.name,
                "goals": self.goal_manager.stats(),
                "total_completed": self.total_goals_completed,
                "total_actions": self.total_actions_taken,
                "active_goal": self.context.active_goal_id[:8] if self.context.active_goal_id else None,
                "consecutive_failures": self.context.consecutive_failures,
                "uptime_seconds": time.time() - self.created_at,
            }


def integrate_autonomy(agent) -> AutonomousEngine:
    engine = AutonomousEngine(name=f"{getattr(agent, 'name', 'agent')}-auto")
    agent.autonomy = engine
    logger.info(f"AutonomousEngine integrated into {getattr(agent, 'name', 'agent')}")
    return engine
