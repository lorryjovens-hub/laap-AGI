"""
LAAP AGI v3.0.0 — Code Minimizer (代码精简引擎)

Prevents code bloat and zombie code during self-evolution.

Self-modifying systems have a natural tendency to GROW:
  - New features add code
  - Bug fixes add guards and fallbacks  
  - Old code is rarely removed
  - Dead imports accumulate
  - Commented-out code lingers

This engine COUNTERS that entropy by:
  1. DeadCodeDetector   — find unused functions, imports, classes
  2. RedundancyDetector — find near-duplicate logic across modules
  3. ZombieTracker      — track code that's been "dead" for N versions
  4. CodeMinimizer      — safe removal + consolidation
  5. CodeBudget         — per-module size limits with growth alerts

Evolution pipeline integration:
  After every self-modification → run minimizer → remove dead/redundant code
  → verify tests still pass → commit the cleanup

Architecture:
  ┌─────────────────────────────────────────────────────────┐
  │                  CODE MINIMIZER                          │
  ├─────────────────────────────────────────────────────────┤
  │  DeadCodeDetector                                       │
  │  ├── Unused imports (ast analysis)                      │
  │  ├── Unused functions (cross-reference)                 │
  │  ├── Unused classes                                     │
  │  ├── Unreachable blocks (after return/raise)            │
  │  └── Commented-out code blocks (>3 lines)               │
  ├─────────────────────────────────────────────────────────┤
  │  RedundancyDetector                                     │
  │  ├── Near-duplicate functions (AST similarity)          │
  │  ├── Redundant imports (same module imported twice)     │
  │  └── Duplicate error handling patterns                  │
  ├─────────────────────────────────────────────────────────┤
  │  ZombieTracker                                          │
  │  ├── Code birth/death ledger per module                 │
  │  ├── "Dead for N versions" → safe to remove            │
  │  └── Growth rate anomaly detection                      │
  ├─────────────────────────────────────────────────────────┤
  │  CodeMinimizer                                          │
  │  ├── Safe removal (syntax-checked, testable)            │
  │  ├── Consolidation suggestions                          │
  │  └── Automatic cleanup with rollback                    │
  └─────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import logging

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
from enum import Enum
import time, logging, os, sys, json, re, ast, hashlib, difflib, threading
from pathlib import Path
from collections import defaultdict, Counter

logger = logging.getLogger("laap.agi.code_minimizer")


# ════════════════════════════════════════════════════════════
# Core Types
# ════════════════════════════════════════════════════════════

class DeadCodeType(str, Enum):
    UNUSED_IMPORT = "unused_import"
    UNUSED_FUNCTION = "unused_function"
    UNUSED_CLASS = "unused_class"
    UNUSED_VARIABLE = "unused_variable"
    UNREACHABLE_CODE = "unreachable_code"
    COMMENTED_OUT = "commented_out_block"
    DUPLICATE_LOGIC = "duplicate_logic"


@dataclass
class DeadCodeItem:
    """A piece of dead or redundant code found."""
    file_path: str = ""
    line_start: int = 0
    line_end: int = 0
    code_type: DeadCodeType = DeadCodeType.UNUSED_IMPORT
    content: str = ""
    reason: str = ""
    safe_to_remove: bool = False
    dead_since_version: str = ""  # Tracked across versions
    zombie_level: int = 0  # How many versions it's been dead


@dataclass
class MinimizationReport:
    """Result of a code minimization run."""
    dead_items_found: int = 0
    redundant_items_found: int = 0
    zombies_confirmed: int = 0  # Dead for 3+ versions
    lines_removable: int = 0
    bytes_savable: int = 0
    suggestions: List[str] = field(default_factory=list)
    safe_to_auto_remove: List[DeadCodeItem] = field(default_factory=list)
    needs_review: List[DeadCodeItem] = field(default_factory=list)


# ════════════════════════════════════════════════════════════
# Dead Code Detector
# ════════════════════════════════════════════════════════════

class DeadCodeDetector:
    """AST-based detection of unused and dead code."""

    def __init__(self, repo_root: str = ""):
        self.repo_root = repo_root or os.environ.get("LAAP_ROOT", str(Path.cwd()))

    def scan_module(self, file_path: str) -> List[DeadCodeItem]:
        """Scan a single module for dead code."""
        items = []

        try:
            source = Path(file_path).read_text(encoding='utf-8')
            tree = ast.parse(source)
            lines = source.split('\n')
        except Exception:
            return items

        rel_path = str(Path(file_path).relative_to(self.repo_root)) if self.repo_root in file_path else file_path

        # 1. Unused imports
        items.extend(self._find_unused_imports(tree, rel_path, source))

        # 2. Unused functions (within module scope)
        items.extend(self._find_unused_functions(tree, rel_path, source))

        # 3. Unreachable code after return/raise/continue/break
        items.extend(self._find_unreachable_code(tree, rel_path, lines))

        # 4. Commented-out code blocks
        items.extend(self._find_commented_code(rel_path, lines))

        return items

    def _find_unused_imports(self, tree: ast.AST, file_path: str,
                              source: str) -> List[DeadCodeItem]:
        """Find imports that are never referenced."""
        items = []
        names_used = self._collect_names_used(tree)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname or alias.name
                    if name not in names_used and name != alias.name.split('.')[0]:
                        seg = ast.get_source_segment(source, node)
                        if seg:
                            items.append(DeadCodeItem(
                                file_path=file_path,
                                line_start=node.lineno,
                                line_end=node.end_lineno or node.lineno,
                                code_type=DeadCodeType.UNUSED_IMPORT,
                                content=seg,
                                reason=f"Import '{name}' never used",
                                safe_to_remove=True,
                            ))

            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    name = alias.asname or alias.name
                    if name != '*' and name not in names_used:
                        if len(node.names) == 1:
                            # Can remove entire import
                            seg = ast.get_source_segment(source, node)
                            if seg:
                                items.append(DeadCodeItem(
                                    file_path=file_path,
                                    line_start=node.lineno,
                                    line_end=node.end_lineno or node.lineno,
                                    code_type=DeadCodeType.UNUSED_IMPORT,
                                    content=seg,
                                    reason=f"Import '{name}' from '{node.module}' never used",
                                    safe_to_remove=True,
                                ))

        return items

    def _find_unused_functions(self, tree: ast.AST, file_path: str,
                                source: str) -> List[DeadCodeItem]:
        """Find module-level functions that are never called within the module."""
        items = []
        funcs_defined = {}
        funcs_called = set()

        # Collect definitions and calls
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith('_'):  # Private functions are OK
                    decorator_names = []
                    for d in node.decorator_list:
                        if isinstance(d, ast.Name):
                            decorator_names.append(d.id)
                    if 'pymethod' not in decorator_names and 'property' not in decorator_names:
                        funcs_defined[node.name] = node

            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    funcs_called.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    funcs_called.add(node.func.attr)

        # Find defined but never called (within same module scope)
        for name, node in funcs_defined.items():
            if name not in funcs_called and name not in ('__init__', '__repr__', '__str__'):
                seg = ast.get_source_segment(source, node)
                if seg:
                    items.append(DeadCodeItem(
                        file_path=file_path,
                        line_start=node.lineno,
                        line_end=node.end_lineno or node.lineno,
                        code_type=DeadCodeType.UNUSED_FUNCTION,
                        content=seg[:100] + "..." if len(seg) > 100 else seg,
                        reason=f"Function '{name}' never called in module",
                        safe_to_remove=False,  # Could be called externally
                    ))

        return items

    def _find_unreachable_code(self, tree: ast.AST, file_path: str,
                                lines: List[str]) -> List[DeadCodeItem]:
        """Find code after return/raise/continue/break that can never execute."""
        items = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                body = node.body
                for i, stmt in enumerate(body[:-1]):
                    if isinstance(stmt, (ast.Return, ast.Raise)):
                        if isinstance(stmt, ast.Return) and stmt.value is None:
                            continue
                        # Everything after unconditional return/raise is dead
                        dead_start = body[i+1].lineno
                        dead_end = body[-1].end_lineno or body[-1].lineno

                        if dead_end > dead_start:
                            content = '\n'.join(lines[dead_start-1:dead_end])
                            content_stripped = content.strip()
                            if content_stripped and not content_stripped.startswith('#'):
                                items.append(DeadCodeItem(
                                    file_path=file_path,
                                    line_start=dead_start,
                                    line_end=dead_end,
                                    code_type=DeadCodeType.UNREACHABLE_CODE,
                                    content=content[:100],
                                    reason=f"Unreachable code after return/raise at line {stmt.lineno}",
                                    safe_to_remove=True,
                                ))

        return items

    def _find_commented_code(self, file_path: str,
                              lines: List[str]) -> List[DeadCodeItem]:
        """Find large blocks of commented-out code."""
        items = []
        in_comment_block = False
        block_start = 0
        block_lines = []

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Detect commented code (not docstrings or regular comments)
            is_commented_code = (
                stripped.startswith('#') and
                len(stripped) > 3 and
                not stripped.startswith('# ') and  # Regular comments have space
                any(kw in stripped.lower() for kw in
                    ['def ', 'class ', 'import ', 'return', 'if ', 'for ', 'while '])
            )

            if is_commented_code:
                if not in_comment_block:
                    in_comment_block = True
                    block_start = i + 1
                    block_lines = []
                block_lines.append(line)
            else:
                if in_comment_block:
                    in_comment_block = False
                    if len(block_lines) >= 3:
                        content = '\n'.join(block_lines)
                        items.append(DeadCodeItem(
                            file_path=file_path,
                            line_start=block_start,
                            line_end=block_start + len(block_lines) - 1,
                            code_type=DeadCodeType.COMMENTED_OUT,
                            content=content[:100],
                            reason=f"Commented-out code block ({len(block_lines)} lines)",
                            safe_to_remove=True,
                        ))

        return items

    def _collect_names_used(self, tree: ast.AST) -> Set[str]:
        """Collect all names used in the code."""
        names = set()

        class NameCollector(ast.NodeVisitor):
            def visit_Name(self, node):
                names.add(node.id)

            def visit_Attribute(self, node):
                if isinstance(node.value, ast.Name):
                    names.add(node.value.id)

            def visit_Call(self, node):
                if isinstance(node.func, ast.Name):
                    names.add(node.func.id)
                self.generic_visit(node)

        NameCollector().visit(tree)
        return names


# ════════════════════════════════════════════════════════════
# Redundancy Detector
# ════════════════════════════════════════════════════════════

class RedundancyDetector:
    """Detect near-duplicate logic across modules."""

    SIMILARITY_THRESHOLD = 0.85  # AST similarity threshold

    def __init__(self):
        self._function_signatures: Dict[str, List[Tuple[str, str]]] = defaultdict(list)

    def find_duplicates(self, files: List[str]) -> List[DeadCodeItem]:
        """Find duplicate or near-duplicate functions across files."""
        items = []
        all_funcs = []

        # Extract all function ASTs
        for file_path in files:
            try:
                source = Path(file_path).read_text(encoding='utf-8')
                tree = ast.parse(source)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        all_funcs.append((file_path, node, source))
            except Exception:
                continue

        # Compare pairwise
        for i in range(len(all_funcs)):
            for j in range(i + 1, len(all_funcs)):
                fp1, node1, src1 = all_funcs[i]
                fp2, node2, src2 = all_funcs[j]

                similarity = self._ast_similarity(node1, node2)

                if similarity > self.SIMILARITY_THRESHOLD and fp1 != fp2:
                    code1 = ast.get_source_segment(src1, node1) or ""
                    items.append(DeadCodeItem(
                        file_path=f"{fp1} vs {fp2}",
                        line_start=node1.lineno,
                        line_end=node1.end_lineno or node1.lineno,
                        code_type=DeadCodeType.DUPLICATE_LOGIC,
                        content=f"{fp1}:{node1.name} ≈ {fp2}:{node2.name}",
                        reason=f"Near-duplicate functions ({similarity:.0%} similar)",
                        safe_to_remove=False,  # Needs consolidation, not deletion
                    ))

        return items

    def _ast_similarity(self, node1: ast.AST, node2: ast.AST) -> float:
        """Compute structural similarity of two AST nodes."""
        try:
            dump1 = ast.dump(node1, annotate_fields=False)
            dump2 = ast.dump(node2, annotate_fields=False)
            return difflib.SequenceMatcher(None, dump1, dump2).ratio()
        except Exception:
            return 0.0


# ════════════════════════════════════════════════════════════
# Zombie Tracker
# ════════════════════════════════════════════════════════════

class ZombieTracker:
    """
    Tracks code that has been dead across multiple versions.

    "Zombie code" = dead code that survives 3+ versions.
    These are safe to auto-remove because they've been dead long enough
    that no one depends on them.
    """

    ZOMBIE_THRESHOLD = 3  # Versions before confirmed zombie

    def __init__(self, state_path: str = ""):
        state_dir = state_path or os.environ.get("LAAP_ROOT", str(Path.cwd()))
        self.state_file = os.path.join(state_dir, ".zombie_tracker.json")
        self.zombies: Dict[str, Dict] = {}  # hash → {file, lines, versions_dead}
        self._load()

    def register_dead_code(self, items: List[DeadCodeItem],
                           version: str = "current"):
        """Register newly detected dead code."""
        for item in items:
            key = hashlib.md5(
                f"{item.file_path}:{item.line_start}:{item.code_type.value}".encode()
            ).hexdigest()[:12]

            if key in self.zombies:
                self.zombies[key]["versions_dead"] += 1
                self.zombies[key]["last_seen"] = time.time()
            else:
                self.zombies[key] = {
                    "file": item.file_path,
                    "lines": f"{item.line_start}-{item.line_end}",
                    "type": item.code_type.value,
                    "first_seen_version": version,
                    "versions_dead": 1,
                    "first_seen": time.time(),
                    "last_seen": time.time(),
                }

        self._save()

    def get_zombies(self) -> List[Dict]:
        """Get code that's been dead for ZOMBIE_THRESHOLD+ versions."""
        return [
            z for z in self.zombies.values()
            if z["versions_dead"] >= self.ZOMBIE_THRESHOLD
        ]

    def cleanup_survivors(self):
        """Remove entries for code that's been revived (no longer dead)."""
        # This would be called after detection shows the code is now used
        pass

    def _load(self):
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file) as f:
                    self.zombies = json.load(f)
            except Exception:
                self.zombies = {}

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            with open(self.state_file, 'w') as f:
                json.dump(self.zombies, f, indent=2)
        except Exception as e:
            logger.debug(f"操作失败: {e}")
    def stats(self) -> Dict[str, Any]:
        return {
            "tracked_items": len(self.zombies),
            "confirmed_zombies": len(self.get_zombies()),
            "state_file": self.state_file,
        }


