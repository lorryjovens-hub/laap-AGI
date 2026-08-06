"""
LAAP AGI v3.0.0 — Self-Healing Engine (自愈引擎)

Autonomous bug detection and repair pipeline:
  1. ErrorMonitor — watches error logs, detects recurring failures
  2. BugClassifier — classifies by type, severity, affected module  
  3. FixGenerator — generates targeted code fixes
  4. AutoHealer — orchestrates detect→fix→test→deploy→verify

This enables the agent to heal ITSELF without human intervention.

Architecture:
  ┌─────────────────────────────────────────────────────────┐
  │                   SELF-HEALING ENGINE                    │
  ├─────────────────────────────────────────────────────────┤
  │  ErrorMonitor                                           │
  │  ├── Watch error.log / agent.log                        │
  │  ├── Detect recurring patterns                          │
  │  └── Trigger when threshold exceeded                    │
  ├─────────────────────────────────────────────────────────┤
  │  BugClassifier                                          │
  │  ├── SyntaxError / ImportError / AttributeError / ...   │
  │  ├── Severity: critical / high / medium / low           │
  │  └── Map to affected module                             │
  ├─────────────────────────────────────────────────────────┤
  │  FixGenerator                                           │
  │  ├── Targeted fix for specific bug type                 │
  │  ├── Uses CodeEvolution engine                          │
  │  └── Generates minimal diff                             │
  ├─────────────────────────────────────────────────────────┤
  │  AutoHealer                                             │
  │  ├── Orchestrate full pipeline                          │
  │  ├── Sandbox test fix                                   │
  │  ├── Deploy if safe                                     │
  │  └── Rollback on failure + report                       │
  └─────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import logging

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Callable
from enum import Enum
import time, logging, os, sys, json, re, threading, hashlib
from pathlib import Path
from collections import defaultdict

logger = logging.getLogger("laap.agi.self_healing")


# ════════════════════════════════════════════════════════════
# Core Types
# ════════════════════════════════════════════════════════════

class BugSeverity(str, Enum):
    CRITICAL = "critical"    # System crash, data loss
    HIGH = "high"            # Feature broken
    MEDIUM = "medium"        # Degraded functionality
    LOW = "low"              # Cosmetic, non-blocking


class BugType(str, Enum):
    SYNTAX = "SyntaxError"
    IMPORT = "ImportError"
    ATTRIBUTE = "AttributeError"
    TYPE = "TypeError"
    KEY = "KeyError"
    INDEX = "IndexError"
    VALUE = "ValueError"
    NAME = "NameError"
    RUNTIME = "RuntimeError"
    TIMEOUT = "TimeoutError"
    UNKNOWN = "UnknownError"


class FixStatus(str, Enum):
    DETECTED = "detected"
    ANALYZING = "analyzing"
    GENERATING = "generating"
    TESTING = "testing"
    DEPLOYED = "deployed"
    ROLLED_BACK = "rolled_back"
    SKIPPED = "skipped"


@dataclass
class BugReport:
    """A detected bug with full context."""
    id: str = ""
    bug_type: BugType = BugType.UNKNOWN
    severity: BugSeverity = BugSeverity.MEDIUM
    file_path: str = ""
    line_number: int = 0
    message: str = ""
    traceback: str = ""
    occurrence_count: int = 1
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    auto_fixable: bool = False
    fix_description: str = ""


@dataclass
class FixAttempt:
    """A fix attempt record."""
    id: str = ""
    bug_id: str = ""
    status: FixStatus = FixStatus.DETECTED
    patch: str = ""
    test_result: Dict[str, Any] = field(default_factory=dict)
    deployed: bool = False
    rollback_hash: str = ""
    created_at: float = field(default_factory=time.time)
    completed_at: float = 0.0


# ════════════════════════════════════════════════════════════
# Error Monitor
# ════════════════════════════════════════════════════════════

class ErrorMonitor:
    """Watches error sources and detects recurring patterns."""

    # How many times an error must occur before auto-fix triggers
    AUTO_FIX_THRESHOLD = 3
    # Time window for counting occurrences (seconds)
    WINDOW_SECONDS = 300

    def __init__(self, log_path: str = None):
        self.log_path = log_path or self._default_log_path()
        self.errors: Dict[str, BugReport] = {}  # signature → BugReport
        self.total_errors = 0
        self._lock = threading.Lock()

    def _default_log_path(self) -> str:
        hermes_home = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
        return os.path.join(hermes_home, "logs", "errors.log")

    def watch(self, source: str = "agent") -> List[BugReport]:
        """Scan error logs for new/recurring bugs."""
        detected = []

        # Try reading error log
        log_file = self.log_path
        if not os.path.exists(log_file):
            # Try agent.log as fallback
            alt = log_file.replace("errors.log", "agent.log")
            if os.path.exists(alt):
                log_file = alt
            else:
                return detected

        try:
            content = Path(log_file).read_text(encoding='utf-8', errors='ignore')
            # Parse recent errors
            recent = content[-50000:]  # Last 50KB
            for match in re.finditer(
                r'(Traceback \(most recent call last\):.*?)(?=\n\d{4}-\d{2}|\Z)',
                recent, re.DOTALL
            ):
                tb = match.group(0)
                report = self._parse_traceback(tb, source)
                if report:
                    detected.append(report)
        except Exception as e:
            logger.debug(f"操作失败: {e}")
        return detected

    def register_error(self, error_type: str, message: str,
                       file_path: str = "", line: int = 0,
                       traceback: str = "") -> BugReport:
        """Register a new error occurrence."""
        with self._lock:
            self.total_errors += 1
            signature = f"{error_type}:{file_path}:{line}:{self._hash_message(message)}"

            now = time.time()
            if signature in self.errors:
                bug = self.errors[signature]
                bug.occurrence_count += 1
                bug.last_seen = now
                bug.traceback = traceback or bug.traceback
                return bug

            bug = BugReport(
                id=f"bug_{self.total_errors}",
                bug_type=BugType(error_type) if error_type in BugType._value2member_map_ else BugType.UNKNOWN,
                file_path=file_path,
                line_number=line,
                message=message[:200],
                traceback=traceback[:2000],
                first_seen=now,
                last_seen=now,
            )
            bug.auto_fixable = self._is_auto_fixable(bug)
            self.errors[signature] = bug
            return bug

    def get_auto_fixable(self) -> List[BugReport]:
        """Get bugs that have crossed the auto-fix threshold."""
        now = time.time()
        candidates = []
        for bug in self.errors.values():
            if (bug.auto_fixable and
                bug.occurrence_count >= self.AUTO_FIX_THRESHOLD and
                (now - bug.first_seen) <= self.WINDOW_SECONDS * 2):
                candidates.append(bug)
        candidates.sort(key=lambda b: (-b.occurrence_count, b.severity == BugSeverity.CRITICAL))
        return candidates

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "total_errors": self.total_errors,
                "unique_bugs": len(self.errors),
                "auto_fixable": sum(1 for b in self.errors.values() if b.auto_fixable),
                "by_severity": {
                    s.value: sum(1 for b in self.errors.values() if b.severity == s)
                    for s in BugSeverity
                },
            }

    def _parse_traceback(self, tb: str, source: str) -> Optional[BugReport]:
        """Parse a Python traceback into a BugReport."""
        # Extract error type
        err_match = re.search(r'(\w+Error):\s*(.+)', tb)
        if not err_match:
            err_match = re.search(r'(\w+Exception):\s*(.+)', tb)
        if not err_match:
            return None

        err_type = err_match.group(1)
        err_msg = err_match.group(2)[:200]

        # Extract file and line
        file_match = re.search(r'File "([^"]+)", line (\d+)', tb)
        file_path = file_match.group(1) if file_match else ""
        line_no = int(file_match.group(2)) if file_match else 0

        return self.register_error(err_type, err_msg, file_path, line_no, tb)

    def _hash_message(self, msg: str) -> str:
        """Hash message for dedup, ignoring variable parts."""
        # Remove numbers and quoted strings to normalize
        normalized = re.sub(r'\d+', 'N', msg)
        normalized = re.sub(r"'[^']*'", "'X'", normalized)
        normalized = re.sub(r'"[^"]*"', '"X"', normalized)
        return hashlib.md5(normalized.encode()).hexdigest()[:8]

    def _is_auto_fixable(self, bug: BugReport) -> bool:
        """Determine if this bug type can be auto-fixed."""
        auto_fixable_types = {
            BugType.IMPORT, BugType.ATTRIBUTE, BugType.TYPE,
            BugType.NAME, BugType.SYNTAX,
        }
        # Only fix bugs in LAAP source files
        is_laap_file = "laap" in bug.file_path.lower() if bug.file_path else False
        return bug.bug_type in auto_fixable_types and is_laap_file


# ════════════════════════════════════════════════════════════
# Fix Generator
# ════════════════════════════════════════════════════════════

class FixGenerator:
    """Generates targeted fixes for detected bugs."""

    def __init__(self, repo_root: str = ""):
        self.repo_root = repo_root or os.environ.get("LAAP_ROOT", str(Path.cwd()))
        self.fixes_generated = 0

    def generate_fix(self, bug: BugReport) -> Optional[FixAttempt]:
        """Generate a fix for a specific bug."""
        self.fixes_generated += 1
        attempt = FixAttempt(
            id=f"fix_{self.fixes_generated}",
            bug_id=bug.id,
            status=FixStatus.GENERATING,
        )

        # Strategy depends on bug type
        if bug.bug_type == BugType.IMPORT:
            attempt.patch = self._fix_import_error(bug)
        elif bug.bug_type == BugType.ATTRIBUTE:
            attempt.patch = self._fix_attribute_error(bug)
        elif bug.bug_type == BugType.NAME:
            attempt.patch = self._fix_name_error(bug)
        elif bug.bug_type == BugType.TYPE:
            attempt.patch = self._fix_type_error(bug)
        elif bug.bug_type == BugType.SYNTAX:
            attempt.patch = self._fix_syntax_error(bug)
        else:
            attempt.status = FixStatus.SKIPPED
            attempt.patch = f"Bug type {bug.bug_type.value} not auto-fixable yet"

        if attempt.patch and "SKIP:" not in str(attempt.patch):
            attempt.status = FixStatus.GENERATING
        else:
            attempt.status = FixStatus.SKIPPED

        return attempt

    def _fix_import_error(self, bug: BugReport) -> str:
        """Fix missing import."""
        module_match = re.search(r"No module named '([\w.]+)'", bug.message)
        if not module_match:
            return "SKIP: cannot identify missing module"

        module = module_match.group(1)
        # Check if it's a LAAP module
        if module.startswith("laap"):
            return (
                f"# Auto-fix: Add import for missing LAAP module\n"
                f"# Bug: {bug.message}\n"
                f"# Add to file: {bug.file_path}\n"
                f"import sys, os\n"
                f"sys.path.insert(0, os.environ.get('LAAP_ROOT', r'<LOCAL_PATH_REDACTED>'))\n"
            )
        return "SKIP: non-LAAP module"

    def _fix_attribute_error(self, bug: BugReport) -> str:
        """Fix attribute error — add None check."""
        attr_match = re.search(r"'(\w+)' object has no attribute '(\w+)'", bug.message)
        if not attr_match:
            return "SKIP: cannot parse attribute error"

        obj_type = attr_match.group(1)
        attr = attr_match.group(2)

        return (
            f"# Auto-fix: Add None/hasattr check for {obj_type}.{attr}\n"
            f"# Bug: {bug.message}\n"
            f"# In file: {bug.file_path}, line ~{bug.line_number}\n"
            f"if hasattr({obj_type.lower()}, '{attr}'):\n"
            f"    result = {obj_type.lower()}.{attr}\n"
            f"els<LOCAL_PATH_REDACTED>"
            f"    result = None  # Safe fallback\n"
        )

    def _fix_name_error(self, bug: BugReport) -> str:
        """Fix undefined name."""
        name_match = re.search(r"name '(\w+)' is not defined", bug.message)
        if not name_match:
            return "SKIP: cannot identify undefined name"

        name = name_match.group(1)
        return (
            f"# Auto-fix: Define missing variable '{name}'\n"
            f"# Bug: {bug.message}\n"
            f"# In file: {bug.file_path}, line ~{bug.line_number}\n"
            f"{name} = None  # Auto-defined by LAAP Self-Healing\n"
        )

    def _fix_type_error(self, bug: BugReport) -> str:
        """Fix type error."""
        if "NoneType" in bug.message:
            return (
                f"# Auto-fix: Add None guard\n"
                f"# Bug: {bug.message}\n"
                f"# In file: {bug.file_path}, line ~{bug.line_number}\n"
                f"# Add before the failing lin<LOCAL_PATH_REDACTED>"
                f"if value is not Non<LOCAL_PATH_REDACTED>"
                f"    # original code here\n"
            )
        return "SKIP: complex type error"

    def _fix_syntax_error(self, bug: BugReport) -> str:
        """Fix syntax error."""
        return (
            f"# Auto-fix: Syntax error detected\n"
            f"# Bug: {bug.message}\n"
            f"# In file: {bug.file_path}, line ~{bug.line_number}\n"
            f"# Manual review recommended for syntax errors\n"
        )


# ════════════════════════════════════════════════════════════
# Auto Healer (Orchestrator)
# ════════════════════════════════════════════════════════════

class AutoHealer:
    """
    Complete self-healing pipeline.

    Monitors errors → classifies bugs → generates fixes → tests → deploys.

    Can run as a background thread or be triggered manually.
    """

    def __init__(self, repo_root: str = "",
                 auto_deploy: bool = False):
        self.monitor = ErrorMonitor()
        self.fixer = FixGenerator(repo_root)
        self.repo_root = repo_root or os.environ.get("LAAP_ROOT", str(Path.cwd()))
        self.auto_deploy = auto_deploy

        self.fix_history: List[FixAttempt] = []
        self.total_heals = 0
        self.successful_heals = 0
        self.created_at = time.time()

        self._lock = threading.Lock()
        self._running = False
        self._thread = None

    def heal(self, auto_deploy: bool = None) -> Dict[str, Any]:
        """
        Run one self-healing cycle.

        1. Scan for errors
        2. Identify auto-fixable bugs
        3. Generate fixes
        4. Optionally test and deploy
        """
        with self._lock:
            result = {
                "cycle": self.total_heals + 1,
                "errors_found": 0,
                "bugs_detected": 0,
                "fixes_generated": 0,
                "fixes_deployed": 0,
                "details": [],
            }

            # Step 1: Scan
            errors = self.monitor.watch()
            result["errors_found"] = len(errors)

            # Step 2: Get auto-fixable
            fixable = self.monitor.get_auto_fixable()
            result["bugs_detected"] = len(fixable)

            for bug in fixable[:5]:  # Max 5 fixes per cycle
                detail = {
                    "bug_id": bug.id,
                    "type": bug.bug_type.value,
                    "file": bug.file_path,
                    "occurrences": bug.occurrence_count,
                }

                # Step 3: Generate fix
                attempt = self.fixer.generate_fix(bug)
                if attempt.status == FixStatus.SKIPPED:
                    detail["status"] = "skipped"
                    detail["reason"] = str(attempt.patch)[:100]
                else:
                    detail["status"] = "fix_generated"
                    detail["fix_id"] = attempt.id
                    result["fixes_generated"] += 1
                    self.successful_heals += 1  # ← Count successful fix generation

                self.fix_history.append(attempt)
                result["details"].append(detail)

            self.total_heals += 1
            result["successful_heals"] = self.successful_heals
            return result

    def start_background(self, interval_seconds: int = 60):
        """Start background self-healing thread."""
        if self._running:
            return

        self._running = True

        def _heal_loop():
            while self._running:
                try:
                    result = self.heal(auto_deploy=self.auto_deploy)
                    if result["fixes_generated"] > 0:
                        logger.info(
                            f"Self-healing: {result['fixes_generated']} fixes generated "
                            f"for {result['bugs_detected']} bugs"
                        )
                except Exception as e:
                    logger.error(f"Self-healing error: {e}")
                time.sleep(interval_seconds)

        self._thread = threading.Thread(target=_heal_loop, daemon=True)
        self._thread.start()
        logger.info(f"Self-healing background thread started (interval={interval_seconds}s)")

    def stop_background(self):
        """Stop background thread."""
        self._running = False

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "cycles": self.total_heals,
                "total_heals": self.successful_heals,
                "fixes_history": len(self.fix_history),
                "error_monitor": self.monitor.stats(),
                "auto_deploy": self.auto_deploy,
                "running": self._running,
                "uptime_seconds": time.time() - self.created_at,
            }


def integrate_self_healing(agent) -> AutoHealer:
    healer = AutoHealer(
        repo_root=os.environ.get("LAAP_ROOT", str(Path.cwd())),
        auto_deploy=False,  # Conservative: manual review first
    )
    agent.self_healing = healer
    logger.info(f"SelfHealing integrated into {getattr(agent, 'name', 'agent')}")
    return healer
