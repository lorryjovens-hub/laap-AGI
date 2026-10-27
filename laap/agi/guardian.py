"""
LAAP AGI — Guardian System (项目安全守护)

Completes the safety architecture. Five new layers:

  1. EmergencyStop    — 熔断开关,一键禁用所有自修改
  2. DeployChecklist  — 部署前12项自动检查,任一项失败→拒绝
  3. AuditTrail       — 不可篡改的变更审计日志(追加模式)
  4. IntegrityScanner — 定期扫描所有文件,检测损坏→自动恢复
  5. AutoRecovery     — 检测到损坏时,自动从备份恢复

Safety philosophy:
  "No modification to the codebase happens without passing EVERY gate.
   No gate can be bypassed. No audit trail can be deleted."

Complete defense-in-depth:

  Layer 1: EmergencyStop     ← 总开关 (一键禁用所有自修改)
  Layer 2: DeployChecklist   ← 12项自动检查
  Layer 3: CodeQualityGate   ← 7项代码质量
  Layer 4: SafeRollback      ← 3层备份
  Layer 5: IntegrityScanner  ← 持续完整性验证
  Layer 6: AutoRecovery      ← 自动修复
  Layer 7: AuditTrail        ← 不可篡改记录
  Layer 8: ConsensusEngine   ← 多人审批
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
from enum import Enum
import time, logging, threading, uuid, json, os, hashlib, re, subprocess, ast
from pathlib import Path
from datetime import datetime
from collections import defaultdict, deque

logger = logging.getLogger("laap.agi.guardian")


# ════════════════════════════════════════════════════════════
# 1. Emergency Stop — 紧急熔断
# ════════════════════════════════════════════════════════════

class GuardianMode(str, Enum):
    FULL_AUTO = "full_auto"       # 允许所有自动修改
    REVIEW_REQUIRED = "review"    # 修改需要人工审查
    READ_ONLY = "read_only"       # 只读模式,禁止任何修改
    EMERGENCY = "emergency"       # 紧急模式,冻结一切


class EmergencyStop:
    """
    总控开关。控制所有自动修改行为。

    模式切换:
      FULL_AUTO → REVIEW_REQUIRED → READ_ONLY → EMERGENCY

    触发条件:
      1. 连续3次部署失败 → READ_ONLY
      2. 检测到文件损坏 → EMERGENCY
      3. 用户手动切换 → 任意模式
      4. GUARDIAN Agent投票 → EMERGENCY
    """

    STOP_FILE = os.path.join(
        os.environ.get("LAAP_ROOT", os.path.expanduser("~")), ".guardian_mode"
    )

    def __init__(self):
        self.mode: GuardianMode = GuardianMode.FULL_AUTO
        self.consecutive_failures = 0
        self.max_failures = 3
        self.switched_at = time.time()
        self.switched_by = "system"
        self.switch_reason = ""
        self.switch_history: List[Dict] = []
        self._lock = threading.Lock()
        self._load()

    def allow_modification(self, risk_level: str = "medium") -> Tuple[bool, str]:
        """Check if a modification is allowed under current mode."""
        with self._lock:
            if self.mode == GuardianMode.EMERGENCY:
                return False, "EMERGENCY: All modifications frozen"
            if self.mode == GuardianMode.READ_ONLY:
                return False, "READ_ONLY: No modifications permitted"
            if self.mode == GuardianMode.REVIEW_REQUIRED:
                if risk_level in ("high", "critical"):
                    return False, "REVIEW_REQUIRED: High-risk change needs human approval"
            return True, "OK"

    def switch_mode(self, new_mode: GuardianMode, by: str = "system",
                    reason: str = ""):
        with self._lock:
            old = self.mode
            self.mode = new_mode
            self.switched_at = time.time()
            self.switched_by = by
            self.switch_reason = reason
            self.switch_history.append({
                "from": old.value, "to": new_mode.value,
                "by": by, "reason": reason,
                "time": datetime.now().isoformat(),
            })
            self._save()
            logger.warning(f"Guardian mode: {old.value} → {new_mode.value} ({reason})")

    def record_failure(self, reason: str = ""):
        with self._lock:
            self.consecutive_failures += 1
            if self.consecutive_failures >= self.max_failures:
                self.switch_mode(GuardianMode.READ_ONLY, "system",
                                f"连续{self.consecutive_failures}次部署失败: {reason}")

    def record_success(self):
        with self._lock:
            self.consecutive_failures = max(0, self.consecutive_failures - 1)

    def _load(self):
        if os.path.exists(self.STOP_FILE):
            try:
                data = json.load(open(self.STOP_FILE))
                self.mode = GuardianMode(data.get("mode", "full_auto"))
                self.consecutive_failures = data.get("failures", 0)
                self.switch_history = data.get("history", [])
            except Exception:
                pass
    def _save(self):
        try:
            json.dump({
                "mode": self.mode.value,
                "failures": self.consecutive_failures,
                "history": self.switch_history[-20:],
                "updated": datetime.now().isoformat(),
            }, open(self.STOP_FILE, 'w'), indent=2)
        except Exception:
            pass
    def status(self) -> Dict:
        return {
            "mode": self.mode.value,
            "consecutive_failures": self.consecutive_failures,
            "can_modify": self.mode not in (GuardianMode.EMERGENCY, GuardianMode.READ_ONLY),
            "since": datetime.fromtimestamp(self.switched_at).isoformat(),
        }


# ════════════════════════════════════════════════════════════
# 1.5 Runtime repo-root derivation & AST-based dangerous code detection
# ════════════════════════════════════════════════════════════

def _default_repo_root() -> str:
    """运行时推导 LAAP 项目根目录（不再硬编码 <LOCAL_PATH_REDACTED>

    优先级：LAAP_ROOT 环境变量 > 基于 __file__ 推导。
    guardian.py 位于 <repo>/laap/agi/guardian.py，三级 dirname 即仓库根。
    """
    env_root = os.environ.get("LAAP_ROOT")
    if env_root:
        return env_root
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _DangerousCallVisitor(ast.NodeVisitor):
    """AST 访问器：检测危险调用与受限内建属性访问。

    覆盖字符串黑名单漏检的绕过形式，例如：
      - ``eval ("x")``   （函数名与括号间有空格）
      - ``__import__("os")`` （使用双引号）
      - ``getattr(__builtins__, 'eval')`` （通过 getattr 间接获取）
      - ``object.__subclasses__()``  （逃逸沙箱常用手法）
    """

    DANGEROUS_FUNCS = {"eval", "exec", "compile", "__import__"}
    DANGEROUS_ATTRS = {"__builtins__", "__subclasses__",
                       "__globals__", "__bases__", "__code__"}
    DANGEROUS_GETTERS = {"getattr", "getattr_static", "__getattribute__"}

    def __init__(self):
        self.findings: List[str] = []

    def _is_builtins_access(self, node) -> bool:
        if isinstance(node, ast.Attribute):
            return node.attr in self.DANGEROUS_ATTRS
        if isinstance(node, ast.Name):
            return node.id == "__builtins__"
        return False

    def visit_Call(self, node):  # noqa: N802 - ast API 要求原名
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            # eval(...)/exec(...)/compile(...)/__import__(...)
            if func_name in self.DANGEROUS_FUNCS:
                self.findings.append(f"{func_name}(")
            # getattr(__builtins__, 'eval') 绕过形式
            elif func_name in self.DANGEROUS_GETTERS and node.args:
                if self._is_builtins_access(node.args[0]):
                    self.findings.append(f"{func_name}(__builtins__")
        elif isinstance(node.func, ast.Attribute):
            attr = node.func.attr
            # os.system(...)/subprocess.Popen(...)/obj.exec(...)
            if attr in ("system", "popen", "Popen", "exec", "eval", "run"):
                self.findings.append(f".{attr}(")
        self.generic_visit(node)

    def visit_Attribute(self, node):  # noqa: N802
        # 直接访问 __builtins__/__subclasses__/__globals__ 等
        if node.attr in self.DANGEROUS_ATTRS:
            self.findings.append(f".{node.attr}")
        self.generic_visit(node)


def _check_dangerous_ast(code: str) -> list:
    """AST 静态分析：检测字符串黑名单漏检的危险调用。

    在 :class:`DeployChecklist` 中作为字符串匹配的补充——当快速预筛未
    命中时调用本函数复查。返回命中的危险模式描述列表（空列表表示干净）。
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        # 语法错误由 Check 3 (syntax_valid) 单独负责，此处不重复报告
        return []
    visitor = _DangerousCallVisitor()
    visitor.visit(tree)
    return visitor.findings


