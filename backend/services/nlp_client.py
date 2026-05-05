from typing import Any

import httpx

from config import get_settings
from exceptions import MLServiceUnavailableError


async def search(
    query: str,
    limit: int,
    filters: dict[str, Any] | None = None,
    offset: int = 0,
) -> list[dict[str, Any]]:
    settings = get_settings()
    payload: dict[str, Any] = {"query": query, "limit": limit, "offset": offset}
    if filters:
        # NLP service expects filters flattened into top-level fields.
        for k in ("year_from", "year_to", "min_rating"):
            if filters.get(k) is not None:
                payload[k] = filters[k]

    try:
        async with httpx.AsyncClient(
            base_url=settings.ml_nlp_url,
            timeout=httpx.Timeout(connect=2.0, read=5.0, write=5.0, pool=5.0),
        ) as client:
            resp = await client.post("/search", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return list(data.get("items", data) if isinstance(data, dict) else data)
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError):
        raise MLServiceUnavailableError("nlp")
