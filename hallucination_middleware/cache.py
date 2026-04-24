"""
Two-level claim verification cache with semantic similarity.

Level 1 (always available): in-memory dict with TTL checking.
Level 2 (optional):         Redis, falls back gracefully on any connection error.
Level 3 (semantic):         Vector similarity for near-duplicate queries.

Cache key: SHA-256( claim.normalized + "::" + kb_collection_name )
Cache value: JSON-serialised VerifiedClaim

This prevents re-verifying identical claims within the TTL window, cutting
API costs significantly for repeated or near-identical requests.
"""
import asyncio
import hashlib
import json
import logging
import threading
import time
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

import chromadb
from chromadb.config import Settings as ChromaSettings

from .models import VerifiedClaim

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SentenceTransformer singleton — loaded once at first use, shared across all
# ClaimCache instances. Avoids reloading 90 MB model on every embedding call.
# ---------------------------------------------------------------------------

_ST_MODEL = None
_ST_LOCK = threading.Lock()


def _get_st_model():
    global _ST_MODEL
    if _ST_MODEL is not None:
        return _ST_MODEL
    with _ST_LOCK:
        if _ST_MODEL is not None:
            return _ST_MODEL
        try:
            from sentence_transformers import SentenceTransformer  # noqa: PLC0415
            import torch  # noqa: PLC0415
            device = "cuda" if torch.cuda.is_available() else "cpu"
            _ST_MODEL = SentenceTransformer("all-MiniLM-L6-v2", device=device)
            logger.info("[Cache] SentenceTransformer loaded on %s", device)
        except ImportError:
            logger.debug("[Cache] sentence-transformers not installed; semantic cache will use Ollama fallback")
        except Exception as exc:
            logger.warning("[Cache] Failed to load SentenceTransformer: %s", exc)
    return _ST_MODEL


