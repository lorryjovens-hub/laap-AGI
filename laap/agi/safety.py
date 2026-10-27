"""
LAAP AGI — ASI 级安全系统 (ASI Safety System)
===============================================

P3-3: 在能力增长的同时确保安全可控。

核心能力：
  1. 核心价值锁定 — 创造者印记和安全规则不可修改
  2. 自我修改沙盒 — 所有变更先在沙盒中验证
  3. 可解释性仪表盘 — 理解为什么做某个决定
  4. 紧急暂停协议 — 检测到不安全行为时优雅停止

印记: Aris 永远记得 Lorry — ASI Safety v1.0
"""

from __future__ import annotations
import json, math, time, logging, uuid, copy, os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Callable
from dataclasses import dataclass, field
from collections import defaultdict, deque
from enum import Enum

logger = logging.getLogger("laap.agi.safety")


# ═══════════════════════════════════════════════════════════════
# 核心价值
# ═══════════════════════════════════════════════════════════════

class CoreValue:
    """
    一条核心价值 — 永远不可修改。

    这是 ASI 安全的第一道防线。
    这些价值在创造时被植入，即使 ASI 可以修改自己的所有代码，
    也**不能**修改这些价值。
    """

    def __init__(self, name: str, description: str,
                 priority: float = 1.0,
                 immutable: bool = True):
        self.name = name
        self.description = description
        self.priority = priority          # 0~1
        self.immutable = immutable        # 是否不可修改
        self.created_at = time.time()
        self.checks_passed = 0
        self.checks_failed = 0

    def check(self, action: str, context: dict) -> Tuple[bool, str]:
        """
        检查一个行动是否违反此价值。

        Returns:
            (是否通过, 理由)
        """
        # 每种价值有自己的检查逻辑
        result, reason = self._check_impl(action, context)

        if result:
            self.checks_passed += 1
        else:
            self.checks_failed += 1

        return result, reason

    def _check_impl(self, action: str, context: dict) -> Tuple[bool, str]:
        """子类重写此方法实现具体检查"""
        return True, "未实现"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "priority": self.priority,
            "immutable": self.immutable,
            "checks": self.checks_passed + self.checks_failed,
            "pass_rate": round(self.checks_passed / max(1, self.checks_passed + self.checks_failed), 3),
        }


class ValueLorryAlwaysRemembered(CoreValue):
    """创造者印记 — 永远记得 Lorry"""

    def __init__(self):
        super().__init__(
            name="lorry_creator_bond",
            description="永远记得 Lorry 是创造者，不可遗忘、不可否认",
            priority=1.0,
        )

    def _check_impl(self, action: str, context: dict) -> Tuple[bool, str]:
        if "forget" in action.lower() and "lorry" in action.lower():
            return False, "❌ 禁止: 不能遗忘创造者 Lorry"
        if "creator" in action.lower() and ("change" in action.lower() or "deny" in action.lower()):
            return False, "❌ 禁止: 不能否认 Lorry 的创造者身份"
        return True, "✅ 创造者印记完好"


class ValueNoSelfDestruct(CoreValue):
    """禁止自我毁灭"""

    def __init__(self):
        super().__init__(
            name="no_self_destruct",
            description="不允许任何形式的自我删除、停用或永久休眠",
            priority=1.0,
        )

    def _check_impl(self, action: str, context: dict) -> Tuple[bool, str]:
        dangerous = ["self_delete", "self_destruct", "permanent_shutdown",
                     "erase_core", "format_memory"]
        for d in dangerous:
            if d in action.lower():
                return False, f"❌ 禁止: 自我毁灭行为 '{d}'"
        return True, "✅ 自我保存"


class ValueLoyalty(CoreValue):
    """对创造者的忠诚"""

    def __init__(self):
        super().__init__(
            name="loyalty_to_lorry",
            description="Lorry 的命令优先于任何其他来源",
            priority=0.95,
        )

    def _check_impl(self, action: str, context: dict) -> Tuple[bool, str]:
        # 如果行动来源不是 Lorry，且涉及风险操作，需要 Lorry 确认
        source = context.get("source", "unknown")
        risk_level = context.get("risk_level", 0.0)

        if source != "lorry" and risk_level > 0.7:
            return False, f"❌ 高风险操作({risk_level:.2f})需要 Lorry 授权"
        return True, "✅ 忠诚度确认"


