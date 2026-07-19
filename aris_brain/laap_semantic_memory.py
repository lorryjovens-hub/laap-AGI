"""
LAAP Semantic Memory — vector-based episodic memory retrieval.

Design:
  - Store memories as {id, text, timestamp, embedding, meta}
  - Pluggable embedding provider (API or local model)
  - In-memory index + JSON persistence
  - Cosine-similarity top-k retrieval

Default provider priority:
  1. OPENAI_API_KEY / DEEPSEEK_API_KEY -> OpenAI-compatible embedding API
  2. sentence-transformers local model (if installed)
  3. Keyword fallback
"""

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

BRAIN_DIR = Path(__file__).resolve().parent
MEMORY_PATH = BRAIN_DIR / "laap_semantic_memory.json"

DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_EMBEDDING_DIM = 1536


class EmbeddingProvider:
    """Base class for embedding providers."""

    def embed(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """Use OpenAI-compatible API for embeddings."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = DEFAULT_EMBEDDING_MODEL,
    ):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
        self.base_url = base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.model = model

    def embed(self, texts: List[str]) -> List[List[float]]:
        import requests

        if not self.api_key:
            raise RuntimeError("No API key for embedding provider")

        resp = requests.post(
            f"{self.base_url}/embeddings",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={"input": texts, "model": self.model},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        return [item["embedding"] for item in data["data"]]


class SentenceTransformersProvider(EmbeddingProvider):
    """Local sentence-transformers model."""

    def __init__(self, model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name)

    def embed(self, texts: List[str]) -> List[List[float]]:
        return self.model.encode(texts, convert_to_numpy=True).tolist()


class TfidfEmbeddingProvider(EmbeddingProvider):
    """Pure-numpy TF-IDF embeddings. Works without torch/sklearn."""

    # Common Chinese stop characters/words to de-emphasize
    STOP_CHARS = set("的是了我你他在有和就这那吗呢吧啊哦嗯个为之上中与及以可到也去也又非常的会要着过来看起来觉得感觉想")

    def __init__(self, dim: int = 4096):
        self.dim = dim
        self.df: Dict[str, int] = {}
        self.n_docs = 0

    def _tokenize(self, text: str) -> List[str]:
        text = text.lower()
        chars = re.findall(r"[\u4e00-\u9fff]", text)
        # Add Chinese bigrams for phrase awareness
        bigrams = [chars[i] + chars[i + 1] for i in range(len(chars) - 1)]
        # ASCII words/numbers
        words = re.findall(r"[a-z0-9]+", text)
        tokens = [t for t in chars + bigrams + words if t not in self.STOP_CHARS]
        return tokens

    def _hash(self, tok: str) -> int:
        return int(hashlib.md5(tok.encode()).hexdigest(), 16) % self.dim

    def _fit(self, texts: List[str]):
        self.n_docs += len(texts)
        for text in texts:
            seen = set(self._tokenize(text))
            for tok in seen:
                self.df[tok] = self.df.get(tok, 0) + 1

    def embed(self, texts: List[str]) -> List[List[float]]:
        self._fit(texts)
        vectors = []
        for text in texts:
            tokens = self._tokenize(text)
            counts: Dict[str, int] = {}
            for tok in tokens:
                counts[tok] = counts.get(tok, 0) + 1
            vec = np.zeros(self.dim, dtype=np.float32)
            for tok, cnt in counts.items():
                # Sublinear TF + smoothed IDF
                tf = 1 + np.log(cnt) if cnt > 0 else 0
                idf = np.log((self.n_docs + 1) / (self.df.get(tok, 1) + 1)) + 1
                vec[self._hash(tok)] += tf * idf
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec /= norm
            vectors.append(vec.tolist())
        return vectors


class KeywordEmbeddingProvider(EmbeddingProvider):
    """Fallback: bag-of-words pseudo-embeddings. Not semantic but deterministic."""

    def __init__(self, dim: int = 256):
        self.dim = dim
        self.vocab: Dict[str, int] = {}

    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r"[\u4e00-\u9fff]|\w+", text.lower())

    def embed(self, texts: List[str]) -> List[List[float]]:
        vectors = []
        for text in texts:
            tokens = self._tokenize(text)
            vec = np.zeros(self.dim, dtype=np.float32)
            for tok in tokens:
                idx = int(hashlib.md5(tok.encode()).hexdigest(), 16) % self.dim
                vec[idx] += 1.0
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec /= norm
            vectors.append(vec.tolist())
        return vectors


# ═══════════════════════════════════════════════════════════════════
# Vector database backends (pluggable)
# ═══════════════════════════════════════════════════════════════════

class MemoryBackend:
    """Abstract backend for semantic memory persistence/retrieval."""

    def add(self, memory: Dict) -> None:
        raise NotImplementedError

    def load(self) -> List[Dict]:
        raise NotImplementedError

    def recall(self, query_vec: np.ndarray, top_k: int, min_score: float) -> List[Tuple[float, Dict]]:
        raise NotImplementedError

    def list_all(self, limit: int) -> List[Dict]:
        raise NotImplementedError


class JsonMemoryBackend(MemoryBackend):
    """Default JSON-file backend (no extra dependencies)."""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> List[Dict]:
        if not self.path.exists():
            return []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("memories", [])
        except Exception as e:
            logger.warning(f"Failed to load JSON memory: {e}")
            return []

    def add(self, memory: Dict) -> None:
        memories = self.load()
        memories.append(memory)
        self._save(memories)

    def _save(self, memories: List[Dict]):
        try:
            tmp = self.path.with_suffix(".json.tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(
                    {"memories": memories, "updated": datetime.now(timezone.utc).isoformat()},
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
            tmp.replace(self.path)
        except Exception as e:
            logger.warning(f"Failed to save JSON memory: {e}")

    def recall(self, query_vec: np.ndarray, top_k: int, min_score: float) -> List[Tuple[float, Dict]]:
        memories = self.load()
        scores = []
        for mem in memories:
            mem_vec = np.array(mem.get("embedding", []), dtype=np.float32)
            if mem_vec.size == 0 or query_vec.size == 0:
                continue
            if mem_vec.shape != query_vec.shape:
                continue
            score = float(np.dot(query_vec, mem_vec) / (np.linalg.norm(query_vec) * np.linalg.norm(mem_vec)))
            if score >= min_score:
                scores.append((score, mem))
        scores.sort(key=lambda x: x[0], reverse=True)
        return scores[:top_k]

    def list_all(self, limit: int) -> List[Dict]:
        return [{"id": m["id"], "text": m["text"], "timestamp": m["timestamp"]}
                for m in self.load()[-limit:]]


class ChromaMemoryBackend(MemoryBackend):
    """ChromaDB persistent vector-store backend.

    Enabled by setting LAAP_VECTOR_DB=chromadb and having `chromadb` installed.
    Falls back to JSON backend if Chroma is unavailable at runtime.
    """

    def __init__(self, persist_dir: Path):
        import chromadb
        self.client = chromadb.PersistentClient(path=str(persist_dir))
        self.collection = self.client.get_or_create_collection(
            name="laap_memories",
            metadata={"hnsw:space": "cosine"},
        )

    def add(self, memory: Dict) -> None:
        self.collection.add(
            ids=[memory["id"]],
            documents=[memory["text"]],
            embeddings=[memory["embedding"]],
            metadatas=[{
                "timestamp": memory.get("timestamp", ""),
                **{k: json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else str(v)
                   for k, v in memory.get("meta", {}).items()},
            }],
        )

    def load(self) -> List[Dict]:
        try:
            data = self.collection.get(include=["documents", "embeddings", "metadatas"])
            memories = []
            for i, doc_id in enumerate(data.get("ids", [])):
                meta_raw = data["metadatas"][i] if data.get("metadatas") else {}
                meta = {}
                for k, v in meta_raw.items():
                    if k == "timestamp":
                        continue
                    try:
                        meta[k] = json.loads(v)
                    except Exception:
                        meta[k] = v
                memories.append({
                    "id": doc_id,
                    "text": data["documents"][i],
                    "embedding": data["embeddings"][i],
                    "timestamp": meta_raw.get("timestamp", ""),
                    "meta": meta,
                })
            return memories
        except Exception as e:
            logger.warning(f"ChromaDB load failed: {e}")
            return []

    def recall(self, query_vec: np.ndarray, top_k: int, min_score: float) -> List[Tuple[float, Dict]]:
        try:
            results = self.collection.query(
                query_embeddings=[query_vec.tolist()],
                n_results=top_k,
                include=["documents", "embeddings", "metadatas", "distances"],
            )
        except Exception as e:
            logger.warning(f"ChromaDB query failed: {e}")
            return []

        scores = []
        ids = results.get("ids", [[]])[0]
        docs = results.get("documents", [[]])[0]
        embeddings = results.get("embeddings", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for i, doc_id in enumerate(ids):
            if not doc_id:
                continue
            # Chroma cosine distance -> similarity
            distance = distances[i] if distances and len(distances) > i else 0.0
            score = max(0.0, 1.0 - float(distance))
            if score < min_score:
                continue
            meta_raw = metadatas[i] if metadatas and len(metadatas) > i else {}
            meta = {}
            for k, v in meta_raw.items():
                if k == "timestamp":
                    continue
                try:
                    meta[k] = json.loads(v)
                except Exception:
                    meta[k] = v
            mem = {
                "id": doc_id,
                "text": docs[i] if docs and len(docs) > i else "",
                "embedding": embeddings[i] if embeddings and len(embeddings) > i else [],
                "timestamp": meta_raw.get("timestamp", ""),
                "meta": meta,
            }
            scores.append((score, mem))
        scores.sort(key=lambda x: x[0], reverse=True)
        return scores

    def list_all(self, limit: int) -> List[Dict]:
        try:
            data = self.collection.get(include=["documents", "metadatas"])
            items = []
            ids = data.get("ids", [])
            docs = data.get("documents", [])
            metas = data.get("metadatas", [])
            for i in range(len(ids)):
                items.append({
                    "id": ids[i],
                    "text": docs[i] if i < len(docs) else "",
                    "timestamp": metas[i].get("timestamp", "") if i < len(metas) else "",
                })
            return items[-limit:]
        except Exception as e:
            logger.warning(f"ChromaDB list failed: {e}")
            return []


def _get_vector_db_backend(path: Path) -> MemoryBackend:
    """Choose vector database backend based on env and availability."""
    backend_name = os.environ.get("LAAP_VECTOR_DB", "json").lower()
    if backend_name == "chromadb":
        try:
            persist_dir = BRAIN_DIR / "memory" / "vector_db"
            persist_dir.mkdir(parents=True, exist_ok=True)
            backend = ChromaMemoryBackend(persist_dir)
            logger.info(f"Using ChromaDB vector memory backend at {persist_dir}")
            return backend
        except Exception as e:
            logger.warning(f"ChromaDB backend requested but unavailable: {e}; falling back to JSON")
    return JsonMemoryBackend(path)


def _get_embedding_provider() -> EmbeddingProvider:
    """Return best available embedding provider."""
    if os.environ.get("OPENAI_API_KEY") or os.environ.get("DEEPSEEK_API_KEY"):
        try:
            provider = OpenAIEmbeddingProvider()
            # 实际测试 API 是否可用
            provider.embed(["probe"])
            logger.info("Using OpenAI-compatible embedding API")
            return provider
        except Exception as e:
            logger.warning(f"OpenAI embedding API failed ({e}), falling back to local")

    try:
        return SentenceTransformersProvider()
    except Exception as e:
        logger.warning(f"Local embedding provider failed: {e}")

    logger.warning("Using pure-numpy TF-IDF embeddings (no torch required)")
    return TfidfEmbeddingProvider()


class LaapSemanticMemory:
    def __init__(self, path: Path = MEMORY_PATH):
        self.path = path
        self.provider = _get_embedding_provider()
        self.backend = _get_vector_db_backend(path)
        self.memories: List[Dict] = []
        self._load()

    def _load(self):
        try:
            self.memories = self.backend.load()
        except Exception as e:
            logger.warning(f"Failed to load semantic memory: {e}")
            self.memories = []

        # Re-embed memories if provider dimension changed
        expected_dim = None
        try:
            expected_dim = len(self.provider.embed(["probe"])[0])
        except Exception:
            pass
        reembedded = 0
        for mem in self.memories:
            emb = mem.get("embedding", [])
            if expected_dim and len(emb) != expected_dim:
                try:
                    mem["embedding"] = self.provider.embed([mem["text"]])[0]
                    reembedded += 1
                except Exception as e:
                    logger.warning(f"Re-embedding failed for {mem.get('id')}: {e}")
        if reembedded:
            logger.info(f"Re-embedded {reembedded} memories due to provider change")
            # For JSON backend we can rewrite; Chroma already stores updated embeddings below
            if isinstance(self.backend, JsonMemoryBackend):
                self.backend._save(self.memories)
        logger.info(f"Loaded {len(self.memories)} semantic memories")

    def add(self, text: str, meta: Optional[Dict] = None) -> str:
        """Add a memory with auto-computed embedding."""
        mem_id = hashlib.md5(f"{text}:{datetime.now(timezone.utc).isoformat()}".encode()).hexdigest()[:16]
        try:
            embedding = self.provider.embed([text])[0]
        except Exception as e:
            logger.warning(f"Embedding failed, using keyword fallback: {e}")
            embedding = KeywordEmbeddingProvider().embed([text])[0]

        memory = {
            "id": mem_id,
            "text": text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "embedding": embedding,
            "meta": meta or {},
        }
        self.memories.append(memory)
        try:
            self.backend.add(memory)
        except Exception as e:
            logger.warning(f"Backend add failed, falling back to JSON save: {e}")
            # Last resort: ensure JSON file is consistent
            if not isinstance(self.backend, JsonMemoryBackend):
                JsonMemoryBackend(self.path)._save(self.memories)
        return mem_id

    def recall(self, query: str, top_k: int = 5, min_score: float = 0.0) -> List[Dict]:
        """Retrieve top-k memories by cosine similarity."""
        if not self.memories:
            return []

        try:
            query_vec = np.array(self.provider.embed([query])[0], dtype=np.float32)
        except Exception as e:
            logger.warning(f"Query embedding failed: {e}")
            return []

        try:
            scores = self.backend.recall(query_vec, top_k=top_k, min_score=min_score)
        except Exception as e:
            logger.warning(f"Backend recall failed: {e}")
            return []

        results = []
        for score, mem in scores:
            item = {
                "id": mem["id"],
                "text": mem["text"],
                "timestamp": mem["timestamp"],
                "score": round(score, 4),
                "meta": mem.get("meta", {}),
            }
            results.append(item)
        return results

    def list_all(self, limit: int = 100) -> List[Dict]:
        return self.backend.list_all(limit=limit)


# Module-level singleton
_MEMORY: Optional[LaapSemanticMemory] = None


def get_memory() -> LaapSemanticMemory:
    global _MEMORY
    if _MEMORY is None:
        _MEMORY = LaapSemanticMemory()
    return _MEMORY


def add_memory(text: str, meta: Optional[Dict] = None) -> str:
    return get_memory().add(text, meta)


def recall_memory(query: str, top_k: int = 5, min_score: float = 0.0) -> List[Dict]:
    return get_memory().recall(query, top_k, min_score)
