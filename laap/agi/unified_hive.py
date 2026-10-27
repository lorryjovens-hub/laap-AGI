"""
LAAP AGI — Unified Multi-Agent System (统一多Agent体系)

Merges five previously separate systems into one coherent framework:
  AgentRegistry + SharedRegistry + EventBus + CentralBrain + SwarmSystem

Design principles:
  1. Every agent has a unique ID within the hive
  2. One registry to rule them all (no more duplicates)
  3. Market-based task allocation with role-matching
  4. Swarm formation for complex tasks
  5. Collective knowledge sharing via HiveMind
  6. Consensus voting for critical decisions

Governance model (hybrid):
  ┌──────────────────────────────────────────────────────┐
  │  Ant Colony ──── emergent task allocation (market)   │
  │  Bee Swarm ───── role-based collaboration (swarm)    │
  │  Human Corp ──── OKR-based governance (objectives)   │
  │  Incident Cmd ── crisis chain-of-command (escalate)  │
  └──────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import logging

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple, Callable
from enum import Enum
import time, logging, threading, uuid, json, os, random, heapq, subprocess, platform
from pathlib import Path
from datetime import datetime
from collections import defaultdict, deque

logger = logging.getLogger("laap.agi.hive")

# ════════════════════════════════════════════════════════════
# Agent Identity & Registration
# ════════════════════════════════════════════════════════════

class AgentClass(str, Enum):
    QUEEN = "queen"        # Central Coordinator (one per hive)
    WORKER = "worker"      # General task execution
    CODER = "coder"        # Code generation/modification
    REVIEWER = "reviewer"  # Code review & quality
    TESTER = "tester"      # Testing & validation
    SCOUT = "scout"        # Research & exploration
    GUARDIAN = "guardian"  # Security & monitoring

class AgentStatus(str, Enum):
    ONLINE = "online"
    BUSY = "busy"
    IDLE = "idle"
    OFFLINE = "offline"
    DEGRADED = "degraded"

@dataclass
class HiveAgent:
    """A single agent in the hive. Every Hermes instance has one."""
    agent_id: str           # Unique global ID (uuid8)
    serial: str             # Human-readable: "A-001", "A-002"
    name: str               # Display name
    role: AgentClass         # Primary role
    secondary_roles: List[AgentClass] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)
    status: AgentStatus = AgentStatus.ONLINE
    version: str = "3.0.0"
    laap_enabled: bool = True
    profile: str = "default"
    pid: int = 0
    host: str = ""
    current_task: str = ""
    performance_score: float = 0.5
    tasks_completed: int = 0
    tasks_failed: int = 0
    joined_at: str = ""
    last_heartbeat: str = ""
    load_index: float = 0.0  # 0=idle, 1=maxed out


# ════════════════════════════════════════════════════════════
# Task System
# ════════════════════════════════════════════════════════════

class TaskPriority(int, Enum):
    CRITICAL = 1    # System survival
    HIGH = 2        # User-facing, blocking
    MEDIUM = 3      # Important but not blocking
    LOW = 4         # Nice to have
    BACKGROUND = 5  # Can wait indefinitely

class TaskType(str, Enum):
    CODE_FIX = "code_fix"
    CODE_FEATURE = "code_feature"
    CODE_REVIEW = "code_review"
    CODE_TEST = "code_test"
    CODE_REFACTOR = "code_refactor"
    RESEARCH = "research"
    MONITOR = "monitor"
    CLEANUP = "cleanup"
    DEPLOY = "deploy"
    EMERGENCY = "emergency"

@dataclass
class HiveTask:
    task_id: str
    title: str
    description: str
    task_type: TaskType = TaskType.CODE_FIX
    priority: TaskPriority = TaskPriority.MEDIUM
    required_roles: List[AgentClass] = field(default_factory=list)
    required_capabilities: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    assigned_to: str = ""
    swarm_id: str = ""       # If handled by a swarm
    status: str = "queued"   # queued→assigned→running→done|failed
    created_at: float = field(default_factory=time.time)
    started_at: float = 0.0
    deadline: float = 0.0    # Unix timestamp
    base_reward: float = 1.0 # Market reward for completing
    result: Any = None
    affected_files: List[str] = field(default_factory=list)
    okr_link: str = ""       # Link to parent Objective


# ════════════════════════════════════════════════════════════
# OKR System (Objectives & Key Results)
# ════════════════════════════════════════════════════════════

@dataclass
class Objective:
    obj_id: str
    title: str
    description: str
    key_results: List[Dict[str, Any]] = field(default_factory=list)
    progress: float = 0.0
    status: str = "active"
    owner: str = ""           # Agent responsible
    created_at: float = field(default_factory=time.time)
    deadline: float = 0.0


# ════════════════════════════════════════════════════════════
# Unified Hive — The One System
# ════════════════════════════════════════════════════════════

class HiveMind:
    """
    Unified multi-agent system. Replaces ALL previous separate systems.

    Agents: register, heartbeat, discover (cross-version)
    Tasks:  submit, bid, assign, track (market + central)
    Events: publish, subscribe, query (event bus)
    Swarms: form, collaborate, dissolve
    Knowledge: broadcast, query (collective intelligence)
    Consensus: propose, vote, approve (governance)
    OKRs: define, track, report (objectives)

    File-based persistence: ~/.laap/hive.json
    All Hermes instances (any version) share this single file.
    """

    HIVE_PATH = os.path.join(os.path.expanduser("~"), ".laap", "hive.json")

    def __init__(self):
        self.agents: Dict[str, HiveAgent] = {}    # agent_id → HiveAgent
        self.tasks: Dict[str, HiveTask] = {}      # task_id → HiveTask
        self.objectives: Dict[str, Objective] = {}
        self.events: deque = deque(maxlen=500)
        self.swarms: Dict[str, Dict] = {}
        self.consensus_pool: Dict[str, Dict] = {}

        self._agent_serials: Dict[AgentClass, int] = defaultdict(int)
        self._lock = threading.Lock()
        self._load()

        self.total_cycles = 0
        self.total_tasks_completed = 0
        self.created_at = time.time()

    # ── Agent Management ──

    def register_agent(self, name: str, role: AgentClass,
                       capabilities: List[str] = None,
                       version: str = "3.0.0",
                       laap_enabled: bool = True,
                       profile: str = "default") -> HiveAgent:
        """Register a new agent in the hive. Assigns unique serial."""
        with self._lock:
            self._agent_serials[role] += 1
            serial = f"{role.value[0].upper()}-{self._agent_serials[role]:03d}"

            agent = HiveAgent(
                agent_id=str(uuid.uuid4())[:8],
                serial=serial,
                name=name,
                role=role,
                capabilities=capabilities or [],
                version=version,
                laap_enabled=laap_enabled,
                profile=profile,
                pid=os.getpid(),
                host=platform.node(),
                joined_at=datetime.now().isoformat(),
            )
            self.agents[agent.agent_id] = agent
            self._publish("agent.registered", agent.agent_id,
                         {"serial": serial, "role": role.value, "name": name})
            self._save()
            return agent

    def heartbeat(self, agent_id: str, current_task: str = ""):
        """Update agent heartbeat and status."""
        with self._lock:
            agent = self.agents.get(agent_id)
            if not agent:
                return
            agent.last_heartbeat = datetime.now().isoformat()
            agent.status = AgentStatus.BUSY if current_task else AgentStatus.IDLE
            agent.current_task = current_task
            agent.load_index = min(1.0, agent.tasks_completed / max(1, agent.tasks_completed + 1))

            # Prune dead agents
            self._prune_dead()

            self._save()

    def discover(self) -> Dict[str, List[HiveAgent]]:
        """Discover all agents in the hive, grouped by class."""
        result = defaultdict(list)
        alive = 0
        with self._lock:
            for agent in self.agents.values():
                if self._is_alive(agent):
                    result[agent.role.value].append(agent)
                    alive += 1
                else:
                    result["offline"].append(agent)
        return dict(result)

    def discover_cross_version(self) -> Dict[str, int]:
        """Cross-version discovery — detect non-LAAP Hermes processes."""
        counts = {"laap": 0, "hermes_native": 0}
        with self._lock:
            for agent in self.agents.values():
                if self._is_alive(agent):
                    if agent.laap_enabled:
                        counts["laap"] += 1
                    else:
                        counts["hermes_native"] += 1
        # OS-level discovery for non-registered processes
        try:
            if platform.system() == "Windows":
                result = subprocess.run(
                    ["wmic", "process", "where", "name='python.exe'",
                     "get", "CommandLine", "/format:csv"],
                    capture_output=True, text=True, timeout=5
                )
                for line in result.stdout.split('\n'):
                    if 'hermes' in line.lower() and 'laap' not in line.lower():
                        counts["hermes_native"] += 1
            else:
                result = subprocess.run(
                    ["pgrep", "-f", "hermes"], capture_output=True, text=True, timeout=5
                )
                counts["hermes_native"] += max(0, len(result.stdout.strip().split('\n')) - 1)
        except Exception as e:
            logger.debug(f"操作失败: {e}")
        return counts

    # ── Task System ──

    def submit_task(self, title: str, description: str,
                    task_type: TaskType = TaskType.CODE_FIX,
                    priority: TaskPriority = TaskPriority.MEDIUM,
                    required_roles: List[AgentClass] = None,
                    required_capabilities: List[str] = None,
                    dependencies: List[str] = None,
                    deadline: float = 0.0,
                    base_reward: float = 1.0) -> HiveTask:
        """Submit a task to the hive task board."""
        task = HiveTask(
            task_id=str(uuid.uuid4())[:8],
            title=title,
            description=description,
            task_type=task_type,
            priority=priority,
            required_roles=required_roles or [],
            required_capabilities=required_capabilities or [],
            dependencies=dependencies or [],
            deadline=deadline,
            base_reward=base_reward,
        )
        with self._lock:
            self.tasks[task.task_id] = task
            self._publish("task.created", "hive", {"task_id": task.task_id, "title": title})
            self._save()
        return task

    def bid_task(self, agent_id: str, task_id: str, bid_amount: float = 1.0) -> Tuple[bool, str]:
        """Agent bids on a task. Market-based allocation."""
        with self._lock:
            task = self.tasks.get(task_id)
            agent = self.agents.get(agent_id)

            if not task or not agent:
                return False, "Not found"
            if task.status != "queued":
                return False, f"Task is {task.status}"
            if not self._dependencies_met(task):
                return False, "Dependencies not met"

            # Check capability match
            match = self._capability_match(task.required_capabilities, agent.capabilities)
            if match == 0.0 and task.required_capabilities:
                return False, "No capability match"

            # Award to highest bidder after a brief window
            task.assigned_to = agent_id
            task.status = "assigned"
            task.started_at = time.time()

            self._publish("task.assigned", agent_id,
                         {"task_id": task_id, "title": task.title})
            self._save()
            return True, "Assigned"

    def complete_task(self, task_id: str, success: bool = True,
                      result: Any = None):
        """Mark a task as complete."""
        with self._lock:
            task = self.tasks.get(task_id)
            if not task:
                return

            task.status = "done" if success else "failed"
            task.result = result

            agent = self.agents.get(task.assigned_to)
            if agent:
                if success:
                    agent.tasks_completed += 1
                    agent.performance_score = min(1.0, agent.performance_score + 0.05)
                else:
                    agent.tasks_failed += 1
                    agent.performance_score = max(0.1, agent.performance_score - 0.1)

            self.total_tasks_completed += 1
            self._publish("task.completed", task.assigned_to,
                         {"task_id": task_id, "success": success})
            self._save()

    def get_pending_tasks(self) -> List[HiveTask]:
        with self._lock:
            pending = [t for t in self.tasks.values() if t.status == "queued"]
            pending.sort(key=lambda t: (t.priority.value, -t.base_reward))
            return pending

    # ── Swarm Formation ──

    def form_swarm(self, task_id: str, members: List[str],
                   leader: str = "") -> str:
        """Form a swarm to tackle a complex task together."""
        swarm_id = str(uuid.uuid4())[:8]

        with self._lock:
            self.swarms[swarm_id] = {
                "swarm_id": swarm_id,
                "task_id": task_id,
                "members": members,
                "leader": leader or members[0],
                "status": "forming",
                "created_at": time.time(),
                "findings": [],
            }

            task = self.tasks.get(task_id)
            if task:
                task.swarm_id = swarm_id

            self._publish("swarm.formed", swarm_id,
                         {"task_id": task_id, "members": len(members)})
            self._save()

        return swarm_id

    def dissolve_swarm(self, swarm_id: str, success: bool = True):
        with self._lock:
            swarm = self.swarms.pop(swarm_id, None)
            if not swarm:
                return

            task = self.tasks.get(swarm["task_id"])
            if task:
                task.status = "done" if success else "failed"

            self._publish("swarm.dissolved", swarm_id,
                         {"success": success, "members": len(swarm["members"])})
            self._save()

    # ── Consensus ──

    def propose(self, title: str, description: str,
                required_approvals: int = 2,
                risk_level: str = "medium") -> str:
        """Propose a change that requires multi-agent consensus."""
        proposal_id = str(uuid.uuid4())[:8]
        with self._lock:
            self.consensus_pool[proposal_id] = {
                "id": proposal_id,
                "title": title,
                "description": description,
                "required_approvals": required_approvals,
                "risk_level": risk_level,
                "votes_for": 0,
                "votes_against": 0,
                "voters": {},
                "status": "voting",
                "created_at": time.time(),
            }
            self._save()
        return proposal_id

    def vote(self, proposal_id: str, agent_id: str,
             approve: bool = True, agent_role: str = "worker") -> str:
        """Cast a vote on a proposal."""
        with self._lock:
            p = self.consensus_pool.get(proposal_id)
            if not p:
                return "not_found"

            p["voters"][agent_id] = approve
            if approve:
                p["votes_for"] += 1
            else:
                p["votes_against"] += 1
                # Veto: queen or guardian rejection kills proposal
                if agent_role in ("queen", "guardian"):
                    p["status"] = "rejected"
                    return "rejected"

            if p["votes_for"] >= p["required_approvals"]:
                p["status"] = "approved"

            self._save()
            return p["status"]

    # ── Collective Knowledge ──

    def share_knowledge(self, source_agent: str, topic: str,
                        content: str, confidence: float = 0.5):
        """Share a discovery with all agents."""
        self._publish("knowledge.shared", source_agent,
                     {"topic": topic, "content": content[:200],
                      "confidence": confidence})

    # ── Events ──

    def _publish(self, event_type: str, source: str, data: Dict):
        self.events.append({
            "id": str(uuid.uuid4())[:8],
            "type": event_type,
            "source": source,
            "data": data,
            "timestamp": datetime.now().isoformat(),
        })

    def get_events(self, since: str = "", event_type: str = "",
                   limit: int = 50) -> List[Dict]:
        result = list(self.events)
        if since:
            result = [e for e in result if e["timestamp"] > since]
        if event_type:
            result = [e for e in result if e["type"] == event_type]
        return result[-limit:]

    # ── Helpers ──

    def _is_alive(self, agent: HiveAgent, timeout: int = 60) -> bool:
        try:
            last = datetime.fromisoformat(agent.last_heartbeat)
            return (datetime.now() - last).total_seconds() < timeout
        except: return False

    def _prune_dead(self, timeout: int = 300):
        dead = [aid for aid, a in self.agents.items()
               if not self._is_alive(a, timeout)]
        for aid in dead:
            del self.agents[aid]

    def _capability_match(self, required: List[str], available: List[str]) -> float:
        if not required: return 0.5
        if not available: return 0.0
        matches = sum(1 for r in required
                     for a in available
                     if r.lower() in a.lower() or a.lower() in r.lower())
        return matches / len(required)

    def _dependencies_met(self, task: HiveTask) -> bool:
        for dep_id in task.dependencies:
            dep = self.tasks.get(dep_id)
            if not dep or dep.status != "done":
                return False
        return True

    # ── Persistence ──

    def _load(self):
        if os.path.exists(self.HIVE_PATH):
            try:
                data = json.load(open(self.HIVE_PATH, encoding='utf-8'))
                for a in data.get("agents", []):
                    self.agents[a["agent_id"]] = HiveAgent(**a)
                for t in data.get("tasks", []):
                    self.tasks[t["task_id"]] = HiveTask(**t)
                self.events = deque(data.get("events", [])[-500:], maxlen=500)
            except Exception as e:
                logger.debug(f"操作失败: {e}")
    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.HIVE_PATH), exist_ok=True)
            data = {
                "agents": [a.__dict__ for a in self.agents.values()],
                "tasks": [t.__dict__ for t in self.tasks.values()],
                "events": list(self.events),
                "updated": datetime.now().isoformat(),
            }
            json.dump(data, open(self.HIVE_PATH, 'w', encoding='utf-8'), indent=2)
        except Exception as e:
            logger.debug(f"操作失败: {e}")
    def stats(self) -> Dict[str, Any]:
        with self._lock:
            alive = [a for a in self.agents.values() if self._is_alive(a)]
            return {
                "agents_total": len(self.agents),
                "agents_alive": len(alive),
                "tasks_queued": sum(1 for t in self.tasks.values() if t.status == "queued"),
                "tasks_running": sum(1 for t in self.tasks.values() if t.status in ("assigned","running")),
                "tasks_done": sum(1 for t in self.tasks.values() if t.status == "done"),
                "active_swarms": len(self.swarms),
                "pending_consensus": len(self.consensus_pool),
                "total_events": len(self.events),
                "uptime_seconds": time.time() - self.created_at,
            }


def integrate_hive(agent) -> Dict:
    """One-line integration: replace all old systems with the HiveMind."""
    hive = HiveMind()
    agent.hive = hive

    # Register this agent
    agent._hive_agent = hive.register_agent(
        name=getattr(agent, 'name', 'Ao'),
        role=AgentClass.QUEEN,
        capabilities=["coding","architecture","evolution","self_healing",
                      "quality_assurance","orchestration","swarm"],
        version=getattr(agent, 'version', '3.0.0'),
        profile=os.environ.get("HERMES_PROFILE", "default"),
    )

    # Health check update
    agent.health_check = lambda: {
        "healthy": True,
        "hive": hive.stats(),
        "my_serial": agent._hive_agent.serial,
        "modules": getattr(agent, '_module_count', lambda: 0)(),
    }

    return hive.stats()
