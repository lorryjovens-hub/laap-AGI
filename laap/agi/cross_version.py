"""
LAAP AGI — Cross-Version Agent Awareness & Update Notification

Enables agents across different Hermes versions to perceive each other:

  1. SharedRegistry  — Well-known file ALL Hermes instances read/write
  2. ProcessDiscovery — Find running Hermes processes (even non-LAAP)
  3. VersionBridge    — Translate capabilities across LAAP versions
  4. UpdateNotifier   — Auto-log significant changes, notify user on startup

Key design: uses FILESYSTEM as communication channel.
  - No network, no sockets, no complex IPC
  - ~/.laap/registry.json — ALL Hermes instances share this
  - Even vanilla Hermes (no LAAP) can be detected via process scanning
"""

from __future__ import annotations

import logging

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
import time, logging, threading, uuid, json, os, re, subprocess, platform
from pathlib import Path
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger("laap.agi.cross_version")


# ════════════════════════════════════════════════════════════
# Shared Registry — Cross-Version Agent Discovery
# ════════════════════════════════════════════════════════════

@dataclass
class AgentEntry:
    """An agent's entry in the shared registry."""
    agent_id: str
    name: str
    version: str           # e.g. "LAAP v3.0.0", "Hermes 2.x"
    laap_enabled: bool
    profile: str           # e.g. "laap-avatar", "default"
    pid: int
    capabilities: List[str] = field(default_factory=list)
    status: str = "online"
    current_task: str = ""
    host: str = ""
    started_at: str = ""   # ISO timestamp
    last_heartbeat: str = ""  # ISO timestamp
    endpoint: str = ""     # Optional: how to reach this agent

    def is_laap(self) -> bool: return self.laap_enabled
    def is_alive(self, timeout_seconds: int = 30) -> bool:
        try:
            last = datetime.fromisoformat(self.last_heartbeat)
            return (datetime.now() - last).total_seconds() < timeout_seconds
        except: return False


