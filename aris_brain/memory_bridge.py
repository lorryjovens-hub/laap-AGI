"""
LAAP Memory Bridge — minimal fallback implementation.

Provides the public interface expected by aris_cognitive_bridge and
laap_integrator when the full memory bridge is not available.
"""
from __future__ import annotations

from typing import List

from aris_brain.memory_store import MemoryFragment, MemoryStore


_store: MemoryStore | None = None


def _get_store() -> MemoryStore:
    global _store
    if _store is None:
        _store = MemoryStore()
    return _store


def get_memory_context(max_core: int = 3, max_recent: int = 3, max_working: int = 2) -> str:
    """Return a short memory context string for prompt injection."""
    store = _get_store()
    parts: List[str] = []

    core = store.query(layer="core", top_k=max_core)
    if core:
        parts.append("[核心记忆] " + "；".join(f.content[:80] for f in core))

    recent = store.query(layer="episodic", top_k=max_recent)
    if recent:
        parts.append("[最近经历] " + "；".join(f.content[:80] for f in recent))

    working = store.query(layer="working", top_k=max_working)
    if working:
        parts.append("[当前工作记忆] " + "；".join(f.content[:60] for f in working))

    return "\n".join(parts)


def recall_related(query: str, top_k: int = 3) -> List[MemoryFragment]:
    """Return memory fragments related to the query."""
    store = _get_store()
    query_words = set(query.lower().split())
    scored = []
    for f in store._fragments:
        frag_words = set(f.content.lower().split())
        score = len(query_words & frag_words)
        if score > 0:
            scored.append((score, f))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [f for _, f in scored[:top_k]]


def store_important(content: str, layer: str = "episodic", importance: float = 0.7, topics: List[str] | None = None) -> None:
    """Store an important memory fragment."""
    store = _get_store()
    fragment = MemoryFragment(
        content=content,
        layer=layer,
        importance=importance,
        topics=topics or [],
    )
    store.store(fragment)