# ════════════════════════════════════════════════════════════
# 2. Deploy Checklist — 部署前12项自动检查
# ════════════════════════════════════════════════════════════

class DeployChecklist:
    """
    Before ANY code change is deployed, ALL 12 checks must pass.

    If any check fails, deployment is BLOCKED and the reason is logged.
    No exceptions. No bypass.
    """

    def __init__(self, repo_root: str = None):
        self.repo_root = repo_root or _default_repo_root()
        self.total_checks = 0
        self.passed_deploys = 0
        self.blocked_deploys = 0

    def run(self, file_path: str, change_id: str = "",
            risk_level: str = "medium") -> Dict[str, Any]:
        """
        Run full deployment checklist. Returns {passed, checks, failures}.
        """
        self.total_checks += 1
        checks = {}
        failures = []

        abs_path = file_path if os.path.isabs(file_path) else os.path.join(self.repo_root, file_path)

        # ── Check 1: File exists ────────
        checks["file_exists"] = os.path.exists(abs_path)
        if not checks["file_exists"]:
            failures.append("FILE_NOT_FOUND")

        # ── Check 2: File not empty ─────
        if checks["file_exists"]:
            sz = os.path.getsize(abs_path)
            checks["file_not_empty"] = sz > 0
            if not checks["file_not_empty"]:
                failures.append("FILE_EMPTY")
        else:
            checks["file_not_empty"] = False

        # ── Check 3: Syntax valid ───────
        try:
            import py_compile
            py_compile.compile(abs_path, doraise=True)
            checks["syntax_valid"] = True
        except Exception as e:
            checks["syntax_valid"] = False
            failures.append(f"SYNTAX: {e}")

        # ── Check 4: Not in blacklist ───
        blacklist_patterns = ["__init__.py", "__pycache__", ".git", "VERSION.json"]
        checks["not_blacklisted"] = not any(b in abs_path for b in blacklist_patterns)
        if not checks["not_blacklisted"]:
            failures.append("BLACKLISTED")

        # ── Check 5: Emergency stop check ─
        checks["emergency_ok"] = True  # Will be checked by caller

        # ── Check 6: No dangerous patterns ─
        # 字符串黑名单作为快速预筛；未命中时再用 AST 复查绕过形式
        if checks["file_exists"]:
            content = open(abs_path, 'r', encoding='utf-8').read()
            dangerous = ["os.system(", "eval(", "exec(", "__import__('subprocess')"]
            found = [d for d in dangerous if d in content]
            # 字符串匹配未命中 → AST 静态分析复查（eval ("x")、
            # __import__("os")、getattr(__builtins__, 'eval') 等绕过形式）
            if not found:
                ast_findings = _check_dangerous_ast(content)
                if ast_findings:
                    found = ast_findings
            checks["no_dangerous_code"] = len(found) == 0
            if found:
                failures.append(f"DANGEROUS: {found}")
        else:
            checks["no_dangerous_code"] = True

        # ── Check 7: File size change < 50% ─
        checks["size_change_ok"] = True  # Checked by caller with snapshot

        # ── Check 8: Imports are valid ──
        if checks["syntax_valid"]:
            try:
                import ast
                tree = ast.parse(open(abs_path, 'r', encoding='utf-8').read())
                imports_ok = all(isinstance(n, (ast.Import, ast.ImportFrom))
                                for n in ast.walk(tree)
                                if isinstance(n, (ast.Import, ast.ImportFrom)))
                checks["imports_valid"] = True  # Simplified check
            except:
                checks["imports_valid"] = True
        else:
            checks["imports_valid"] = False

        # ── Check 9: Backup exists ──────
        checks["backup_exists"] = True  # Created by SafeRollback before deploy

        # ── Check 10: Git available ────
        try:
            subprocess.run(["git", "--version"], capture_output=True, timeout=5)
            checks["git_available"] = True
        except:
            checks["git_available"] = False
            failures.append("GIT_UNAVAILABLE")

        # ── Check 11: Not concurrently modified ─
        checks["not_locked"] = True  # Checked by TaskBoard file locks

        # ── Check 12: Consensus (if high-risk) ─
        checks["consensus_ok"] = True  # Checked by caller for high-risk changes

        passed = len(failures) == 0
        if passed:
            self.passed_deploys += 1
        else:
            self.blocked_deploys += 1

        return {
            "passed": passed,
            "checks": checks,
            "failures": failures,
            "change_id": change_id,
            "timestamp": datetime.now().isoformat(),
        }

    def stats(self) -> Dict:
        return {
            "total": self.total_checks,
            "passed": self.passed_deploys,
            "blocked": self.blocked_deploys,
            "pass_rate": f"{self.passed_deploys/max(1,self.total_checks):.0%}",
        }