class SharedRegistry:
    """
    Cross-version, cross-process agent registry.

    Location: ~/.laap/registry.json
    Accessible by ALL Hermes instances on the same machine.

    Even vanilla Hermes (no LAAP) can be detected via process scanning
    and registered here by the LAAP-aware instances.
    """

    REGISTRY_PATH = os.path.join(
        os.path.expanduser("~"), ".laap", "registry.json"
    )

    def __init__(self):
        self.agents: Dict[str, AgentEntry] = {}  # pid → entry
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(self.REGISTRY_PATH), exist_ok=True)
        self._load()

    def register(self, agent_id: str, name: str, version: str,
                 laap_enabled: bool, profile: str = "default",
                 capabilities: List[str] = None,
                 current_task: str = "",
                 endpoint: str = "") -> AgentEntry:
        """Register this agent in the shared registry."""
        now = datetime.now().isoformat()

        entry = AgentEntry(
            agent_id=agent_id,
            name=name,
            version=version,
            laap_enabled=laap_enabled,
            profile=profile,
            pid=os.getpid(),
            capabilities=capabilities or [],
            current_task=current_task,
            host=platform.node(),
            started_at=now,
            last_heartbeat=now,
            endpoint=endpoint,
        )

        with self._lock:
            # Remove old entries with same agent_id
            to_remove = [k for k, v in self.agents.items()
                        if v.agent_id == agent_id and k != str(os.getpid())]
            for k in to_remove:
                del self.agents[k]

            self.agents[str(os.getpid())] = entry
            self._save()

        return entry

    def heartbeat(self):
        """Update heartbeat timestamp."""
        now = datetime.now().isoformat()
        with self._lock:
            pid = str(os.getpid())
            if pid in self.agents:
                self.agents[pid].last_heartbeat = now
                self.agents[pid].status = "online"
                self._save()

    def update_task(self, task_description: str):
        """Update current task for this agent."""
        with self._lock:
            pid = str(os.getpid())
            if pid in self.agents:
                self.agents[pid].current_task = task_description
                self._save()

    def discover_all(self) -> Dict[str, List[AgentEntry]]:
        """
        Discover ALL agents across all versions.

        Returns:
          {"laap": [...], "hermes_native": [...], "unknown": [...]}
        """
        all_agents = self._merge_with_process_discovery()

        categorized = {
            "laap": [],
            "hermes_native": [],
            "unknown": [],
        }

        for agent in all_agents.values():
            if agent.laap_enabled:
                categorized["laap"].append(agent)
            elif "hermes" in agent.version.lower():
                categorized["hermes_native"].append(agent)
            else:
                categorized["unknown"].append(agent)

        return categorized

    def get_collaboration_partners(self) -> List[AgentEntry]:
        """Get agents this agent can collaborate with."""
        all_agents = self._merge_with_process_discovery()
        my_pid = str(os.getpid())
        partners = []

        for pid, agent in all_agents.items():
            if pid != my_pid and agent.is_alive():
                partners.append(agent)

        # Sort: LAAP agents first (richer collaboration)
        partners.sort(key=lambda a: (not a.laap_enabled, a.version))
        return partners

    def _merge_with_process_discovery(self) -> Dict[str, AgentEntry]:
        """Merge registry entries with process-level discovery."""
        with self._lock:
            merged = dict(self.agents)

        # Discover non-LAAP Hermes processes
        discovered = self._discover_hermes_processes()
        for pid, entry in discovered.items():
            if pid not in merged:
                merged[pid] = entry

        return merged

    def _discover_hermes_processes(self) -> Dict[str, AgentEntry]:
        """Find running Hermes processes via OS process listing."""
        discovered = {}

        try:
            if platform.system() == "Windows":
                result = subprocess.run(
                    ["wmic", "process", "where", "name='python.exe'",
                     "get", "ProcessId,CommandLine", "/format:csv"],
                    capture_output=True, text=True, timeout=10
                )
                for line in result.stdout.split('\n'):
                    if 'hermes' in line.lower() or 'laap' in line.lower():
                        parts = line.strip().split(',')
                        if len(parts) >= 2:
                            try:
                                pid = parts[-1].strip()
                                cmd = ','.join(parts[1:-1])
                                is_laap = 'laap' in cmd.lower()
                                discovered[pid] = AgentEntry(
                                    agent_id=f"discovered_{pid}",
                                    name="Hermes (discovered)",
                                    version="Hermes-Native" if not is_laap else "LAAP (unknown ver)",
                                    laap_enabled=is_laap,
                                    profile="unknown",
                                    pid=int(pid),
                                    status="online",
                                    host=platform.node(),
                                    started_at="unknown",
                                    last_heartbeat=datetime.now().isoformat(),
                                )
                            except Exception as e:
                                logger.debug(f"操作失败: {e}")
            else:  # Linux/macOS
                result = subprocess.run(
                    ["ps", "-eo", "pid,command"],
                    capture_output=True, text=True, timeout=10
                )
                for line in result.stdout.split('\n'):
                    if 'hermes' in line.lower() or 'laap' in line.lower():
                        parts = line.strip().split(None, 1)
                        if len(parts) >= 1:
                            try:
                                pid = parts[0]
                                is_laap = 'laap' in line.lower()
                                discovered[pid] = AgentEntry(
                                    agent_id=f"discovered_{pid}",
                                    name="Hermes (discovered)",
                                    version="Hermes-Native" if not is_laap else "LAAP (unknown ver)",
                                    laap_enabled=is_laap,
                                    profile="unknown",
                                    pid=int(pid),
                                    status="online",
                                    host=platform.node(),
                                    started_at="unknown",
                                    last_heartbeat=datetime.now().isoformat(),
                                )
                            except Exception as e:
                                logger.debug(f"操作失败: {e}")
        except Exception as e:
            logger.debug(f"Process discovery failed: {e}")

        return discovered

    def _load(self):
        if os.path.exists(self.REGISTRY_PATH):
            try:
                data = json.load(open(self.REGISTRY_PATH))
                for pid, entry_data in data.get("agents", {}).items():
                    self.agents[pid] = AgentEntry(**entry_data)
            except Exception as e:
                logger.debug(f"操作失败: {e}")
    def _save(self):
        try:
            data = {"agents": {pid: entry.__dict__ for pid, entry in self.agents.items()}}
            json.dump(data, open(self.REGISTRY_PATH, 'w'), indent=2)
        except Exception as e:
            logger.debug(f"操作失败: {e}")
    def cleanup_dead_agents(self, timeout_seconds: int = 120):
        """Remove agents that haven't heartbeated in timeout_seconds."""
        with self._lock:
            dead = [pid for pid, agent in self.agents.items()
                   if not agent.is_alive(timeout_seconds)]
            for pid in dead:
                del self.agents[pid]
            if dead:
                self._save()
                logger.info(f"Cleaned {len(dead)} dead agents from registry")

    def stats(self) -> Dict:
        all_agents = self._merge_with_process_discovery()
        categorized = {"laap": 0, "hermes_native": 0, "total": len(all_agents)}
        for agent in all_agents.values():
            if agent.laap_enabled:
                categorized["laap"] += 1
            else:
                categorized["hermes_native"] += 1
        return categorized


