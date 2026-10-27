"""LAAP Rust 核心桥接 stub。

在 laap-AGI 仓库中，Rust 核心并非必须依赖；本 stub 提供与旧版 LAAP
兼容的 API，使得需要 Rust 加速的模块仍可被导入并在缺少原生扩展时优雅降级。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger("laap.rust_bridge")


class _StubBridge:
    """Rust 桥接的纯 Python fallback，返回空结果以保证导入可用。"""

    def scan_complexity(self, code: str) -> Dict[str, Any]:
        """返回代码复杂度空扫描结果。"""
        return {
            "cyclomatic": 1,
            "cognitive": 1,
            "tokens": len(code.split()),
            "lines": len(code.splitlines()),
        }

    def scan_threats(self, content: str) -> List[Dict[str, Any]]:
        """返回威胁扫描空结果。"""
        return []

    def __bool__(self) -> bool:
        return False


_BRIDGE = None


def get_bridge() -> _StubBridge:
    """返回 Rust 桥接实例；原生扩展不可用时返回 stub 实例。"""
    global _BRIDGE
    if _BRIDGE is None:
        _BRIDGE = _StubBridge()
        logger.debug("Rust bridge not available; using Python stub.")
    return _BRIDGE
