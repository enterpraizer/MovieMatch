from typing import Any

import httpx

from config import get_settings
from exceptions import FaceNotDetectedError, MLServiceUnavailableError


async def detect_emotion(image_bytes: bytes) -> dict[str, Any]:
    settings = get_settings()
    files = {"image": ("upload.bin", image_bytes, "application/octet-stream")}
    try:
        async with httpx.AsyncClient(
            base_url=settings.ml_cv_url,
            timeout=httpx.Timeout(connect=2.0, read=10.0, write=5.0, pool=5.0),
        ) as client:
            resp = await client.post("/detect", files=files)
            del files
            if resp.status_code == 422:
                try:
                    body = resp.json()
                    # FastAPI wraps HTTPException payloads in `{"detail": {...}}`;
                    # some handlers use `error` instead. Cover both.
                    detail = body.get("detail") or body.get("error") or {}
                    code = (
                        detail.get("code")
                        if isinstance(detail, dict)
                        else body.get("code", "")
                    )
                except Exception:
                    code = ""
                if code == "FACE_NOT_DETECTED":
                    raise FaceNotDetectedError()
            resp.raise_for_status()
            return dict(resp.json())
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError):
        raise MLServiceUnavailableError("cv")