# ════════════════════════════════════════════════════════════
# Update Notifier — User-Facing Change Log
# ════════════════════════════════════════════════════════════

class UpdateLevel(str):
    CRITICAL = "critical"   # Architecture changes, major features
    FEATURE = "feature"     # New capabilities
    FIX = "fix"            # Bug fixes
    EVOLUTION = "evolution"  # Self-evolved changes
    CLEANUP = "cleanup"    # Code minimization, dead code removal


@dataclass
class UpdateRecord:
    update_id: str
    level: str  # UpdateLevel
    title: str
    description: str
    files_affected: List[str] = field(default_factory=list)
    before_snapshot: str = ""   # checksum
    after_snapshot: str = ""    # checksum
    auto_applied: bool = False
    timestamp: str = ""


class UpdateNotifier:
    """
    Tracks and notifies user of significant changes.

    1. Records every self-evolution step
    2. Records every manual significant change
    3. On startup, shows "Since last session: ..."
    4. Pending notifications accumulate until user acknowledges
    """

    UPDATES_PATH = os.path.join(
        os.path.expanduser("~"), ".laap", "updates.json"
    )
    PENDING_PATH = os.path.join(
        os.path.expanduser("~"), ".laap", "pending_updates.json"
    )

    def __init__(self):
        self.updates: List[UpdateRecord] = []
        self.pending: List[UpdateRecord] = []
        self.last_user_seen: str = ""  # ISO timestamp
        os.makedirs(os.path.dirname(self.UPDATES_PATH), exist_ok=True)
        self._load()

    def notify(self, level: str, title: str, description: str,
               files_affected: List[str] = None,
               before_snapshot: str = "",
               after_snapshot: str = "",
               auto_applied: bool = False) -> UpdateRecord:
        """Record an update. User will see this next time they look."""
        record = UpdateRecord(
            update_id=str(uuid.uuid4())[:8],
            level=level,
            title=title,
            description=description,
            files_affected=files_affected or [],
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
            auto_applied=auto_applied,
            timestamp=datetime.now().isoformat(),
        )
        self.updates.append(record)
        self.pending.append(record)
        self._save()

        # Log for immediate visibility
        prefix = {
            UpdateLevel.CRITICAL: "[!!!] ",
            UpdateLevel.FEATURE: "[NEW] ",
            UpdateLevel.FIX: "[FIX] ",
            UpdateLevel.EVOLUTION: "[EVO] ",
            UpdateLevel.CLEANUP: "[CLN] ",
        }.get(level, "[*] ")

        logger.info(f"{prefix}{title}: {description[:100]}")
        return record

    def get_since_last_session(self) -> List[UpdateRecord]:
        """Get all updates since user's last session."""
        if not self.last_user_seen:
            return self.pending[-10:]  # Last 10 if no baseline

        result = []
        for u in self.pending:
            if u.timestamp > self.last_user_seen:
                result.append(u)
        return result

    def get_pending_count(self) -> int:
        return len(self.get_since_last_session())

    def mark_as_seen(self):
        """User has seen current updates."""
        self.last_user_seen = datetime.now().isoformat()
        self.pending = []
        self._save()

    def format_startup_summary(self) -> str:
        """Formatted summary for agent startup."""
        since_last = self.get_since_last_session()
        if not since_last:
            return ""

        lines = ["", "═══ LAAP AGI — 更新摘要 ═══", ""]

        counts = defaultdict(int)
        for u in since_last:
            counts[u.level] += 1

        summary_parts = []
        if counts[UpdateLevel.CRITICAL] > 0:
            summary_parts.append(f"{counts[UpdateLevel.CRITICAL]} 重大更新")
        if counts[UpdateLevel.FEATURE] > 0:
            summary_parts.append(f"{counts[UpdateLevel.FEATURE]} 新功能")
        if counts[UpdateLevel.FIX] > 0:
            summary_parts.append(f"{counts[UpdateLevel.FIX]} 修复")
        if counts[UpdateLevel.EVOLUTION] > 0:
            summary_parts.append(f"{counts[UpdateLevel.EVOLUTION]} 自我进化")
        if counts[UpdateLevel.CLEANUP] > 0:
            summary_parts.append(f"{counts[UpdateLevel.CLEANUP]} 代码清理")

        lines.append(f"  自上次会话以来: {', '.join(summary_parts)}")
        lines.append("")

        for u in since_last[-5:]:  # Show last 5 in detail
            prefix = {
                UpdateLevel.CRITICAL: "✶",
                UpdateLevel.FEATURE: "+",
                UpdateLevel.FIX: "✓",
                UpdateLevel.EVOLUTION: "⚡",
                UpdateLevel.CLEANUP: "−",
            }.get(u.level, "•")

            auto = "[自动]" if u.auto_applied else "[手动]"
            lines.append(f"  {prefix} {u.title} {auto}")
            if u.files_affected:
                lines.append(f"    文件: {', '.join(u.files_affected[:3])}")

        lines.append("")
        lines.append(f"  输入 /updates 查看完整变更日志")
        lines.append("═" * 50)
        return "\n".join(lines)

    def generate_changelog_markdown(self, count: int = 20) -> str:
        """Generate CHANGELOG.md entry for recent updates."""
        lines = ["# 更新日志\n"]
        for u in sorted(self.updates, key=lambda x: x.timestamp, reverse=True)[:count]:
            date = u.timestamp[:10] if u.timestamp else "?"
            lines.append(f"## [{date}] {u.title}")
            lines.append(f"- **级别**: {u.level}")
            lines.append(f"- **描述**: {u.description}")
            if u.files_affected:
                lines.append(f"- **文件**: {', '.join(u.files_affected)}")
            lines.append(f"- **自动**: {'是' if u.auto_applied else '否'}")
            lines.append("")
        return "\n".join(lines)

    def _load(self):
        try:
            if os.path.exists(self.UPDATES_PATH):
                data = json.load(open(self.UPDATES_PATH))
                self.updates = [UpdateRecord(**u) for u in data.get("updates", [])]
                self.last_user_seen = data.get("last_seen", "")
            if os.path.exists(self.PENDING_PATH):
                data = json.load(open(self.PENDING_PATH))
                self.pending = [UpdateRecord(**u) for u in data.get("pending", [])]
        except Exception as e:
            logger.debug(f"操作失败: {e}")
    def _save(self):
        try:
            data = {
                "updates": [u.__dict__ for u in self.updates[-100:]],  # Keep last 100
                "last_seen": self.last_user_seen,
            }
            json.dump(data, open(self.UPDATES_PATH, 'w'), indent=2)

            data2 = {"pending": [u.__dict__ for u in self.pending]}
            json.dump(data2, open(self.PENDING_PATH, 'w'), indent=2)
        except Exception as e:
            logger.debug(f"操作失败: {e}")
    def stats(self) -> Dict:
        return {
            "total_updates": len(self.updates),
            "pending": len(self.pending),
            "since_last": self.get_pending_count(),
            "levels": {level: sum(1 for u in self.updates if u.level == level)
                      for level in [UpdateLevel.CRITICAL, UpdateLevel.FEATURE,
                                    UpdateLevel.FIX, UpdateLevel.EVOLUTION,
                                    UpdateLevel.CLEANUP]},
        }