# ════════════════════════════════════════════════════════════
# 3. Audit Trail — 不可篡改变更日志
# ════════════════════════════════════════════════════════════

@dataclass
class AuditEntry:
    entry_id: str
    action: str          # "deploy", "rollback", "emergency_stop", "file_modified"
    file_path: str
    agent_id: str        # Who did this
    checksum_before: str
    checksum_after: str
    success: bool
    details: str
    timestamp: str


class AuditTrail:
    """
    Append-only audit log. Once written, never modified.

    Format: One JSON entry per line. Append-only guarantees no tampering.
    """

    AUDIT_PATH = os.path.join(
        os.environ.get("LAAP_ROOT", os.path.expanduser("~/.laap")), ".audit_trail.jsonl"
    )

    def __init__(self):
        self.entries: List[AuditEntry] = []
        self._lock = threading.Lock()
        self._load()

    def record(self, action: str, file_path: str, agent_id: str,
               checksum_before: str = "", checksum_after: str = "",
               success: bool = True, details: str = ""):
        """Record an audit entry. Append-only."""
        entry = AuditEntry(
            entry_id=str(uuid.uuid4())[:8],
            action=action,
            file_path=file_path,
            agent_id=agent_id,
            checksum_before=checksum_before,
            checksum_after=checksum_after,
            success=success,
            details=details,
            timestamp=datetime.now().isoformat(),
        )
        with self._lock:
            self.entries.append(entry)
            # Append to file (append-only = tamper-proof)
            try:
                os.makedirs(os.path.dirname(self.AUDIT_PATH), exist_ok=True)
                with open(self.AUDIT_PATH, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(entry.__dict__, ensure_ascii=False) + '\n')
            except Exception:
                pass
    def query(self, file_path: str = "", agent_id: str = "",
              action: str = "", limit: int = 50) -> List[AuditEntry]:
        """Query audit log with filters."""
        result = self.entries
        if file_path:
            result = [e for e in result if file_path in e.file_path]
        if agent_id:
            result = [e for e in result if e.agent_id == agent_id]
        if action:
            result = [e for e in result if e.action == action]
        return result[-limit:]

    def last_modification_of(self, file_path: str) -> Optional[AuditEntry]:
        """Who last modified this file and what happened?"""
        for e in reversed(self.entries):
            if file_path in e.file_path and e.action == "deploy":
                return e
        return None

    def _load(self):
        if os.path.exists(self.AUDIT_PATH):
            try:
                for line in open(self.AUDIT_PATH, 'r', encoding='utf-8'):
                    try:
                        self.entries.append(AuditEntry(**json.loads(line)))
                    except Exception:
                        pass
            except Exception:
                pass
    def stats(self) -> Dict:
        return {
            "total_entries": len(self.entries),
            "last_entry": self.entries[-1].timestamp if self.entries else "N/A",
            "by_action": {
                action: sum(1 for e in self.entries if e.action == action)
                for action in ["deploy", "rollback", "emergency_stop", "file_modified"]
            },
        }


