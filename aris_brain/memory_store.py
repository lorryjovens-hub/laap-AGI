"""
LAAP Memory Store — minimal fallback implementation.

This is a lightweight in-memory + JSON-backed store used when the full
Rust-backed memory engine is not available. It provides the same public
interface so that aris_cognitive_bridge, laap_integrator, and other modules
can import it without modification.

In a full LAAP deployment this module may be replaced by a vector-backed
or Rust-backed implementation.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class MemoryFragment:
    """A single memory fragment."""
    content: str
    layer: str = "episodic"  # core / episodic / working
    importance: float = 0.5
    topics: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    fragment_id: str = field(default_factory=lambda: f"mf_{uuid.uuid4().hex[:8]}")


class MemoryStore:
    """Minimal fallback memory store."""

    def __init__(self, state_dir: Optional[Path] = None):
        self.state_dir = state_dir or Path(__file__).resolve().parent / "state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self.state_dir / "memory_store_fallback.json"

        self._fragments: List[MemoryFragment] = []
        self._load()

    def _load(self) -> None:
        if not self._db_path.exists():
            return
        try:
            data = json.loads(self._db_path.read_text(encoding="utf-8"))
            for item in data:
                self._fragments.append(MemoryFragment(**item))
        except Exception:
            pass

    def _save(self) -> None:
        try:
            records = []
            for f in self._fragments:
                records.append({
                    "content": f.content,
                    "layer": f.layer,
                    "importance": f.importance,
                    "topics": f.topics,
                    "timestamp": f.timestamp,
                    "fragment_id": f.fragment_id,
                })
            self._db_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def store(self, fragment: MemoryFragment) -> None:
        """Store a memory fragment."""
        self._fragments.append(fragment)
        # Keep a bounded number of fragments per layer
        self._prune()
        self._save()

    def _prune(self, max_total: int = 2000) -> None:
        if len(self._fragments) <= max_total:
            return
        # Sort by importance desc, then timestamp desc
        self._fragments.sort(key=lambda f: (f.importance, f.timestamp), reverse=True)
        self._fragments = self._fragments[:max_total]

    def query(self, layer: Optional[str] = None, top_k: int = 5) -> List[MemoryFragment]:
        """Return the most recent fragments, optionally filtered by layer."""
        candidates = self._fragments
        if layer:
            candidates = [f for f in candidates if f.layer == layer]
        candidates = sorted(candidates, key=lambda f: f.timestamp, reverse=True)
        return candidates[:top_k]

    def get_stats(self) -> Dict[str, int]:
        """Return memory statistics."""
        return {
            "total": len(self._fragments),
            "core": len([f for f in self._fragments if f.layer == "core"]),
            "episodic": len([f for f in self._fragments if f.layer == "episodic"]),
            "working": len([f for f in self._fragments if f.layer == "working"]),
        }

    def get_memory_embedding(self, query: str = "", layer: str = "episodic", top_k: int = 3) -> Any:
        """Return a simple pseudo-embedding based on keyword overlap."""
        try:
            import numpy as np
            query_words = set(query.lower().split())
            candidates = [f for f in self._fragments if f.layer == layer]
            scores = []
            for f in candidates:
                frag_words = set(f.content.lower().split())
                score = len(query_words & frag_words) / max(len(query_words), 1)
                scores.append((score, f))
            scores.sort(key=lambda x: x[0], reverse=True)
            selected = [f for _, f in scores[:top_k]]

            emb = np.zeros(384, dtype=np.float32)
            if selected:
                for f in selected:
                    # Simple hash-based projection
                    h = hash(f.content) % 384
                    emb[h] += f.importance
                norm = np.linalg.norm(emb)
                if norm > 0:
                    emb = emb / norm
            return emb
        except Exception:
            return None