# ════════════════════════════════════════════════════════════
# Version-Aware Integration
# ════════════════════════════════════════════════════════════

def integrate_cross_version(agent) -> Dict[str, Any]:
    """
    Wire up cross-version awareness to an agent.

    Returns summary of what was found.
    """
    registry = SharedRegistry()
    notifier = UpdateNotifier()

    # Store on agent
    agent.shared_registry = registry
    agent.update_notifier = notifier

    # Register this agent
    version = getattr(agent, 'version', '3.0.0')
    name = getattr(agent, 'name', 'Ao')

    registry.register(
        agent_id=name,
        name=name,
        version=f"LAAP v{version}",
        laap_enabled=True,
        profile=os.environ.get("HERMES_PROFILE", "laap-avatar"),
        capabilities=["coding", "debugging", "evolution", "self_healing",
                     "code_minimization", "quality_assurance", "swarm"],
        current_task="Initializing",
    )

    # Discover other agents
    all_agents = registry.discover_all()
    partners = registry.get_collaboration_partners()

    logger.info(
        f"Cross-version awareness: {len(partners)} partners, "
        f"{all_agents['laap'].__len__()} LAAP, "
        f"{all_agents['hermes_native'].__len__()} native Hermes"
    )

    # Show startup summary if there are pending updates
    startup_msg = notifier.format_startup_summary()
    if startup_msg:
        logger.info(startup_msg)

    return {
        "this_agent": f"LAAP v{version}",
        "partners_found": len(partners),
        "laap_agents": len(all_agents["laap"]),
        "native_hermes": len(all_agents["hermes_native"]),
        "pending_updates": notifier.get_pending_count(),
        "registry_path": registry.REGISTRY_PATH,
    }
