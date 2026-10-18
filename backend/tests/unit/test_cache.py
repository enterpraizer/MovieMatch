import json
from collections.abc import AsyncIterator
from typing import Any

from redis.asyncio import Redis

from services import cache


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.store[key] = value
        self.ttls[key] = ttl

    async def scan_iter(self, match: str, count: int) -> AsyncIterator[str]:
        prefix = match.rstrip("*")
        for key in list(self.store):
            if key.startswith(prefix):
                yield key

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self.store.pop(key, None)


def _fake() -> tuple[FakeRedis, Redis]:
    fake = FakeRedis()
    return fake, fake  # type: ignore[return-value]


def test_params_key_is_order_independent() -> None:
    a = cache._params_key({"a": 1, "b": [2, 3]})
    b = cache._params_key({"b": [2, 3], "a": 1})
    assert a == b
    assert len(a) == 16
    assert cache._params_key(None) == "none"
    assert cache._params_key({}) == "none"


async def test_roundtrip() -> None:
    fake, redis = _fake()
    params: dict[str, Any] = {"limit": 5}
    assert await cache.get_cached(redis, "u1", "collab", params) is None
    await cache.set_cached(redis, "u1", "collab", params, {"x": 1}, ttl=60)
    assert await cache.get_cached(redis, "u1", "collab", params) == {"x": 1}
    assert list(fake.ttls.values()) == [60]


async def test_corrupt_entry_is_a_miss() -> None:
    fake, redis = _fake()
    fake.store[cache._build_key("u1", "collab", None)] = "{not json"
    assert await cache.get_cached(redis, "u1", "collab", None) is None
    fake.store[cache._build_key("u1", "collab", None)] = json.dumps([1, 2])
    assert await cache.get_cached(redis, "u1", "collab", None) is None


async def test_invalidate_user_only_removes_that_user() -> None:
    fake, redis = _fake()
    await cache.set_cached(redis, "u1", "collab", {"a": 1}, {"v": 1})
    await cache.set_cached(redis, "u1", "search", None, {"v": 2})
    await cache.set_cached(redis, "u2", "collab", {"a": 1}, {"v": 3})
    await cache.invalidate_user(redis, "u1")
    assert all(k.startswith("reco:u2:") for k in fake.store)
    assert len(fake.store) == 1


async def test_invalidate_user_batches_large_scans() -> None:
    fake, redis = _fake()
    for i in range(1200):
        fake.store[f"reco:u1:e:{i}"] = "{}"
    await cache.invalidate_user(redis, "u1")
    assert fake.store == {}
