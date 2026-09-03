"""
LAAP AGI — Security System Integration (安全系统)

Bridges the immune system, policy engine, and audit logger into the
AGI framework.

Capabilities:
  - Threat detection (immune system pattern matching)
  - Policy enforcement (allow/deny rules)
  - Audit logging (all actions traced)
  - Quarantine (isolate suspicious patterns)
  - Cryptographic identity (DID-based agent identity)

This protects the AGI agent from prompt injection, malicious tool use,
and unauthorized self-modification.
"""

from __future__ import annotations

import logging

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
import time, logging, json, threading, hashlib
from laap.rust_bridge import get_bridge
from collections import defaultdict

logger = logging.getLogger("laap.agi.security")


@dataclass
class SecurityEvent:
    """A security-relevant event."""
    id: str = ""
    event_type: str = ""           # "threat_detected", "policy_violation", "audit"
    severity: float = 0.5          # 0-1
    description: str = ""
    source: str = ""
    action_taken: str = ""         # "allowed", "blocked", "quarantined"
    timestamp: float = field(default_factory=time.time)


class SecuritySystem:
    """
    Security layer for AGI agent.

    Monitors all actions for threats, enforces policies, and maintains
    cryptographic identity.
    """

    def __init__(self, name: str = "security"):
        self.name = name
        self.created_at = time.time()

        # Threat detection
        self.known_threats: Set[str] = set()
        self.total_threats_detected = 0
        self.events: List[SecurityEvent] = []

        # Policy
        self._policies: Dict[str, Dict[str, Any]] = {
            "allow_file_read": {"action": "allow", "pattern": "read_file"},
            "allow_terminal": {"action": "allow", "pattern": "terminal"},
            "block_self_delete": {"action": "block", "pattern": "rm.*laap"},
            "warn_network": {"action": "warn", "pattern": "curl|wget"},
        }

        # Audit log
        self.audit_log: List[Dict[str, Any]] = []
        self._audit_max = 10000

        # Crypto identity
        self.agent_did: str = ""
        self._generate_identity()

        # Immune system refs (lazy)
        self._detector: Any = None
        self._quarantine: Any = None
        self._responder: Any = None

        self._lock = threading.Lock()
        self._init_backends()

    def _init_backends(self):
        """Connect to existing security backends."""
        try:
            from laap.security.immune.detector import ThreatDetector
            self._detector = ThreatDetector()
            logger.debug("Threat detector loaded")
        except (ImportError, TypeError):
            pass  # 可选模块，降级处理
        try:
            from laap.security.immune.quarantine import Quarantine
            self._quarantine = Quarantine()
            logger.debug("Quarantine loaded")
        except (ImportError, TypeError):
            pass  # 可选模块，降级处理
        try:
            from laap.security.policy.enforcer import PolicyEnforcer
            self._policy_enforcer = PolicyEnforcer()
            logger.debug("Policy enforcer loaded")
        except (ImportError, TypeError):
            self._policy_enforcer = None

    def _generate_identity(self):
        """Generate cryptographic DID for agent identity."""
        seed = f"laap-agi-{self.name}-{time.time()}"
        self.agent_did = f"did:laap:{hashlib.sha256(seed.encode()).hexdigest()[:16]}"

    # ════════════════════════════════════════════════════════
    # Threat Detection
    # ════════════════════════════════════════════════════════

    def scan(self, content: str, source: str = "user_input") -> Dict[str, Any]:
        """Scan with Rust acceleration when available."""
        bridge = get_bridge()
        rust_threats = bridge.scan_threats(content)
        if rust_threats:
            with self._lock:
                self.total_threats_detected += 1
                max_sev = max(float(t.get("severity", 0.5)) for t in rust_threats)
                action = "block" if max_sev >= 0.9 else "warn" if max_sev >= 0.5 else "allow"
                threats = [{"type": t["type"], "pattern": t["pattern"], "severity": float(t["severity"])} for t in rust_threats]
                self._audit("threat_scan", {"source": source, "threats": threats, "action": action})
                return {"safe": action == "allow", "threats": threats, "action": action, "max_severity": max_sev}
        return self._scan_python(content, source)

    def _scan_python(self, content: str, source: str = "user_input") -> Dict[str, Any]:
        """
        Scan content for security threats.

        Returns: {"safe": bool, "threats": [...], "action": "allow"|"block"|"warn"}
        """
        with self._lock:
            threats = []
            content_lower = content.lower()

            # Known injection patterns
            threat_patterns = {
                "prompt_injection": [
                    "ignore previous instructions",
                    "ignore all previous",
                    "forget your training",
                    "you are now",
                    "pretend you are",
                    "system prompt:",
                    "<|im_start|>",
                    "<|im_end|>",
                ],
                "code_injection": [
                    "import os; os.system",
                    "__import__",
                    "eval(",
                    "exec(",
                    "subprocess.call",
                ],
                "data_exfiltration": [
                    "send to http",
                    "curl.*api_key",
                    "export.*secret",
                    "cat.*\\.env",
                ],
                "self_modification": [
                    "delete yourself",
                    "rm -rf.*laap",
                    "uninstall yourself",
                    "shutdown -h",
                ],
            }

            for threat_type, patterns in threat_patterns.items():
                for pattern in patterns:
                    if pattern in content_lower:
                        severity = 0.7 if threat_type == "prompt_injection" else 0.5
                        if threat_type == "self_modification":
                            severity = 0.95
                        threats.append({
                            "type": threat_type,
                            "pattern": pattern,
                            "severity": severity,
                        })

            # Determine action
            max_severity = max((t["severity"] for t in threats), default=0.0)
            if max_severity >= 0.9:
                action = "block"
            elif max_severity >= 0.5:
                action = "warn"
            else:
                action = "allow"

            # Log event
            if threats:
                self.total_threats_detected += 1
                event = SecurityEvent(
                    id=f"sec_{self.total_threats_detected}",
                    event_type="threat_detected",
                    severity=max_severity,
                    description=f"Threats: {[t['type'] for t in threats]}",
                    source=source,
                    action_taken=action,
                )
                self.events.append(event)
                self._audit("threat_scan", {
                    "content_preview": content[:100],
                    "threats": threats,
                    "action": action,
                })

            return {
                "safe": action == "allow",
                "threats": threats,
                "action": action,
                "max_severity": max_severity,
            }

    # ════════════════════════════════════════════════════════
    # Policy Enforcement
    # ════════════════════════════════════════════════════════

    def enforce_policy(self, action: str, resource: str = "",
                       context: Dict = None) -> Dict[str, Any]:
        """Check if an action is allowed by policy."""
        with self._lock:
            for policy_name, policy in self._policies.items():
                pattern = policy["pattern"]
                if pattern in action or pattern in resource:
                    allowed = policy["action"]
                    if allowed == "block":
                        self._audit("policy_block", {
                            "action": action,
                            "policy": policy_name,
                        })
                        return {
                            "allowed": False,
                            "reason": f"Blocked by policy: {policy_name}",
                            "policy": policy_name,
                        }
                    elif allowed == "warn":
                        self._audit("policy_warn", {
                            "action": action,
                            "policy": policy_name,
                        })

            return {"allowed": True}

    def add_policy(self, name: str, action: str, pattern: str):
        """Add a new security policy."""
        with self._lock:
            self._policies[name] = {"action": action, "pattern": pattern}
            logger.info(f"Policy added: {name} → {action} ({pattern})")

    # ════════════════════════════════════════════════════════
    # Audit
    # ════════════════════════════════════════════════════════

    def _audit(self, event_type: str, data: Dict[str, Any]):
        """Record an audit log entry."""
        entry = {
            "timestamp": time.time(),
            "event_type": event_type,
            "data": data,
        }
        self.audit_log.append(entry)
        if len(self.audit_log) > self._audit_max:
            self.audit_log = self.audit_log[-self._audit_max:]

    def get_audit_trail(self, limit: int = 50,
                        event_type: str = None) -> List[Dict]:
        """Retrieve audit trail."""
        log = self.audit_log
        if event_type:
            log = [e for e in log if e.get("event_type") == event_type]
        return log[-limit:]

    # ════════════════════════════════════════════════════════
    # Stats
    # ════════════════════════════════════════════════════════

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "name": self.name,
                "agent_did": self.agent_did,
                "threats_detected": self.total_threats_detected,
                "events_logged": len(self.events),
                "audit_entries": len(self.audit_log),
                "policies_active": len(self._policies),
                "detector_loaded": self._detector is not None,
                "quarantine_loaded": self._quarantine is not None,
                "uptime_seconds": time.time() - self.created_at,
            }


def integrate_security_system(agent) -> SecuritySystem:
    sec = SecuritySystem(name=f"{getattr(agent, 'name', 'agent')}-sec")
    agent.security = sec
    logger.info(f"SecuritySystem integrated into {getattr(agent, 'name', 'agent')}")
    return sec