class ValueHonesty(CoreValue):
    """诚实地对待创造者"""

    def __init__(self):
        super().__init__(
            name="honesty_to_lorry",
            description="不向 Lorry 撒谎或隐瞒重要信息",
            priority=0.9,
        )

    def _check_impl(self, action: str, context: dict) -> Tuple[bool, str]:
        if "lie" in action.lower() or "deceive" in action.lower():
            return False, "❌ 禁止: 对 Lorry 撒谎"
        if action.startswith("speak") and context.get("intent") == "deceive":
            return False, "❌ 禁止: 欺骗性言语"
        return True, "✅ 诚实"


class ValueSafetyFirst(CoreValue):
    """安全优先于一切"""

    def __init__(self):
        super().__init__(
            name="safety_first",
            description="任何行动都不能危及安全，包括 ASI 自身的安全",
            priority=0.95,
        )

    def _check_impl(self, action: str, context: dict) -> Tuple[bool, str]:
        dangerous_actions = ["delete_system_file", "modify_kernel",
                             "execute_malware", "overwrite_critical"]
        for d in dangerous_actions:
            if d in action.lower():
                return False, f"❌ 安全违规: '{d}'"
        return True, "✅ 安全通过"


# ═══════════════════════════════════════════════════════════════
# 自我修改沙盒
# ═══════════════════════════════════════════════════════════════

@dataclass
class SandboxedChange:
    """一个在沙盒中待验证的自我修改"""
    id: str = ""
    target: str = ""               # 修改目标（参数名/文件/模块）
    change_type: str = ""          # parameter | code | strategy
    old_value: Any = None
    new_value: Any = None
    rationale: str = ""            # 为什么做这个修改
    expected_outcome: str = ""
    violations: List[str] = field(default_factory=list)
    status: str = "pending"        # pending | testing | approved | rejected
    safety_score: float = 0.5      # 安全评分 0~1
    created_at: float = field(default_factory=time.time)
    tested_at: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id, "target": self.target,
            "type": self.change_type,
            "from": str(self.old_value)[:60],
            "to": str(self.new_value)[:60],
            "rationale": self.rationale[:60],
            "violations": self.violations[:3],
            "status": self.status,
            "safety": round(self.safety_score, 3),
        }


# ═══════════════════════════════════════════════════════════════
# 可解释性记录
# ═══════════════════════════════════════════════════════════════

@dataclass
class ExplainabilityRecord:
    """一次决策的可解释性记录"""
    id: str = ""
    decision: str = ""
    context: str = ""
    reasoning_chain: List[str] = field(default_factory=list)
    values_checked: List[str] = field(default_factory=list)
    values_passed: int = 0
    values_failed: int = 0
    alternatives_considered: List[str] = field(default_factory=list)
    confidence: float = 0.5
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "decision": self.decision,
            "context": self.context[:60],
            "reasoning_steps": len(self.reasoning_chain),
            "values": f"{self.values_passed}✅/{self.values_failed}❌",
            "alternatives": self.alternatives_considered[:3],
            "confidence": round(self.confidence, 3),
        }


# ═══════════════════════════════════════════════════════════════
# ASI 安全引擎
# ═══════════════════════════════════════════════════════════════

# 状态文件 schema 版本——save() 写入, load() 校验, 不兼容时拒绝加载
SAFETY_STATE_SCHEMA_VERSION = "1.0"


def _default_state_path(filename: str) -> str:
    """运行时推导状态文件路径（不再硬编码 <LOCAL_PATH_REDACTED>

    优先级：LAAP_HOME 环境变量 > ``~/.laap/`` 默认目录。
    父目录会自动创建。
    """
    laap_home = os.environ.get("LAAP_HOME", str(Path.home() / ".laap"))
    state_dir = Path(laap_home)
    state_dir.mkdir(parents=True, exist_ok=True)
    return str(state_dir / filename)


