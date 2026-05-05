from typing import Any

import httpx

from config import get_settings
from exceptions import MLServiceUnavailableError


async def get_recommendations(
    ratings: list[dict[str, Any]],
    k: int,
) -> list[dict[str, Any]]:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(
            base_url=settings.ml_recsys_url,
            timeout=httpx.Timeout(connect=2.0, read=8.0, write=5.0, pool=5.0),
        ) as client:
            resp = await client.post("/recommend", json={"ratings": ratings, "k": k})
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict):
                return list(data.get("results") or data.get("items") or [])
            return list(data)
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError):
        raise MLServiceUnavailableError("recsys")
