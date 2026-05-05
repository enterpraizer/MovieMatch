import hashlib
import json
from typing import Any


def _params_key(params: dict[str, Any] | None) -> str:
    if not params:
        return "none"
    payload = json.dumps(params, sort_keys=True, default=str)
    return hashlib.sha1(payload.encode()).hexdigest()[:16]


def _build_key(user_id: str, endpoint: str, params: dict[str, Any] | None) -> str:
    return f"reco:{user_id}:{endpoint}:{_params_key(params)}"


async def get_cached(
    redis: Any,
    user_id: str,
    endpoint: str,
    params: dict[str, Any] | None,
) -> dict[str, Any] | None:
    raw = await redis.get(_build_key(user_id, endpoint, params))
    if not raw:
        return None
    try:
        return dict(json.loads(raw))
    except (ValueError, TypeError):
        return None


async def set_cached(
    redis: Any,
    user_id: str,
    endpoint: str,
    params: dict[str, Any] | None,
    data: dict[str, Any],
    ttl: int = 1800,
) -> None:
    await redis.setex(_build_key(user_id, endpoint, params), ttl, json.dumps(data, default=str))


async def invalidate_user(redis: Any, user_id: str) -> None:
    pattern = f"reco:{user_id}:*"
    keys: list[str] = []
    async for key in redis.scan_iter(match=pattern, count=100):
        keys.append(key)
        if len(keys) >= 500:
            await redis.delete(*keys)
            keys.clear()
    if keys:
        await redis.delete(*keys)
