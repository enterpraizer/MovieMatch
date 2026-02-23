from __future__ import annotations

import json
from typing import Any

import redis

from apps.common.settings import settings

_memory_cache: dict[str, str] = {}


class CacheClient:
    def __init__(self) -> None:
        self._redis: redis.Redis | None = None
        try:
            self._redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)
            self._redis.ping()
        except Exception:
            self._redis = None

    def get_json(self, key: str) -> dict[str, Any] | None:
        raw: str | None
        if self._redis is not None:
            raw = self._redis.get(key)
        else:
            raw = _memory_cache.get(key)
        if not raw:
            return None
        return json.loads(raw)

    def set_json(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        payload = json.dumps(value)
        if self._redis is not None:
            self._redis.setex(key, ttl_seconds, payload)
        else:
            _memory_cache[key] = payload

