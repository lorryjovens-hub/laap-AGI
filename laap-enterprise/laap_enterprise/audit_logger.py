"""企业级审计日志（占位实现）"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AuditLogger:
    """记录关键认知事件与操作，满足企业合规需求。"""

    def __init__(self, log_dir: Path | str | None = None) -> None:
        self.log_dir = Path(log_dir or "logs/audit")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._file = self.log_dir / f"audit_{datetime.now(tz=timezone.utc).strftime('%Y%m%d')}.jsonl"

    def log(self, event_type: str, actor: str, payload: dict[str, Any]) -> None:
        record = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "event_type": event_type,
            "actor": actor,
            "payload": payload,
        }
        with self._file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def query(self, event_type: str | None = None, actor: str | None = None, limit: int = 100) -> list[dict]:
        results: list[dict] = []
        if not self._file.exists():
            return results
        for line in reversed(self._file.read_text(encoding="utf-8").strip().splitlines()):
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event_type and rec.get("event_type") != event_type:
                continue
            if actor and rec.get("actor") != actor:
                continue
            results.append(rec)
            if len(results) >= limit:
                break
        return results