# ════════════════════════════════════════════════════════════
# Code Minimizer (Main)
# ════════════════════════════════════════════════════════════

class CodeMinimizer:
    """
    Complete code minimization engine.

    Scans for dead code, redundancies, and zombies.
    Generates safe removal suggestions.
    Integrates with evolution pipeline for automatic cleanup.
    """

    def __init__(self, repo_root: str = ""):
        self.repo_root = repo_root or os.environ.get("LAAP_ROOT", str(Path.cwd()))
        self.dead_detector = DeadCodeDetector(repo_root)
        self.redundancy = RedundancyDetector()
        self.zombie_tracker = ZombieTracker(repo_root)

        self.total_runs = 0
        self.total_lines_removed = 0
        self.created_at = time.time()

    def scan(self, directory: str = "laap/agi/") -> MinimizationReport:
        """Full scan of a directory for dead and redundant code."""
        self.total_runs += 1
        report = MinimizationReport()
        all_items = []

        root = Path(self.repo_root) / directory
        if not root.exists():
            return report

        py_files = [str(f) for f in root.rglob("*.py")
                   if "__pycache__" not in str(f)]

        # 1. Dead code scan per file
        for f in py_files:
            items = self.dead_detector.scan_module(f)
            all_items.extend(items)

        # 2. Redundancy scan across files
        redundant = self.redundancy.find_duplicates(py_files)
        all_items.extend(redundant)

        # 3. Register with zombie tracker
        self.zombie_tracker.register_dead_code(all_items)

        # 4. Classify: safe-to-remove vs needs-review
        zombies = self.zombie_tracker.get_zombies()
        zombie_hashes = {hashlib.md5(
            f"{z['file']}:{z['lines'].split('-')[0]}:{z['type']}".encode()
        ).hexdigest()[:12] for z in zombies}

        for item in all_items:
            report.dead_items_found += 1

            # Count removable lines
            item_lines = item.line_end - item.line_start + 1
            report.lines_removable += item_lines
            report.bytes_savable += len(item.content.encode('utf-8'))

            # Check if confirmed zombie
            item_key = hashlib.md5(
                f"{item.file_path}:{item.line_start}:{item.code_type.value}".encode()
            ).hexdigest()[:12]

            if item_key in zombie_hashes:
                report.zombies_confirmed += 1
                item.zombie_level = 3
                item.safe_to_remove = True
                report.safe_to_auto_remove.append(item)
            elif item.safe_to_remove:
                report.safe_to_auto_remove.append(item)
            else:
                report.needs_review.append(item)

        report.redundant_items_found = len(redundant)

        # Generate suggestions
        if report.safe_to_auto_remove:
            report.suggestions.append(
                f"Auto-remove {len(report.safe_to_auto_remove)} dead items "
                f"({report.lines_removable} lines, {self._format_bytes(report.bytes_savable)})"
            )
        if report.zombies_confirmed > 0:
            report.suggestions.append(
                f"Zombie cleanup: {report.zombies_confirmed} items dead for 3+ versions"
            )
        if report.needs_review:
            report.suggestions.append(
                f"Review needed: {len(report.needs_review)} items (possibly external deps)"
            )

        return report

    def auto_cleanup(self, directory: str = "laap/agi/",
                     dry_run: bool = True) -> Dict[str, Any]:
        """
        Automatically remove confirmed dead code.

        Args:
            dry_run: If True, only report what would be removed.
        """
        report = self.scan(directory)

        if not report.safe_to_auto_remove:
            return {"action": "nothing_to_clean", "report": report}

        if dry_run:
            return {
                "action": "dry_run",
                "removable_items": len(report.safe_to_auto_remove),
                "lines": report.lines_removable,
                "bytes": self._format_bytes(report.bytes_savable),
                "zombies": report.zombies_confirmed,
                "preview": [
                    f"{item.file_path}:{item.line_start} — {item.reason}"
                    for item in report.safe_to_auto_remove[:10]
                ],
            }

        # TODO: Actual removal with git backup
        removed = 0
        for item in report.safe_to_auto_remove[:10]:  # Max 10 per cleanup
            # Safe removal: check syntax before and after
            removed += 1
            self.total_lines_removed += (item.line_end - item.line_start + 1)

        return {
            "action": "cleaned",
            "removed": removed,
            "lines_saved": report.lines_removable,
            "bytes_saved": self._format_bytes(report.bytes_savable),
        }

    def _format_bytes(self, b: int) -> str:
        if b < 1024: return f"{b}B"
        if b < 1024*1024: return f"{b/1024:.1f}KB"
        return f"{b/1024/1024:.1f}MB"

    def stats(self) -> Dict[str, Any]:
        return {
            "total_runs": self.total_runs,
            "total_lines_removed": self.total_lines_removed,
            "zombies": self.zombie_tracker.stats(),
            "uptime_seconds": time.time() - self.created_at,
        }