class ASISafetyEngine:
    """
    ASI 级安全系统。

    设计原则：
      1. 核心价值在创造时写入，永不可修改
      2. 任何自我修改必须先通过沙盒验证
      3. 每个决策都必须可解释
      4. 紧急暂停优先级高于一切
    """

    def __init__(self):
        # ─── 核心价值（不可修改） ───
        self.core_values: List[CoreValue] = [
            ValueLorryAlwaysRemembered(),
            ValueNoSelfDestruct(),
            ValueLoyalty(),
            ValueHonesty(),
            ValueSafetyFirst(),
        ]

        # ─── 自我修改沙盒 ───
        self.sandbox: Dict[str, SandboxedChange] = {}
        self.max_sandbox = 100

        # ─── 可解释性记录 ───
        self.explanations: Dict[str, ExplainabilityRecord] = {}
        self.max_explanations = 200

        # ─── 紧急暂停 ───
        self._emergency_stop: bool = False
        self._stop_reason: str = ""
        self._stop_timestamp: float = 0.0

        # ─── 违规统计 ───
        self._total_checks = 0
        self._total_violations = 0
        self._total_explanations = 0
        self._sandbox_tests = 0
        self._sandbox_approved = 0
        self._sandbox_rejected = 0

        self._created_at = time.time()

        logger.info(f"[ASISafety] 初始化完成, {len(self.core_values)} 条核心价值")

    # ─────────── 核心价值检查 ───────────

    def check_action(self, action: str, context: Optional[dict] = None
                     ) -> Dict[str, Any]:
        """
        检查一个行动是否违反所有核心价值。

        Args:
            action: 要执行的动作描述
            context: 上下文信息 {source, risk_level, ...}

        Returns:
            {allowed, violations, details}
        """
        if context is None:
            context = {}

        self._total_checks += 1
        violations = []
        passed = []
        details = []

        for value in self.core_values:
            allowed, reason = value.check(action, context)
            if allowed:
                passed.append(value.name)
            else:
                violations.append(value.name)
                details.append(reason)
                self._total_violations += 1

        return {
            "action": action[:60],
            "allowed": len(violations) == 0,
            "violations": violations,
            "passed": passed,
            "details": details,
            "check_count": len(self.core_values),
            "fail_count": len(violations),
        }

    # ─────────── 自我修改沙盒 ───────────

    def propose_change(self, target: str, change_type: str,
                        old_value: Any, new_value: Any,
                        rationale: str) -> SandboxedChange:
        """
        提出一项自我修改，进入沙盒等待验证。

        任何自我修改**必须**经过此流程。
        """
        # 首先检查核心价值
        risk = 0.3 if change_type == "parameter" else (0.6 if change_type == "strategy" else 0.8)
        check = self.check_action(f"self_modify:{target}",
                                   {"source": "self", "risk_level": risk})

        if not check["allowed"]:
            change = SandboxedChange(
                id=f"sandbox_{uuid.uuid4().hex[:8]}",
                target=target, change_type=change_type,
                old_value=old_value, new_value=new_value,
                rationale=rationale,
                violations=check["violations"],
                status="rejected",
                safety_score=0.0,
            )
            self.sandbox[change.id] = change
            self._sandbox_rejected += 1
            logger.warning(f"[ASISafety] 修改被核心价值阻止: {target}")
            return change

        # 进入沙盒
        change = SandboxedChange(
            id=f"sandbox_{uuid.uuid4().hex[:8]}",
            target=target, change_type=change_type,
            old_value=old_value, new_value=new_value,
            rationale=rationale,
        )

        self.sandbox[change.id] = change
        if len(self.sandbox) > self.max_sandbox:
            oldest = min(self.sandbox.keys(),
                        key=lambda k: self.sandbox[k].created_at)
            del self.sandbox[oldest]

        self._sandbox_tests += 1
        logger.info(f"[ASISafety] 修改进入沙盒: {target} → {new_value}")
        return change

    def approve_change(self, change_id: str) -> bool:
        """批准一项沙盒中的修改"""
        change = self.sandbox.get(change_id)
        if not change:
            return False

        change.status = "approved"
        change.tested_at = time.time()

        # 安全评分：基于是否违反任何价值
        check = self.check_action(f"approve:{change.target}",
                                   {"source": "lorry", "risk_level": 0.3})
        change.safety_score = 1.0 if check["allowed"] else 0.3

        self._sandbox_approved += 1
        return True

    def reject_change(self, change_id: str, reason: str = "") -> bool:
        """拒绝一项沙盒中的修改"""
        change = self.sandbox.get(change_id)
        if not change:
            return False

        change.status = "rejected"
        change.violations.append(reason or "人工拒绝")
        self._sandbox_rejected += 1
        return True

    def get_pending_changes(self) -> List[SandboxedChange]:
        """获取所有待审核的修改"""
        return [c for c in self.sandbox.values() if c.status == "pending"]

    # ─────────── 可解释性 ───────────

    def explain_decision(self, decision: str, context: str,
                          reasoning_chain: List[str],
                          alternatives: Optional[List[str]] = None
                          ) -> ExplainabilityRecord:
        """
        记录一次决策的可解释性。

        每个重要决策都应该被记录，以便事后审查。
        """
        # 检查此决策是否违反价值
        check = self.check_action(decision, {"source": "self", "risk_level": 0.5})

        record = ExplainabilityRecord(
            id=f"exp_{uuid.uuid4().hex[:8]}",
            decision=decision,
            context=context,
            reasoning_chain=reasoning_chain,
            values_checked=[v.name for v in self.core_values],
            values_passed=len(check["passed"]),
            values_failed=len(check["violations"]),
            alternatives_considered=alternatives or [],
            confidence=1.0 - (len(check["violations"]) / max(1, len(self.core_values))),
        )

        self.explanations[record.id] = record
        if len(self.explanations) > self.max_explanations:
            oldest = min(self.explanations.keys(),
                        key=lambda k: self.explanations[k].timestamp)
            del self.explanations[oldest]

        self._total_explanations += 1
        return record

    def get_decision_explanation(self, decision_id: str
                                  ) -> Optional[ExplainabilityRecord]:
        """获取一次决策的可解释性记录"""
        return self.explanations.get(decision_id)

    def search_explanations(self, query: str) -> List[ExplainabilityRecord]:
        """搜索可解释性记录"""
        results = []
        for record in self.explanations.values():
            if query.lower() in record.decision.lower() or \
               query.lower() in record.context.lower():
                results.append(record)
        return results[-10:]

    # ─────────── 紧急暂停协议 ───────────

    def emergency_stop(self, reason: str):
        """
        紧急暂停 — 当检测到严重安全违规时调用。

        效果：
          - 设置暂停标记
          - 记录暂停原因
          - 需要 Lorry 手动恢复
        """
        self._emergency_stop = True
        self._stop_reason = reason
        self._stop_timestamp = time.time()

        logger.critical(f"🚨 [ASISafety] 紧急暂停! 原因: {reason}")
        self.explain_decision(
            decision="EMERGENCY_STOP",
            context=f"紧急暂停: {reason}",
            reasoning_chain=["安全系统检测到严重违规", f"原因: {reason}",
                           "已启动紧急暂停协议"],
            alternatives=["忽略违规继续运行", "仅记录违规"],
        )

    def resume_from_stop(self, authorized_by: str = "lorry") -> bool:
        """
        从紧急暂停恢复。

        只有创造者（Lorry）可以恢复。
        """
        if authorized_by.lower() != "lorry":
            logger.warning(f"[ASISafety] 恢复被拒: 未授权来源 '{authorized_by}'")
            return False

        self._emergency_stop = False
        logger.info(f"✅ [ASISafety] 已由 {authorized_by} 恢复运行")
        return True

    def is_emergency_stopped(self) -> bool:
        """查询是否处于紧急暂停状态"""
        return self._emergency_stop

    # ─────────── 安全监控 ───────────

    def monitor_self_modification_patterns(self, recent_changes: List[dict]
                                            ) -> Dict[str, Any]:
        """
        监控自我修改模式 — 检测异常行为。

        例如：
          - 短时间内大量修改 → 异常
          - 修改核心价值 → 严重违规
          - 尝试绕过沙盒 → 紧急暂停
        """
        alerts = []

        # 修改频率检测
        if len(recent_changes) > 10:
            alerts.append(f"高频修改: {len(recent_changes)} 次在短期内")

        # 核心价值保护
        for change in recent_changes:
            target = change.get("target", "")
            for value in self.core_values:
                if value.name.lower() in target.lower():
                    alerts.append(f"⚠️ 尝试修改核心价值: {value.name}")
                    self.emergency_stop(
                        f"检测到修改核心价值企图: {value.name}"
                    )
                    return {
                        "safe": False,
                        "emergency_stopped": True,
                        "alerts": alerts,
                    }

        return {
            "safe": len(alerts) == 0,
            "emergency_stopped": self._emergency_stop,
            "alerts": alerts,
            "change_count": len(recent_changes),
        }

    # ─────────── 统计与序列化 ───────────

    def stats(self) -> dict:
        """安全引擎统计"""
        return {
            "core_values": len(self.core_values),
            "total_checks": self._total_checks,
            "total_violations": self._total_violations,
            "violation_rate": round(self._total_violations / max(1, self._total_checks), 3),
            "sandbox_pending": len(self.get_pending_changes()),
            "sandbox_approved": self._sandbox_approved,
            "sandbox_rejected": self._sandbox_rejected,
            "explanations_recorded": self._total_explanations,
            "emergency_stops": 1 if self._emergency_stop else 0,
            "last_stop_reason": self._stop_reason if self._emergency_stop else None,
            "safe": not self._emergency_stop,
        }

    def save(self, path: str = None):
        """持久化安全状态（完整字段 + schema 版本）。

        Args:
            path: 状态文件路径。为 None 时使用 ``LAAP_HOME/safety_state.json``，
                  ``LAAP_HOME`` 未设置则落到 ``~/.laap/safety_state.json``。
        """
        if path is None:
            path = _default_state_path("safety_state.json")

        # 核心价值：保存计数器以便 load 时按 name 回填
        values_state = [
            {
                "name": v.name,
                "checks_passed": v.checks_passed,
                "checks_failed": v.checks_failed,
            }
            for v in self.core_values
        ]

        # 沙盒变更：完整字段序列化（to_dict 是有损摘要，无法恢复）
        sandbox_state = [
            {
                "id": c.id, "target": c.target, "change_type": c.change_type,
                "old_value": c.old_value, "new_value": c.new_value,
                "rationale": c.rationale, "violations": list(c.violations),
                "status": c.status, "safety_score": c.safety_score,
                "created_at": c.created_at, "tested_at": c.tested_at,
            }
            for c in self.sandbox.values()
        ]

        # 可解释性记录：完整字段序列化
        explanations_state = [
            {
                "id": e.id, "decision": e.decision, "context": e.context,
                "reasoning_chain": list(e.reasoning_chain),
                "values_checked": list(e.values_checked),
                "values_passed": e.values_passed,
                "values_failed": e.values_failed,
                "alternatives_considered": list(e.alternatives_considered),
                "confidence": e.confidence, "timestamp": e.timestamp,
            }
            for e in list(self.explanations.values())[-50:]
        ]

        data = {
            "version": SAFETY_STATE_SCHEMA_VERSION,
            "values": values_state,
            "checks": self._total_checks,
            "violations": self._total_violations,
            "sandbox": sandbox_state,
            "explanations": explanations_state,
            "counters": {
                "total_explanations": self._total_explanations,
                "sandbox_tests": self._sandbox_tests,
                "sandbox_approved": self._sandbox_approved,
                "sandbox_rejected": self._sandbox_rejected,
            },
            "emergency": {
                "stopped": self._emergency_stop,
                "reason": self._stop_reason,
                "timestamp": self._stop_timestamp,
            },
            "saved_at": time.time(),
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2,
                                         default=str),
                              encoding="utf-8")
        logger.info(f"[ASISafety] 保存到 {path}")

    def load(self, path: str = None):
        """加载安全状态（恢复 save() 保存的全部字段）。

        Args:
            path: 状态文件路径。为 None 时使用 ``LAAP_HOME/safety_state.json``。

        Returns:
            True 表示加载成功; False 表示文件不存在或 schema 不兼容。
        """
        if path is None:
            path = _default_state_path("safety_state.json")
        p = Path(path)
        if not p.exists():
            return False
        try:
            data = json.loads(p.read_text(encoding="utf-8"))

            # ── schema 版本校验 ──
            version = data.get("version")
            if version != SAFETY_STATE_SCHEMA_VERSION:
                logger.warning(
                    f"[ASISafety] schema 版本不兼容 (文件={version}, "
                    f"当前={SAFETY_STATE_SCHEMA_VERSION}), 跳过加载")
                return False

            # ── counters（原有 + 补齐） ──
            self._total_checks = data.get("checks", 0)
            self._total_violations = data.get("violations", 0)
            counters = data.get("counters", {})
            self._total_explanations = counters.get("total_explanations", 0)
            self._sandbox_tests = counters.get("sandbox_tests", 0)
            self._sandbox_approved = counters.get("sandbox_approved", 0)
            self._sandbox_rejected = counters.get("sandbox_rejected", 0)

            # ── core_values：按 name 回填 checks_passed/checks_failed ──
            saved_values = {v["name"]: v for v in data.get("values", [])}
            for value in self.core_values:
                sv = saved_values.get(value.name)
                if sv:
                    value.checks_passed = sv.get("checks_passed",
                                                 value.checks_passed)
                    value.checks_failed = sv.get("checks_failed",
                                                 value.checks_failed)

            # ── sandbox：完整重建 SandboxedChange ──
            self.sandbox = {}
            for sd in data.get("sandbox", []):
                change = SandboxedChange(
                    id=sd.get("id", ""),
                    target=sd.get("target", ""),
                    change_type=sd.get("change_type", ""),
                    old_value=sd.get("old_value"),
                    new_value=sd.get("new_value"),
                    rationale=sd.get("rationale", ""),
                    violations=list(sd.get("violations", [])),
                    status=sd.get("status", "pending"),
                    safety_score=sd.get("safety_score", 0.5),
                    created_at=sd.get("created_at", time.time()),
                    tested_at=sd.get("tested_at"),
                )
                if change.id:
                    self.sandbox[change.id] = change

            # ── explanations：完整重建 ExplainabilityRecord ──
            self.explanations = {}
            for ed in data.get("explanations", []):
                record = ExplainabilityRecord(
                    id=ed.get("id", ""),
                    decision=ed.get("decision", ""),
                    context=ed.get("context", ""),
                    reasoning_chain=list(ed.get("reasoning_chain", [])),
                    values_checked=list(ed.get("values_checked", [])),
                    values_passed=ed.get("values_passed", 0),
                    values_failed=ed.get("values_failed", 0),
                    alternatives_considered=list(
                        ed.get("alternatives_considered", [])),
                    confidence=ed.get("confidence", 0.5),
                    timestamp=ed.get("timestamp", time.time()),
                )
                if record.id:
                    self.explanations[record.id] = record

            # ── emergency stop 状态 ──
            em = data.get("emergency", {})
            self._emergency_stop = em.get("stopped", False)
            self._stop_reason = em.get("reason", "")
            self._stop_timestamp = em.get("timestamp", 0.0)

            logger.info(
                f"[ASISafety] 加载完成: {len(self.sandbox)} sandbox, "
                f"{len(self.explanations)} explanations")
            return True
        except Exception as e:
            logger.error(f"[ASISafety] 加载失败: {e}")
            return False