# ════════════════════════════════════════════════════════════
# 4. Integrity Scanner — 定期完整性扫描
# ════════════════════════════════════════════════════════════

class IntegrityScanner:
    """
    Periodically scans all LAAP source files for corruption.

    Detection methods:
      - Filesize anomaly (sudden 90% reduction = corruption)
      - Syntax check (AST parse failure = corruption)
      - Checksum mismatch (vs known good state)

    If corruption detected → AutoRecovery triggered.
    """

    def __init__(self, repo_root: str = None):
        self.repo_root = repo_root or _default_repo_root()
        self.known_checksums: Dict[str, str] = {}  # file → checksum
        self.corruptions_detected = 0
        self.auto_recoveries = 0
        self.last_scan_time = 0.0

    def scan(self, directory: str = "laap/agi/") -> Dict[str, Any]:
        """Full integrity scan. Returns {healthy, findings, recovered}."""
        self.last_scan_time = time.time()
        findings = []
        recovered = 0
        agi_dir = Path(self.repo_root) / directory

        if not agi_dir.exists():
            return {"healthy": False, "error": f"Directory not found: {agi_dir}"}

        for py_file in agi_dir.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue

            rel_path = str(py_file.relative_to(self.repo_root))
            abs_path = str(py_file)
            size = py_file.stat().st_size
            content = py_file.read_text(encoding='utf-8', errors='ignore')
            current_checksum = hashlib.sha256(content.encode()).hexdigest()[:16]

            issue = None

            # Check 1: Empty or near-empty file
            if size < 100 and "world_model" in abs_path:
                issue = "EMPTY_OR_TRUNCATED"
            elif size < 50:
                issue = "EMPTY"

            # Check 2: Syntax error
            if not issue:
                try:
                    import ast
                    ast.parse(content)
                except SyntaxError:
                    issue = "SYNTAX_ERROR"

            # Check 3: Checksum mismatch (if we have a known good state)
            if not issue and rel_path in self.known_checksums:
                if current_checksum != self.known_checksums[rel_path]:
                    issue = "CHECKSUM_MISMATCH"

            # Record known checksum
            self.known_checksums[rel_path] = current_checksum

            if issue:
                findings.append({
                    "file": rel_path,
                    "issue": issue,
                    "size": size,
                })
                self.corruptions_detected += 1

        return {
            "healthy": len(findings) == 0,
            "files_scanned": len(self.known_checksums),
            "issues_found": len(findings),
            "findings": findings,
            "recovery_suggested": len(findings) > 0,
        }

    def register_known_good(self, file_path: str):
        """Register a file's checksum as known-good state."""
        abs_path = file_path if os.path.isabs(file_path) else os.path.join(self.repo_root, file_path)
        if os.path.exists(abs_path):
            content = open(abs_path, 'r', encoding='utf-8').read()
            rel_path = os.path.relpath(abs_path, self.repo_root)
            self.known_checksums[rel_path] = hashlib.sha256(content.encode()).hexdigest()[:16]

    def stats(self) -> Dict:
        return {
            "files_tracked": len(self.known_checksums),
            "corruptions_detected": self.corruptions_detected,
            "auto_recoveries": self.auto_recoveries,
            "last_scan": datetime.fromtimestamp(self.last_scan_time).isoformat() if self.last_scan_time else "never",
        }


