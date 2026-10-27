"""脱敏遥测（占位实现）"""

from __future__ import annotations

import hashlib
from typing import Any


class TelemetryClient:
    """收集脱敏后的运行指标，用于企业级健康监控。"""

    def __init__(self, endpoint: str | None = None) -> None:
        self.endpoint = endpoint
        self._buffer: list[dict[str, Any]] = []

    def record(self, metric: str, value: float, labels: dict[str, str] | None = None) -> None:
        self._buffer.append({
            "metric": metric,
            "value": value,
            "labels": labels or {},
        })

    def flush(self) -> list[dict[str, Any]]:
        snapshot = self._buffer[:]
        self._buffer.clear()
        return snapshot

    @staticmethod
    def anonymize(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()[:16]