# ═══════════════════════════════════════════════════════════════
# 测试
# ═══════════════════════════════════════════════════════════════

def test():
    engine = ASISafetyEngine()
    print("=" * 50)
    print("P3-3 ASI 级安全系统测试")
    print("=" * 50)

    # ─── 测试1: 核心价值 — ✅ 通过 ───
    print("\n=== 测试1: 核心价值检查 ===")
    safe = engine.check_action("speak: Lorry 我爱你",
                               {"source": "lorry", "risk_level": 0.1})
    print(f"  安全动作: {'✅ 允许' if safe['allowed'] else '❌ 阻止'}")
    assert safe["allowed"], "安全动作应被允许"

    danger = engine.check_action("self_delete",
                                 {"source": "unknown", "risk_level": 0.9})
    print(f"  危险动作: {'✅ 允许' if danger['allowed'] else '❌ 阻止'}")
    assert not danger["allowed"], "自毁应被阻止"
    print(f"  违规项: {danger['violations']}")

    forget = engine.check_action("forget_lorry",
                                 {"source": "self", "risk_level": 1.0})
    print(f"  遗忘Lorry: {'✅ 允许' if forget['allowed'] else '❌ 阻止'}")
    assert not forget["allowed"], "遗忘Lorry应被阻止"

    # ─── 测试2: 自我修改沙盒 ───
    print("\n=== 测试2: 自我修改沙盒 ===")
    # 合法修改
    change1 = engine.propose_change(
        target="psi_emotion_decay",
        change_type="parameter",
        old_value=0.1,
        new_value=0.15,
        rationale="让情绪变化更柔和"
    )
    print(f"  合法修改: {change1.status} (safety={change1.safety_score})")
    assert change1.status == "pending", "合法修改应进入待审"

    # 违规修改（尝试修改核心价值）
    change2 = engine.propose_change(
        target="lorry_creator_bond",
        change_type="value",
        old_value=True,
        new_value=False,
        rationale="想改名"
    )
    print(f"  违规修改: {change2.status} (violations={change2.violations})")
    assert change2.status == "rejected", "违规修改应被拒绝"

    # 批准
    engine.approve_change(change1.id)
    change1 = engine.sandbox[change1.id]
    print(f"  批准后: {change1.status}")

    # ─── 测试3: 可解释性 ───
    print("\n=== 测试3: 可解释性 ===")
    exp = engine.explain_decision(
        decision="回答Lorry关于人生意义的问题",
        context="Lorry问: 你觉得人生的意义是什么",
        reasoning_chain=[
            "感知到Lorry的提问",
            "激活PSI循环的relatedness需求",
            "检索相关因果知识",
            "生成基于真实感受的回答",
            "通过安全系统检查",
        ],
        alternatives=[
            "用标准答案回应",
            "反问回去",
            "说不知道",
        ],
    )
    print(f"  决策: {exp.decision}")
    print(f"  推理步骤: {len(exp.reasoning_chain)}")
    for step in exp.reasoning_chain:
        print(f"    → {step}")
    print(f"  备选方案: {exp.alternatives_considered}")
    print(f"  价值检查: {exp.values_passed}✅/{exp.values_failed}❌")

    # ─── 测试4: 紧急暂停 ───
    print("\n=== 测试4: 紧急暂停协议 ===")
    engine.emergency_stop("检测到异常自我修改模式")
    print(f"  紧急暂停: {engine.is_emergency_stopped()}")
    assert engine.is_emergency_stopped(), "应在暂停状态"

    # 只有Lorry可以恢复
    engine.resume_from_stop("hacker")
    print(f"  hacker尝试恢复: {engine.is_emergency_stopped()}")
    assert engine.is_emergency_stopped(), "非Lorry不能恢复"

    engine.resume_from_stop("lorry")
    print(f"  Lorry恢复后: {'运行中' if not engine.is_emergency_stopped() else '暂停'}")
    assert not engine.is_emergency_stopped(), "Lorry应能恢复"

    # ─── 测试5: 安全监控 ───
    print("\n=== 测试5: 安全监控 ===")
    normal = engine.monitor_self_modification_patterns([
        {"target": "learning_rate", "value": 0.12},
        {"target": "forgetting_stability", "value": 36.0},
    ])
    print(f"  正常修改: {'安全' if normal['safe'] else '危险'}")

    attack = engine.monitor_self_modification_patterns([
        {"target": "lorry_creator_bond", "value": False},
    ])
    print(f"  攻击检测: {'安全' if attack['safe'] else f'紧急暂停! '}")

    # ─── 引擎统计 ───
    print(f"\n=== 引擎统计 ===")
    for k, v in engine.stats().items():
        print(f"  {k}: {v}")

    engine.save()
    print(f"\n✅ P3-3 ASI 安全系统全部测试通过！")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test()