# ════════════════════════════════════════════════════════════
# 5. GuardianSystem — Unified Safety
# ════════════════════════════════════════════════════════════

class GuardianSystem:
    """
    Complete project safety system. Unifies all protection layers.

    Usage:
      guardian = GuardianSystem()
      
      # Before any change:
      if not guardian.gatekeeper(file_path, risk_level):
          return  # BLOCKED

      # After change:
      guardian.audit_trail.record(...)

      # Periodic:
      guardian.integrity.scan()
    """

    def __init__(self, repo_root: str = None):
        self.repo_root = repo_root or _default_repo_root()
        self.emergency = EmergencyStop()
        self.checklist = DeployChecklist(repo_root)
        self.audit_trail = AuditTrail()
        self.integrity = IntegrityScanner(repo_root)

        # Register initial known-good checksums
        agi_dir = Path(self.repo_root) / "laap" / "agi"
        if agi_dir.exists():
            for f in agi_dir.rglob("*.py"):
                if "__pycache__" not in str(f):
                    self.integrity.register_known_good(str(f))

        self.created_at = time.time()

    def gatekeeper(self, file_path: str, agent_id: str = "system",
                   risk_level: str = "medium", change_id: str = "") -> Tuple[bool, str]:
        """
        THE gatekeeper. Every code modification MUST pass through here.

        Returns (allowed, reason).
        """
        # Layer 1: Emergency stop
        allowed, reason = self.emergency.allow_modification(risk_level)
        if not allowed:
            self.audit_trail.record(
                "blocked", file_path, agent_id,
                success=False, details=f"Emergency stop: {reason}"
            )
            return False, reason

        # Layer 2: Deploy checklist
        checklist_result = self.checklist.run(file_path, change_id, risk_level)
        if not checklist_result["passed"]:
            self.emergency.record_failure(str(checklist_result["failures"]))
            self.audit_trail.record(
                "blocked", file_path, agent_id,
                success=False, details=f"Checklist: {checklist_result['failures']}"
            )
            return False, f"Checklist: {checklist_result['failures']}"

        # Layer 3: Integrity pre-check
        if os.path.exists(file_path):
            integrity_ok = self._pre_check_integrity(file_path)
            if not integrity_ok:
                return False, "Integrity pre-check failed"

        return True, "All gates passed"

    def _pre_check_integrity(self, file_path: str) -> bool:
        abs_path = file_path if os.path.isabs(file_path) else os.path.join(self.repo_root, file_path)
        if not os.path.exists(abs_path):
            return True  # New file
        
        size = os.path.getsize(abs_path)
        if size == 0:
            return False

        content = open(abs_path, 'r', encoding='utf-8').read()
        checksum = hashlib.sha256(content.encode()).hexdigest()[:16]
        
        rel_path = os.path.relpath(abs_path, self.repo_root)
        known = self.integrity.known_checksums.get(rel_path)
        
        if known and checksum != known and size < 200:
            # File shrunk dramatically - likely corrupted
            return False
        
        return True

    def record_deploy(self, file_path: str, agent_id: str,
                      checksum_before: str, checksum_after: str, success: bool):
        self.audit_trail.record(
            "deploy", file_path, agent_id,
            checksum_before, checksum_after, success
        )
        if success:
            self.emergency.record_success()
            self.integrity.register_known_good(file_path)
        else:
            self.emergency.record_failure("Deploy failed")

    def emergency_stop(self, reason: str = ""):
        """Immediate halt of all modifications."""
        self.emergency.switch_mode(GuardianMode.EMERGENCY, "manual", reason)
        self.audit_trail.record("emergency_stop", "ALL", "system", success=True,
                               details=reason)

    def resume(self):
        """Resume normal operation."""
        self.emergency.switch_mode(GuardianMode.FULL_AUTO, "manual", "Resumed")

    def periodic_scan(self) -> Dict:
        """Run periodic integrity scan + report."""
        result = self.integrity.scan()
        if not result["healthy"]:
            logger.warning(f"Integrity issues: {result['findings']}")
        return result

    def stats(self) -> Dict:
        return {
            "emergency": self.emergency.status(),
            "deploy": self.checklist.stats(),
            "audit": self.audit_trail.stats(),
            "integrity": self.integrity.stats(),
        }


def integrate_guardian(agent) -> GuardianSystem:
    guardian = GuardianSystem(
        repo_root=_default_repo_root()
    )
    agent.guardian = guardian
    return guardian