class ClaimCache:
    """
    Thread-safe in-memory LRU/TTL cache with optional Redis backing.

    Usage:
        cache = ClaimCache()
        hit = cache.get("Einstein was born in 1879")
        if hit is None:
            result = await verify(...)
            cache.set("Einstein was born in 1879", result)
    """

    def __init__(self, kb_version_fn: Optional[Callable[[], str]] = None) -> None:
        from .config import get_settings  # noqa: PLC0415
        s = get_settings()

        self._ttl = s.cache_ttl_seconds
        self._collection = s.kb_collection_name
        self._enabled = s.cache_enabled
        self._kb_version_fn = kb_version_fn or (lambda: "")

        # In-memory store: key → (VerifiedClaim, expires_at)
        self._store: Dict[str, Tuple[VerifiedClaim, float]] = {}
        self._hits = 0
        self._misses = 0

        # Semantic cache: ChromaDB for vector similarity
        self._semantic_enabled = s.semantic_cache_enabled
        self._semantic_threshold = s.semantic_cache_threshold  # e.g., 0.9
        self._chroma_client = None
        self._semantic_collection = None
        if self._semantic_enabled:
            try:
                chroma_path = Path(s.chroma_db_path) / "semantic_cache"
                chroma_path.mkdir(parents=True, exist_ok=True)
                self._chroma_client = chromadb.PersistentClient(
                    path=str(chroma_path),
                    settings=ChromaSettings(anonymized_telemetry=False),
                )
                self._semantic_collection = self._chroma_client.get_or_create_collection(
                    name="semantic_cache",
                    metadata={"hnsw:space": "cosine"},
                )
                logger.info("Semantic cache initialized with ChromaDB")
            except Exception as exc:
                logger.warning("Failed to initialize semantic cache: %s", exc)
                self._semantic_enabled = False

        # File-based persistence — survives restarts when Redis is unavailable
        self._disk_path = Path(f"./hallu_cache_{self._collection}.json")
        # Optional Fernet encryption — keeps LLM output opaque on disk
        self._fernet = None
        enc_key = s.cache_encryption_key.strip()
        if enc_key:
            try:
                from cryptography.fernet import Fernet  # noqa: PLC0415
                self._fernet = Fernet(enc_key.encode())
                logger.info("[Cache] Disk encryption enabled (Fernet)")
            except Exception as exc:
                logger.warning("[Cache] Failed to init Fernet encryption (%s) — storing plaintext", exc)
        if self._enabled:
            self._load_disk_cache()

        # Optional async Redis (redis.asyncio keeps the event loop unblocked)
        self._redis = None
        if self._enabled and s.redis_url:
            self._redis = self._connect_redis_async(s.redis_url)

    async def _get_embedding(self, text: str) -> Optional[list[float]]:
        """Get embedding using the shared SentenceTransformer singleton (GPU-aware)."""
        model = _get_st_model()
        if model is not None:
            try:
                embedding = await asyncio.to_thread(
                    lambda: model.encode(text, convert_to_numpy=True).tolist()
                )
                return embedding
            except Exception as exc:
                logger.warning("[Cache] Embedding failed: %s", exc)
                return None
        # Fallback: Ollama local embeddings
        from .config import get_settings  # noqa: PLC0415
        s = get_settings()
        try:
            from openai import AsyncOpenAI  # noqa: PLC0415
            client = AsyncOpenAI(base_url=s.ollama_base_url, api_key=s.ollama_api_key)
            response = await client.embeddings.create(model="phi3:mini", input=text)
            return response.data[0].embedding
        except Exception as exc:
            logger.warning("[Cache] Ollama embedding fallback failed: %s", exc)
            return None

    async def _semantic_get(self, query: str) -> Optional[VerifiedClaim]:
        """Check semantic cache for similar queries."""
        if not self._semantic_enabled or not self._semantic_collection:
            return None
        embedding = await self._get_embedding(query)
        if not embedding:
            return None
        try:
            results = self._semantic_collection.query(
                query_embeddings=[embedding],
                n_results=1,
                include=["metadatas", "distances"],
            )
            distances = results.get("distances", [])
            # Chroma cosine space returns distance = 1 - similarity, so low distance = high similarity
            if distances and distances[0] and distances[0][0] < (1 - self._semantic_threshold):
                metadatas = results.get("metadatas", [])
                if metadatas and metadatas[0]:
                    metadata = metadatas[0][0]
                    return VerifiedClaim(**json.loads(metadata["claim"]))
        except Exception as exc:
            logger.warning("Semantic cache query failed: %s", exc)
        return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get(self, claim_normalized: str) -> Optional[VerifiedClaim]:
        """Return cached VerifiedClaim or None on miss/expiry."""
        if not self._enabled:
            return None

        key = self._make_key(claim_normalized)

        # Try semantic cache first (for near-duplicates)
        semantic_hit = await self._semantic_get(claim_normalized)
        if semantic_hit:
            self._hits += 1
            logger.debug("[semantic cache hit] %s", claim_normalized[:60])
            return semantic_hit

        # Try Redis first (persistent across restarts)
        if self._redis is not None:
            try:
                raw = await self._redis.get(key)
                if raw:
                    self._hits += 1
                    return VerifiedClaim.model_validate(json.loads(raw))
            except Exception as exc:  # noqa: BLE001
                logger.debug("Redis get failed: %s", exc)

        # Fall back to in-memory
        entry = self._store.get(key)
        if entry is not None:
            result, expires_at = entry
            if time.monotonic() < expires_at:
                self._hits += 1
                return result
            # Expired
            del self._store[key]

        self._misses += 1
        return None

    async def set(self, claim_normalized: str, result: VerifiedClaim) -> None:
        """Store a VerifiedClaim under claim_normalized with TTL."""
        if not self._enabled:
            return

        key = self._make_key(claim_normalized)
        expires_at = time.monotonic() + self._ttl

        # In-memory
        self._store[key] = (result, expires_at)

        # Disk persistence (fire-and-forget, best effort — offloaded to thread pool)
        await asyncio.to_thread(self._save_disk_cache)

        # Redis (async-safe fire-and-forget)
        if self._redis is not None:
            try:
                payload = result.model_dump_json()
                await self._redis.setex(key, self._ttl, payload)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Redis set failed: %s", exc)

        # Semantic cache
        if self._semantic_enabled and self._semantic_collection:
            try:
                embedding = await self._get_embedding(claim_normalized)
                if embedding:
                    self._semantic_collection.upsert(
                        embeddings=[embedding],
                        metadatas=[{"claim": result.model_dump_json(), "key": key}],
                        ids=[key],
                    )
            except Exception as exc:
                logger.warning("Semantic cache set failed: %s", exc)

    async def invalidate_all(self) -> None:
        """Clear all cached entries (memory + disk + Redis)."""
        self._store.clear()
        try:
            if self._disk_path.exists():
                self._disk_path.unlink()
        except Exception:
            pass
        if self._redis is not None:
            try:
                # Only flush keys matching our prefix
                pattern = f"hallu::{self._collection}::*"
                keys = await self._redis.keys(pattern)
                if keys:
                    await self._redis.delete(*keys)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Redis flush failed: %s", exc)

        logger.info("Cache invalidated")

    def stats(self) -> Dict:
        """Return hit/miss counters and current size."""
        total = self._hits + self._misses
        hit_rate = self._hits / total if total else 0.0
        # Count non-expired in-memory entries
        now = time.monotonic()
        live = sum(1 for _, exp in self._store.values() if exp > now)
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(hit_rate, 3),
            "in_memory_entries": live,
            "redis_connected": self._redis is not None,
            "ttl_seconds": self._ttl,
            "enabled": self._enabled,
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _load_disk_cache(self) -> None:
        if not self._disk_path.exists():
            return
        try:
            raw_bytes = self._disk_path.read_bytes()
            if self._fernet is not None:
                try:
                    raw_bytes = self._fernet.decrypt(raw_bytes)
                except Exception:
                    logger.debug("[Cache] Disk cache decryption failed — skipping (key change?)")
                    return
            raw = json.loads(raw_bytes.decode("utf-8"))
            # Disk stores wall-clock expiry (time.time()) so cross-restart comparison works.
            # Convert back to monotonic for in-memory use.
            now_wall = time.time()
            now_mono = time.monotonic()
            loaded = 0
            for key, (vc_raw, wall_exp) in raw.items():
                if wall_exp > now_wall:
                    mono_exp = now_mono + (wall_exp - now_wall)
                    self._store[key] = (VerifiedClaim.model_validate(vc_raw), mono_exp)
                    loaded += 1
            if loaded:
                logger.info("Loaded %d cached claims from disk (%s)", loaded, self._disk_path)
        except Exception as exc:
            logger.debug("Disk cache load failed: %s", exc)

    def _save_disk_cache(self) -> None:
        try:
            now_mono = time.monotonic()
            now_wall = time.time()
            # Convert monotonic expiry to wall-clock so the value survives process restart.
            data = {
                k: (vc.model_dump(mode="json"), now_wall + (exp - now_mono))
                for k, (vc, exp) in self._store.items()
                if exp > now_mono
            }
            payload = json.dumps(data).encode("utf-8")
            if self._fernet is not None:
                payload = self._fernet.encrypt(payload)
            self._disk_path.write_bytes(payload)
        except Exception as exc:
            logger.debug("Disk cache save failed: %s", exc)

    def _make_key(self, claim_normalized: str) -> str:
        kb_version = self._kb_version_fn() or "base"
        digest = hashlib.sha256(
            f"{claim_normalized}::{self._collection}::{kb_version}".encode()
        ).hexdigest()[:24]
        return f"hallu::{self._collection}::{kb_version}::{digest}"

    @staticmethod
    def _connect_redis_async(url: str):
        try:
            import redis.asyncio as aioredis  # noqa: PLC0415
            client = aioredis.Redis.from_url(url, decode_responses=False)
            logger.info("Redis async client created: %s", url)
            return client
        except Exception as exc:  # noqa: BLE001
            logger.warning("redis.asyncio unavailable (%s) — using in-memory cache only", exc)
            return None
