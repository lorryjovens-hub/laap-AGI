"""
LAAP AGI — Central Brain (中央大脑)

Sits above all sub-agents. Actively distributes tasks based on:
  1. Capability matching — which agent CAN do this?
  2. Load balancing — which agent SHOULD do this?
  3. Dependency graph — what must finish FIRST?
  4. Health awareness — is the agent still alive?

Difference from passive components:
  AgentRegistry: agents announce themselves (PASSIVE)
  TaskBoard:     tasks wait to be claimed (PASSIVE)
  CentralBrain:  DECIDES who does what and WHEN (ACTIVE)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple, Callable
from enum import Enum
import time, logging, threading, uuid, heapq, json, os
from collections import defaultdict

logger = logging.getLogger("laap.agi.central_brain")


class TaskStatus(str, Enum):
    QUEUED = "queued"
    ASSIGNED = "assigned"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    BLOCKED = "blocked"  # waiting for dependency


class AgentRole(str, Enum):
    PRIMARY = "primary"      # Main orchestrator
    CODER = "coder"          # Code generation/modification
    REVIEWER = "reviewer"    # Code review
    TESTER = "tester"        # Testing
    RESEARCHER = "researcher" # Research/analysis
    MONITOR = "monitor"      # System monitoring
    WORKER = "worker"        # General worker


@dataclass
class BrainTask:
    task_id: str
    description: str
    required_capabilities: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)  # task_ids that must finish first
    priority: float = 0.5
    status: TaskStatus = TaskStatus.QUEUED
    assigned_to: str = ""  # agent_id
    estimated_duration: float = 30.0  # seconds
    created_at: float = field(default_factory=time.time)
    started_at: float = 0.0
    completed_at: float = 0.0
    result: Any = None

    @property
    def waiting_time(self) -> float:
        return time.time() - self.created_at


@dataclass
class AgentLoad:
    agent_id: str
    name: str
    active_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    avg_task_time: float = 30.0
    last_active: float = field(default_factory=time.time)
    cpu_score: float = 1.0  # 1.0 = baseline, lower = busier


class BrainResult:
    """Result of central brain decision cycle."""
    def __init__(self):
        self.tasks_assigned: List[BrainTask] = []
        self.tasks_blocked: List[BrainTask] = []
        self.tasks_failed: List[BrainTask] = []
        self.dead_agents_reassigned: int = 0
        self.recommendations: List[str] = []


class CentralBrain:
    """
    Active orchestrator. Every decision cycle:
      1. Scan registry for online agents + their capabilities
      2. Scan task queue for pending tasks
      3. Build dependency-aware execution plan
      4. Match tasks to best agents (capability + load)
      5. Assign tasks
      6. Monitor progress, reassign dead agent tasks
    """

    def __init__(self, name: str = "central-brain"):
        self.name = name
        self.tasks: Dict[str, BrainTask] = {}
        self.agent_loads: Dict[str, AgentLoad] = {}
        self._dependency_graph: Dict[str, List[str]] = defaultdict(list)
        self._reverse_deps: Dict[str, List[str]] = defaultdict(list)

        self.total_cycles = 0
        self.total_assignments = 0
        self.created_at = time.time()

        # External references (set after init)
        self.registry = None  # AgentRegistry
        self.task_board = None  # TaskBoard
        self._delegate_fn = None  # delegate_task function

        # Background thread
        self._running = False
        self._thread = None
        self._lock = threading.Lock()

    def integrate(self, registry, task_board, delegate_fn=None):
        """Wire up to existing components."""
        self.registry = registry
        self.task_board = task_board
        self._delegate_fn = delegate_fn

    def submit_task(self, description: str, required_capabilities: List[str] = None,
                    dependencies: List[str] = None, priority: float = 0.5,
                    estimated_duration: float = 30.0) -> BrainTask:
        """Submit a task to the brain for distribution."""
        task = BrainTask(
            task_id=str(uuid.uuid4())[:8],
            description=description,
            required_capabilities=required_capabilities or [],
            dependencies=dependencies or [],
            priority=priority,
            estimated_duration=estimated_duration,
        )
        with self._lock:
            self.tasks[task.task_id] = task
            # Build dependency graph
            for dep in task.dependencies:
                self._dependency_graph[dep].append(task.task_id)
                self._reverse_deps[task.task_id].append(dep)
        return task

    def decision_cycle(self) -> BrainResult:
        """
        One decision cycle. Called periodically or on-demand.

        Returns: BrainResult with assignments made.
        """
        self.total_cycles += 1
        result = BrainResult()

        with self._lock:
            # Step 1: Get online agents with capabilities
            online = self.registry.get_online_agents() if self.registry else []
            agent_map = {a.agent_id: a for a in online}

            # Update agent load tracking
            for agent in online:
                if agent.agent_id not in self.agent_loads:
                    self.agent_loads[agent.agent_id] = AgentLoad(
                        agent_id=agent.agent_id, name=agent.name
                    )

            # Step 2: Mark dead agent tasks for reassignment
            for task in self.tasks.values():
                if task.status == TaskStatus.RUNNING and task.assigned_to not in agent_map:
                    task.status = TaskStatus.QUEUED
                    task.assigned_to = ""
                    result.dead_agents_reassigned += 1

            # Step 3: Find queued tasks with satisfied dependencies
            ready = []
            for task in self.tasks.values():
                if task.status != TaskStatus.QUEUED:
                    continue
                if self._dependencies_satisfied(task, agent_map):
                    ready.append(task)
                else:
                    task.status = TaskStatus.BLOCKED
                    result.tasks_blocked.append(task)

            # Sort by priority (highest first), then waiting time
            ready.sort(key=lambda t: (-t.priority, -t.waiting_time))

            # Step 4: For each ready task, find best agent
            for task in ready:
                best_agent = self._find_best_agent(task, agent_map)
                if best_agent:
                    task.assigned_to = best_agent.agent_id
                    task.status = TaskStatus.ASSIGNED
                    task.started_at = time.time()

                    # Update load
                    load = self.agent_loads.get(best_agent.agent_id)
                    if load:
                        load.active_tasks += 1
                        load.last_active = time.time()

                    result.tasks_assigned.append(task)
                    self.total_assignments += 1
                else:
                    result.tasks_failed.append(task)

        # Step 5: Generate recommendations
        if result.dead_agents_reassigned > 0:
            result.recommendations.append(
                f"Reassigned {result.dead_agents_reassigned} tasks from dead agents"
            )
        if result.tasks_blocked:
            result.recommendations.append(
                f"{len(result.tasks_blocked)} tasks blocked on dependencies"
            )
        if result.tasks_failed:
            result.recommendations.append(
                f"{len(result.tasks_failed)} tasks found no capable agent"
            )

        return result

    def report_completion(self, task_id: str, success: bool = True,
                          result: Any = None):
        """Called when an agent finishes a task."""
        with self._lock:
            task = self.tasks.get(task_id)
            if not task:
                return

            task.status = TaskStatus.DONE if success else TaskStatus.FAILED
            task.completed_at = time.time()
            task.result = result

            # Update load
            load = self.agent_loads.get(task.assigned_to)
            if load:
                load.active_tasks = max(0, load.active_tasks - 1)
                if success:
                    load.completed_tasks += 1
                    duration = task.completed_at - task.started_at
                    if duration > 0:
                        load.avg_task_time = 0.8 * load.avg_task_time + 0.2 * duration
                else:
                    load.failed_tasks += 1

            # Unblock dependent tasks
            for dependent_id in self._dependency_graph.get(task_id, []):
                dep_task = self.tasks.get(dependent_id)
                if dep_task and dep_task.status == TaskStatus.BLOCKED:
                    dep_task.status = TaskStatus.QUEUED

    def _find_best_agent(self, task: BrainTask,
                         online: Dict[str, Any]) -> Optional[Any]:
        """Find the best agent for a task based on capability + load."""
        if not online:
            return None

        scored = []
        for agent in online.values():
            # Capability match score (0.0 to 1.0)
            cap_score = self._capability_match(task.required_capabilities,
                                                agent.capabilities if hasattr(agent, 'capabilities') else [])

            if cap_score == 0.0 and task.required_capabilities:
                continue  # Skip completely incapable agents

            # Load score (lower load = better)
            load = self.agent_loads.get(agent.agent_id)
            if load:
                load.cpu_score = 1.0 / max(0.5, 1.0 + load.active_tasks * 0.3)
                load_score = load.cpu_score
            else:
                load_score = 1.0

            # Role bonus
            role_bonus = self._role_match(task, getattr(agent, 'role', 'worker'))

            # Final score: 60% capability + 30% load + 10% role
            final = cap_score * 0.6 + load_score * 0.3 + role_bonus * 0.1
            scored.append((final, agent))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1] if scored else None

    def _capability_match(self, required: List[str], available: List[str]) -> float:
        """Score how well agent capabilities match requirements."""
        if not required:
            return 1.0  # No requirements = any agent can do it
        if not available:
            return 0.0

        matches = 0
        for req in required:
            req_lower = req.lower()
            for avail in available:
                if req_lower in avail.lower() or avail.lower() in req_lower:
                    matches += 1
                    break

        return matches / len(required)

    def _role_match(self, task: BrainTask, role: str) -> float:
        """Bonus score for role alignment."""
        task_lower = task.description.lower()
        role_map = {
            "coder": ["code", "fix", "implement", "build", "refactor", "write"],
            "reviewer": ["review", "audit", "check", "inspect", "verify"],
            "tester": ["test", "run", "benchmark", "measure", "validate"],
            "researcher": ["research", "analyze", "explore", "find", "search"],
            "monitor": ["monitor", "watch", "track", "observe", "alert"],
        }

        keywords = role_map.get(role, [])
        for kw in keywords:
            if kw in task_lower:
                return 1.0

        return 0.2  # Default bonus

    def _dependencies_satisfied(self, task: BrainTask,
                                 online_agents: Dict[str, Any]) -> bool:
        """Check if all dependencies are done."""
        for dep_id in task.dependencies:
            dep = self.tasks.get(dep_id)
            if not dep or dep.status != TaskStatus.DONE:
                return False
        return True

    def get_execution_plan(self) -> Dict[str, Any]:
        """Get the current execution plan with dependency ordering."""
        with self._lock:
            # Topological sort of all tasks
            ready = []
            blocked = []
            done = []
            running = []

            for task in self.tasks.values():
                if task.status == TaskStatus.DONE:
                    done.append(task)
                elif task.status in (TaskStatus.ASSIGNED, TaskStatus.RUNNING):
                    running.append(task)
                elif task.status == TaskStatus.BLOCKED:
                    blocked.append(task)
                else:
                    ready.append(task)

            return {
                "total": len(self.tasks),
                "done": len(done),
                "running": len(running),
                "ready": len(ready),
                "blocked": len(blocked),
                "agents": len(self.agent_loads),
                "dependencies": dict(self._dependency_graph),
            }

    def start_background(self, interval: int = 5):
        """Start background decision cycling."""
        if self._running:
            return
        self._running = True

        def _cycle():
            while self._running:
                try:
                    result = self.decision_cycle()
                    if result.tasks_assigned:
                        logger.info(
                            f"Brain assigned {len(result.tasks_assigned)} tasks: "
                            f"{[(t.task_id, t.assigned_to) for t in result.tasks_assigned]}"
                        )
                except Exception as e:
                    logger.error(f"Brain cycle error: {e}")
                time.sleep(interval)

        self._thread = threading.Thread(target=_cycle, daemon=True)
        self._thread.start()
        logger.info(f"CentralBrain background cycle started (interval={interval}s)")

    def stop_background(self):
        self._running = False

    def stats(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "cycles": self.total_cycles,
            "assignments": self.total_assignments,
            "execution_plan": self.get_execution_plan(),
            "agent_loads": {
                aid: {
                    "name": al.name,
                    "active": al.active_tasks,
                    "completed": al.completed_tasks,
                    "cpu_score": round(al.cpu_score, 2),
                }
                for aid, al in self.agent_loads.items()
            },
        }


def integrate_central_brain(agent) -> CentralBrain:
    brain = CentralBrain(name=f"{getattr(agent, 'name', 'agent')}-brain")
    brain.integrate(
        registry=getattr(agent, 'agent_registry', None),
        task_board=getattr(agent, 'task_board', None),
    )
    agent.central_brain = brain
    logger.info(f"CentralBrain integrated into {getattr(agent, 'name', 'agent')}")
    return brain
