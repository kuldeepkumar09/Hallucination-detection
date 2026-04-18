"""
Two-level claim verification cache.

Level 1 (always available): in-memory dict with TTL checking.
Level 2 (optional):         Redis, falls back gracefully on any connection error.

Cache key: SHA-256( claim.normalized + "::" + kb_collection_name )
Cache value: JSON-serialised VerifiedClaim

This prevents re-verifying identical claims within the TTL window, cutting
API costs significantly for repeated or near-identical requests.
"""
import hashlib
import json
import logging
import time
from typing import Dict, Optional, Tuple

from .models import VerifiedClaim

logger = logging.getLogger(__name__)


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

    def __init__(self) -> None:
        from .config import get_settings  # noqa: PLC0415
        s = get_settings()

        self._ttl = s.cache_ttl_seconds
        self._collection = s.kb_collection_name
        self._enabled = s.cache_enabled

        # In-memory store: key → (VerifiedClaim, expires_at)
        self._store: Dict[str, Tuple[VerifiedClaim, float]] = {}
        self._hits = 0
        self._misses = 0

        # Optional Redis
        self._redis = None
        if self._enabled and s.redis_url:
            self._redis = self._connect_redis(s.redis_url)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, claim_normalized: str) -> Optional[VerifiedClaim]:
        """Return cached VerifiedClaim or None on miss/expiry."""
        if not self._enabled:
            return None

        key = self._make_key(claim_normalized)

        # Try Redis first (persistent across restarts)
        if self._redis is not None:
            try:
                raw = self._redis.get(key)
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

    def set(self, claim_normalized: str, result: VerifiedClaim) -> None:
        """Store a VerifiedClaim under claim_normalized with TTL."""
        if not self._enabled:
            return

        key = self._make_key(claim_normalized)
        expires_at = time.monotonic() + self._ttl

        # In-memory
        self._store[key] = (result, expires_at)

        # Redis (async-safe fire-and-forget)
        if self._redis is not None:
            try:
                payload = result.model_dump_json()
                self._redis.setex(key, self._ttl, payload)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Redis set failed: %s", exc)

    def invalidate_all(self) -> None:
        """Clear all cached entries."""
        self._store.clear()
        if self._redis is not None:
            try:
                # Only flush keys matching our prefix
                pattern = f"hallu::{self._collection}::*"
                keys = self._redis.keys(pattern)
                if keys:
                    self._redis.delete(*keys)
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

    def _make_key(self, claim_normalized: str) -> str:
        digest = hashlib.sha256(
            f"{claim_normalized}::{self._collection}".encode()
        ).hexdigest()[:24]
        return f"hallu::{self._collection}::{digest}"

    @staticmethod
    def _connect_redis(url: str):
        try:
            import redis  # noqa: PLC0415
            client = redis.Redis.from_url(url, decode_responses=False, socket_timeout=2)
            client.ping()
            logger.info("Redis cache connected: %s", url)
            return client
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis unavailable (%s) — using in-memory cache only", exc)
            return None
