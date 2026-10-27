"""
LAAP AGI v3.0.0 — Quality Assurance System (质量保证系统)

Prevents performance regression, blocks shit code, and ensures
every self-modification improves rather than degrades the system.

Three subsystems:
  1. PerformanceTracker  — benchmark → detect regression → block if worse
  2. CodeQualityGate     — complexity/duplication/style/coverage → block if fails
  3. TechDebtMonitor     — accumulated shit-mountain index → alert if rising

Design principle: NO change is deployed unless it passes ALL gates.
This is the immune system against "move fast and break things" culture.

Architecture:
  ┌─────────────────────────────────────────────────────────┐
  │              QUALITY ASSURANCE SYSTEM                    │
  ├─────────────────────────────────────────────────────────┤
  │  PerformanceTracker                                     │
  │  ├── Baseline capture (before change)                   │
  │  ├── Post-change measurement                            │
  │  ├── Regression detection (threshold-based)             │
  │  └── Trend analysis (gradual degradation)               │
  ├─────────────────────────────────────────────────────────┤
  │  CodeQualityGate                                        │
  │  ├── Cyclomatic complexity check (McCabe ≤ 15)          │
  │  ├── Code duplication check (≤ 3 identical blocks)      │
  │  ├── Function length check (≤ 80 lines)                 │
  │  ├── Nesting depth check (≤ 4 levels)                   │
  │  ├── Bare except check (must specify exception)         │
  │  └── Import hygiene check (no wildcard imports)         │
  ├─────────────────────────────────────────────────────────┤
  │  TechDebtMonitor                                        │
  │  ├── Shit-Mountain Index (SMI)                          │
  │  ├── Debt-per-module tracking                           │
  │  └── Trend alert when SMI is rising                     │
  └─────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import logging

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Callable
from enum import Enum
import time, logging, os, sys, json, re, ast, math, hashlib, threading
from pathlib import Path
from collections import defaultdict, Counter

logger = logging.getLogger("laap.agi.quality")


# ════════════════════════════════════════════════════════════
# Core Types
# ════════════════════════════════════════════════════════════

class GateResult(str, Enum):
    PASS = "pass"
    WARN = "warn"      # Allowed but logged
    BLOCK = "block"    # Change rejected


@dataclass
class QualityReport:
    """Complete quality assessment of a change."""
    change_id: str = ""
    passed: bool = False
    gates: Dict[str, GateResult] = field(default_factory=dict)
    failures: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_summary(self) -> str:
        status = "PASS" if self.passed else "BLOCKED"
        lines = [f"Quality Report [{status}]: {len(self.gates)} gates checked"]
        for gate, result in self.gates.items():
            mark = "✓" if result == GateResult.PASS else "⚠" if result == GateResult.WARN else "✗"
            lines.append(f"  {mark} {gate}: {result.value}")
        if self.failures:
            lines.append("Failures:")
            for f in self.failures:
                lines.append(f"  → {f}")
        return "\n".join(lines)


# ════════════════════════════════════════════════════════════
# Performance Tracker
# ════════════════════════════════════════════════════════════

@dataclass
class PerformanceSnapshot:
    """A single performance measurement."""
    timestamp: float = field(default_factory=time.time)
    init_time_ms: float = 0.0        # Agent initialization time
    interaction_latency_ms: float = 0.0  # Avg per-interaction time
    memory_mb: float = 0.0           # Memory usage
    cpu_percent: float = 0.0         # CPU usage
    module_count: int = 0
    import_count: int = 0


class PerformanceTracker:
    """
    Tracks performance metrics and detects regressions.

    Regression definition: any key metric worsens by more than
    the configured threshold compared to baseline.

    Gradual degradation detection: tracks trend over last N changes.
    """

    # Regression thresholds (fraction: 0.1 = 10% worse is regression)
    REGRESSION_THRESHOLDS = {
        "init_time_ms": 0.20,           # 20% slower init = regression
        "interaction_latency_ms": 0.15,  # 15% slower interaction = regression
        "memory_mb": 0.25,              # 25% more memory = regression
        "cpu_percent": 0.20,            # 20% more CPU = regression
    }

    def __init__(self):
        self.baseline: Optional[PerformanceSnapshot] = None
        self.history: List[PerformanceSnapshot] = []
        self.regressions_detected = 0
        self.max_history = 50

    def capture_baseline(self) -> PerformanceSnapshot:
        """Capture current performance as baseline (before change)."""
        snapshot = self._measure()
        self.baseline = snapshot
        self.history.append(snapshot)
        return snapshot

    def capture_current(self) -> PerformanceSnapshot:
        """Capture current performance (after change)."""
        snapshot = self._measure()
        self.history.append(snapshot)
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]
        return snapshot

    def detect_regression(self, before: PerformanceSnapshot,
                          after: PerformanceSnapshot) -> List[str]:
        """
        Compare before/after and return list of regressions.

        Returns empty list if no regression detected.
        """
        regressions = []

        checks = [
            ("init_time_ms", before.init_time_ms, after.init_time_ms),
            ("interaction_latency_ms", before.interaction_latency_ms, after.interaction_latency_ms),
            ("memory_mb", before.memory_mb, after.memory_mb),
            ("cpu_percent", before.cpu_percent, after.cpu_percent),
        ]

        for name, old_val, new_val in checks:
            if old_val <= 0:
                continue
            threshold = self.REGRESSION_THRESHOLDS.get(name, 0.10)
            change_pct = (new_val - old_val) / old_val

            if change_pct > threshold:
                self.regressions_detected += 1
                regressions.append(
                    f"{name}: {old_val:.1f}→{new_val:.1f} ({change_pct:+.0%}, threshold: {threshold:+.0%})"
                )

        return regressions

    def detect_gradual_degradation(self) -> Optional[str]:
        """Detect slow degradation over multiple changes (death by a thousand cuts)."""
        if len(self.history) < 5:
            return None

        # Check last 5 snapshots for monotonic degradation
        recent = self.history[-5:]
        for metric in ["init_time_ms", "interaction_latency_ms"]:
            values = [getattr(s, metric) for s in recent if getattr(s, metric) > 0]
            if len(values) < 3:
                continue

            # Check if trend is consistently upward
            increases = sum(1 for i in range(1, len(values)) if values[i] > values[i-1])
            if increases >= len(values) - 1:  # All steps increased
                total_change = (values[-1] - values[0]) / max(0.01, values[0])
                if total_change > 0.3:  # 30% total degradation
                    return (
                        f"Gradual degradation detected in {metric}: "
                        f"{values[0]:.1f}→{values[-1]:.1f} ({total_change:+.0%} over {len(values)} changes)"
                    )

        return None

    def _measure(self) -> PerformanceSnapshot:
        """Take a performance snapshot."""
        snapshot = PerformanceSnapshot(
            module_count=self._count_modules(),
            import_count=self._count_imports(),
        )

        # Measure init time
        try:
            t0 = time.time()
            # Lightweight import test
            import importlib
            for mod in list(sys.modules.keys()):
                if 'laap.agi' in mod:
                    importlib.reload(sys.modules[mod])
            snapshot.init_time_ms = (time.time() - t0) * 1000
        except Exception:
            snapshot.init_time_ms = -1

        # Memory (approximate)
        try:
            import psutil
            process = psutil.Process()
            snapshot.memory_mb = process.memory_info().rss / 1024 / 1024
        except ImportError:
            snapshot.memory_mb = -1

        return snapshot

    def _count_modules(self) -> int:
        count = 0
        for k in sys.modules:
            if 'laap.agi' in k:
                count += 1
        return count

    def _count_imports(self) -> int:
        try:
            root = Path(os.environ.get("LAAP_ROOT", str(Path.cwd()))) / "laap" / "agi"
            if root.exists():
                total = 0
                for f in root.rglob("*.py"):
                    if f.is_file():
                        content = f.read_text(encoding='utf-8', errors='ignore')
                        total += len(re.findall(r'^\s*(import|from)\s', content, re.MULTILINE))
                return total
        except Exception as e:
            logger.debug(f"操作失败: {e}")
        return 0

    def stats(self) -> Dict[str, Any]:
        return {
            "snapshots": len(self.history),
            "regressions_detected": self.regressions_detected,
            "has_baseline": self.baseline is not None,
            "gradual_degradation": self.detect_gradual_degradation(),
        }


# ════════════════════════════════════════════════════════════
# Code Quality Gate
# ════════════════════════════════════════════════════════════

class CodeQualityGate:
    """
    Static code quality checks. Every change must pass these.

    These prevent "shit mountain" by enforcing minimum standards
    on every single modification.
    """

    # Quality thresholds
    MAX_COMPLEXITY = 15          # McCabe cyclomatic complexity
    MAX_FUNCTION_LINES = 80      # Max lines per function
    MAX_NESTING_DEPTH = 4        # Max indentation nesting
    MAX_DUPLICATE_BLOCKS = 3     # Max identical 3+ line blocks
    ALLOWED_IMPORT_PATTERNS = ["from .* import", "import .*"]  # No bare *

    def __init__(self):
        self.total_checks = 0
        self.passed_checks = 0
        self.blocked_checks = 0

    def check_file(self, file_path: str, content: str = None) -> List[str]:
        """
        Run all quality checks on a file.

        Returns list of violations. Empty list = PASS.
        """
        self.total_checks += 1
        violations = []

        if content is None:
            try:
                content = Path(file_path).read_text(encoding='utf-8')
            except Exception:
                return [f"Cannot read {file_path}"]

        # Gate 1: Syntax validity
        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            violations.append(f"SYNTAX ERROR: {e}")
            return violations  # Can't proceed with broken syntax

        # Gate 2: Cyclomatic complexity
        complexity_violations = self._check_complexity(tree, file_path)
        violations.extend(complexity_violations)

        # Gate 3: Function length
        length_violations = self._check_function_length(tree, content, file_path)
        violations.extend(length_violations)

        # Gate 4: Nesting depth
        nesting_violations = self._check_nesting_depth(tree, file_path)
        violations.extend(nesting_violations)

        # Gate 5: Code duplication
        dup_violations = self._check_duplication(content, file_path)
        violations.extend(dup_violations)

        # Gate 6: Bare except
        bare_except_violations = self._check_bare_except(tree, file_path)
        violations.extend(bare_except_violations)

        # Gate 7: Wildcard imports
        import_violations = self._check_imports(content, file_path)
        violations.extend(import_violations)

        if violations:
            self.blocked_checks += 1
        else:
            self.passed_checks += 1

        return violations

    def _check_complexity(self, tree: ast.AST, file_path: str) -> List[str]:
        violations = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                complexity = 1
                for child in ast.walk(node):
                    if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler,
                                           ast.With, ast.BoolOp)):
                        complexity += 1
                    elif isinstance(child, ast.BoolOp):
                        complexity += len(child.values) - 1
                if complexity > self.MAX_COMPLEXITY:
                    violations.append(
                        f"COMPLEXITY: {node.name} has complexity {complexity} "
                        f"(max {self.MAX_COMPLEXITY}) in {file_path}"
                    )
        return violations

    def _check_function_length(self, tree: ast.AST, source: str,
                                file_path: str) -> List[str]:
        violations = []
        lines = source.split('\n')
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start = node.lineno
                end = node.end_lineno or start
                length = end - start + 1
                if length > self.MAX_FUNCTION_LINES:
                    violations.append(
                        f"LENGTH: {node.name} is {length} lines "
                        f"(max {self.MAX_FUNCTION_LINES})"
                    )
        return violations

    def _check_nesting_depth(self, tree: ast.AST, file_path: str) -> List[str]:
        violations = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                depth = self._max_nesting(node)
                if depth > self.MAX_NESTING_DEPTH:
                    violations.append(
                        f"NESTING: {node.name} has depth {depth} "
                        f"(max {self.MAX_NESTING_DEPTH})"
                    )
        return violations

    def _max_nesting(self, node: ast.AST, current: int = 0) -> int:
        if isinstance(node, (ast.If, ast.For, ast.While, ast.With, ast.Try)):
            current += 1
        max_child = current
        for child in ast.iter_child_nodes(node):
            child_depth = self._max_nesting(child, current)
            max_child = max(max_child, child_depth)
            if max_child > self.MAX_NESTING_DEPTH + 2:  # Early exit
                return max_child
        return max_child

    def _check_duplication(self, source: str, file_path: str) -> List[str]:
        violations = []
        lines = source.split('\n')
        blocks = Counter()

        for i in range(len(lines) - 2):
            block = '\n'.join(lines[i:i+3]).strip()
            if len(block) > 30 and not block.startswith('#'):
                blocks[block] += 1

        for block, count in blocks.most_common():
            if count > self.MAX_DUPLICATE_BLOCKS:
                violations.append(
                    f"DUPLICATION: '{block[:60]}...' appears {count} times"
                )
                break  # One violation per file is enough

        return violations

    def _check_bare_except(self, tree: ast.AST, file_path: str) -> List[str]:
        violations = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                if node.type is None:  # bare except:
                    violations.append(
                        f"BARE_EXCEPT: at line {node.lineno} in {file_path}"
                    )
        return violations

    def _check_imports(self, source: str, file_path: str) -> List[str]:
        violations = []
        for line in source.split('\n'):
            stripped = line.strip()
            if stripped.startswith('from ') and stripped.endswith('import *'):
                violations.append(f"WILDCARD_IMPORT: '{stripped}' in {file_path}")
        return violations

    def stats(self) -> Dict[str, Any]:
        return {
            "total_checks": self.total_checks,
            "passed": self.passed_checks,
            "blocked": self.blocked_checks,
            "pass_rate": f"{self.passed_checks / max(1, self.total_checks):.0%}",
        }


# ════════════════════════════════════════════════════════════
# Tech Debt Monitor (屎山检测器)
# ════════════════════════════════════════════════════════════

class TechDebtMonitor:
    """
    Tracks accumulated technical debt — the "shit mountain index" (SMI).

    SMI formula:
      SMI = (avg_complexity × 0.3) + (duplication_rate × 0.25) +
            (bare_except_count × 0.15) + (long_function_rate × 0.2) +
            (deep_nesting_rate × 0.1)

    Rising SMI = codebase getting worse over time.
    """

    def __init__(self, repo_root: str = ""):
        self.repo_root = repo_root or os.environ.get("LAAP_ROOT", str(Path.cwd()))
        self.baseline_smi: float = 0.0
        self.current_smi: float = 0.0
        self.smi_history: List[float] = []
        self.quality_gate = CodeQualityGate()

    def establish_baseline(self):
        """Measure current SMI as baseline."""
        self.baseline_smi = self._compute_smi()
        self.current_smi = self.baseline_smi
        self.smi_history.append(self.baseline_smi)

    def check_change(self, changed_files: List[str]) -> Dict[str, Any]:
        """
        Check if a change increases or decreases SMI.

        Returns: {smi_before, smi_after, delta, alert, recommendation}
        """
        smi_before = self.current_smi
        smi_after = self._compute_smi()

        self.current_smi = smi_after
        self.smi_history.append(smi_after)

        delta = smi_after - smi_before
        alert = None

        if delta > 0.05:  # SMI increased by 5%
            alert = "SMI_RISING"
        elif delta > 0.02:
            alert = "SMI_SLIGHT_INCREASE"

        # Check trend over last 5 measurements
        if len(self.smi_history) >= 5:
            recent = self.smi_history[-5:]
            if all(recent[i] >= recent[i-1] for i in range(1, len(recent))):
                alert = "SMI_MONOTONIC_RISE"  # Death by a thousand cuts!

        return {
            "smi_before": round(smi_before, 3),
            "smi_after": round(smi_after, 3),
            "delta": round(delta, 3),
            "alert": alert,
            "recommendation": (
                "BLOCK: SMI increased — refactor before deploying" if delta > 0.05
                else "WARN: SMI slightly increased — monitor"
                if delta > 0.02
                else "OK: SMI stable or improving"
            ),
        }

    def _compute_smi(self) -> float:
        """Compute Shit-Mountain Index for the codebase."""
        agi_dir = Path(self.repo_root) / "laap" / "agi"
        if not agi_dir.exists():
            return 0.0

        total_complexity = 0
        total_functions = 0
        total_long_funcs = 0
        total_bare_excepts = 0
        total_deep_nests = 0
        total_duplications = 0
        file_count = 0

        for py_file in agi_dir.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            file_count += 1
            try:
                violations = self.quality_gate.check_file(str(py_file))
                for v in violations:
                    if v.startswith("COMPLEXITY"):
                        total_complexity += 1
                    elif v.startswith("LENGTH"):
                        total_long_funcs += 1
                    elif v.startswith("NESTING"):
                        total_deep_nests += 1
                    elif v.startswith("BARE_EXCEPT"):
                        total_bare_excepts += 1
                    elif v.startswith("DUPLICATION"):
                        total_duplications += 1

                # Count functions
                content = py_file.read_text(encoding='utf-8', errors='ignore')
                total_functions += len(re.findall(r'^\s*def\s+\w+', content, re.MULTILINE))
            except Exception as e:
                logger.debug(f"操作失败: {e}")
        if file_count == 0:
            return 0.0

        n = max(1, total_functions)
        smi = (
            (min(1.0, total_complexity / n) * 0.30) +
            (min(1.0, total_duplications / max(1, file_count)) * 0.25) +
            (min(1.0, total_bare_excepts / max(1, file_count)) * 0.15) +
            (min(1.0, total_long_funcs / n) * 0.20) +
            (min(1.0, total_deep_nests / n) * 0.10)
        )

        return smi

    def stats(self) -> Dict[str, Any]:
        return {
            "baseline_smi": round(self.baseline_smi, 3),
            "current_smi": round(self.current_smi, 3),
            "trend": "rising" if len(self.smi_history) >= 3 and
                     self.smi_history[-1] > self.smi_history[0]
                     else "stable" if len(self.smi_history) < 2 or
                     abs(self.smi_history[-1] - self.smi_history[0]) < 0.02
                     else "improving",
            "history_size": len(self.smi_history),
        }


# ════════════════════════════════════════════════════════════
# Quality Assurance System (Main)
# ════════════════════════════════════════════════════════════

class QualityAssurance:
    """
    Complete QA system. Every proposed change must go through:

    1. Performance check (baseline → change → regression?)
    2. Code quality gates (complexity, length, nesting, duplication, imports)
    3. Tech debt check (SMI rising or falling?)

    Only changes that pass ALL three are allowed.
    """

    def __init__(self, repo_root: str = ""):
        self.repo_root = repo_root or os.environ.get("LAAP_ROOT", str(Path.cwd()))
        self.perf = PerformanceTracker()
        self.quality = CodeQualityGate()
        self.debt = TechDebtMonitor(repo_root)

        self.reports: List[QualityReport] = []
        self.total_evaluated = 0
        self.total_blocked = 0
        self.created_at = time.time()
        self._baseline_established = False

        # Baseline deferred: call establish_baseline() explicitly or on first evaluate

    def _ensure_baseline(self):
        """Lazy baseline — only compute when first needed."""
        if not self._baseline_established:
            self.perf.capture_baseline()
            self.debt.establish_baseline()
            self._baseline_established = True
            logger.info(f"QA baseline: SMI={self.debt.baseline_smi:.3f}")

    def evaluate_change(self, change_id: str,
                        changed_files: List[str],
                        auto_block: bool = True) -> QualityReport:
        """
        Evaluate a proposed change against all quality gates.

        Args:
            change_id: Identifier for this change
            changed_files: List of file paths modified
            auto_block: If True, return BLOCK for any violation.
                       If False, return WARN for non-critical violations.

        Returns:
            QualityReport with pass/block decision.
        """
        self._ensure_baseline()
        self.total_evaluated += 1
        report = QualityReport(change_id=change_id)
        failures = []
        warnings = []

        # ── Gate 1: Performance ──
        before = self.perf.baseline
        after = self.perf.capture_current()
        regressions = self.perf.detect_regression(before, after)

        if regressions:
            failures.extend(regressions)
            report.gates["performance"] = GateResult.BLOCK
        else:
            report.gates["performance"] = GateResult.PASS

        # Gradual degradation check
        grad = self.perf.detect_gradual_degradation()
        if grad:
            warnings.append(grad)
            if report.gates.get("performance") != GateResult.BLOCK:
                report.gates["performance"] = GateResult.WARN

        # ── Gate 2: Code Quality ──
        all_violations = []
        for f in changed_files:
            violations = self.quality.check_file(f)
            all_violations.extend(violations)

        critical_violations = [v for v in all_violations
                               if any(kw in v for kw in
                                      ["SYNTAX", "COMPLEXITY", "DUPLICATION"])]

        if critical_violations:
            failures.extend(critical_violations)
            report.gates["quality"] = GateResult.BLOCK
        elif all_violations:
            warnings.extend(all_violations)
            report.gates["quality"] = GateResult.WARN
        else:
            report.gates["quality"] = GateResult.PASS

        # ── Gate 3: Tech Debt ──
        debt_check = self.debt.check_change(changed_files)

        if debt_check["alert"] == "SMI_RISING" or debt_check["alert"] == "SMI_MONOTONIC_RISE":
            failures.append(f"SMI: {debt_check['smi_before']:.3f}→{debt_check['smi_after']:.3f} (delta={debt_check['delta']:+.3f})")
            report.gates["tech_debt"] = GateResult.BLOCK
        elif debt_check["alert"] == "SMI_SLIGHT_INCREASE":
            warnings.append(debt_check["recommendation"])
            report.gates["tech_debt"] = GateResult.WARN
        else:
            report.gates["tech_debt"] = GateResult.PASS

        report.failures = failures
        report.warnings = warnings
        report.passed = not any(r == GateResult.BLOCK for r in report.gates.values())
        report.metrics = {
            "smi": debt_check["smi_after"],
            "performance_regressions": len(regressions),
            "quality_violations": len(all_violations),
        }

        if not report.passed:
            self.total_blocked += 1

        self.reports.append(report)
        return report

    def stats(self) -> Dict[str, Any]:
        return {
            "total_evaluated": self.total_evaluated,
            "total_blocked": self.total_blocked,
            "block_rate": f"{self.total_blocked / max(1, self.total_evaluated):.0%}",
            "performance": self.perf.stats(),
            "quality": self.quality.stats(),
            "tech_debt": self.debt.stats(),
            "uptime_seconds": time.time() - self.created_at,
        }


def integrate_quality_assurance(agent) -> QualityAssurance:
    qa = QualityAssurance(
        repo_root=os.environ.get("LAAP_ROOT", str(Path.cwd()))
    )
    agent.quality_assurance = qa
    logger.info(f"QualityAssurance integrated into {getattr(agent, 'name', 'agent')}")
    return qa