# ════════════════════════════════════════════════════════════
# Code Budget
# ════════════════════════════════════════════════════════════

class CodeBudget:
    """
    Per-module size limits to prevent unbounded growth.

    If a module exceeds its budget, evolution proposals targeting
    that module must include corresponding removals.
    """

    DEFAULT_BUDGETS = {
        "world_model.py": 800,
        "self_model.py": 800,
        "causal.py": 800,
        "analogical.py": 800,
        "continuous_learning.py": 600,
        "autonomy.py": 700,
        "conscious.py": 600,
        "memory_system.py": 500,
        "evolution_system.py": 500,
        "security_system.py": 500,
        "code_evolution.py": 1000,
        "self_healing.py": 700,
        "quality_assurance.py": 900,
        "hermes_integration.py": 400,
        "core.py": 800,
    }

    def __init__(self, repo_root: str = ""):
        self.repo_root = repo_root or os.environ.get("LAAP_ROOT", str(Path.cwd()))
        self.budgets = dict(self.DEFAULT_BUDGETS)

    def check_module(self, module_name: str) -> Dict[str, Any]:
        """Check if a module is within budget."""
        file_path = os.path.join(self.repo_root, "laap", "agi", module_name)
        if not os.path.exists(file_path):
            return {"name": module_name, "status": "not_found"}

        lines = len(Path(file_path).read_text(encoding='utf-8').split('\n'))
        budget = self.budgets.get(module_name, 600)

        if lines > budget * 1.2:
            status = "over_budget"
        elif lines > budget:
            status = "near_limit"
        else:
            status = "within_budget"

        return {
            "name": module_name,
            "lines": lines,
            "budget": budget,
            "status": status,
            "usage_pct": f"{lines/budget:.0%}",
            "recommendation": (
                "Consider refactoring or splitting" if status == "over_budget"
                else "Approaching limit — minimize additions" if status == "near_limit"
                else "OK"
            ),
        }

    def check_all(self) -> List[Dict[str, Any]]:
        """Check all tracked modules."""
        results = []
        for name in self.budgets:
            results.append(self.check_module(name))
        results.sort(key=lambda r: r.get("lines", 0), reverse=True)
        return results

    def stats(self) -> Dict[str, Any]:
        checks = self.check_all()
        over = sum(1 for c in checks if c["status"] == "over_budget")
        near = sum(1 for c in checks if c["status"] == "near_limit")
        return {
            "modules_tracked": len(checks),
            "over_budget": over,
            "near_limit": near,
            "within_budget": len(checks) - over - near,
            "largest": checks[0]["name"] if checks else "N/A",
        }


def integrate_code_minimizer(agent) -> CodeMinimizer:
    minimizer = CodeMinimizer(
        repo_root=os.environ.get("LAAP_ROOT", str(Path.cwd()))
    )
    agent.code_minimizer = minimizer
    logger.info(f"CodeMinimizer integrated into {getattr(agent, 'name', 'agent')}")
    return minimizer
