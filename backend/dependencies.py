from typing import Any, AsyncGenerator

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from config import get_settings
from db.database import get_connection

security = HTTPBearer(auto_error=False)


async def get_db() -> AsyncGenerator[Any, None]:
    """Yields asyncpg connection from pool."""
    async with get_connection() as conn:
        yield conn


async def get_redis(request: Request) -> Any:
    """Returns Redis client from app state."""
    return request.app.state.redis


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Any = Depends(get_db),
) -> dict[str, Any]:
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "MISSING_TOKEN", "message": "Authorization header required"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        settings = get_settings()
        payload = jwt.decode(
            credentials.credentials,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )

        if payload.get("type") != "access":
            raise HTTPException(
                status_code=401,
                detail={"code": "INVALID_TOKEN_TYPE", "message": "Access token required"},
            )

        user_id: str | None = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=401,
                detail={"code": "INVALID_TOKEN", "message": "Token missing subject"},
            )

    except JWTError as e:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "INVALID_TOKEN",
                "message": f"Token validation failed: {str(e)}",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await db.fetchrow(
        "SELECT id::text, email, display_name, is_active, email_verified "
        "FROM users WHERE id = $1::uuid",
        user_id,
    )

    if user is None:
        raise HTTPException(status_code=401, detail={"code": "USER_NOT_FOUND"})

    if not user["is_active"]:
        raise HTTPException(status_code=403, detail={"code": "ACCOUNT_DISABLED"})

    return dict(user)


async def get_verified_user(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Same as get_current_user but rejects users who haven't verified email.
    Attach to endpoints that mutate user data (ratings, watchlist, etc.)."""
    if not current_user.get("email_verified", False):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "EMAIL_NOT_VERIFIED",
                "message": "Please verify your email before taking this action.",
            },
        )
    return current_user


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Any = Depends(get_db),
) -> dict[str, Any] | None:
    """Returns user dict if authenticated, None otherwise (no error)."""
    if credentials is None:
        return None
    try:
        return await get_current_user(credentials=credentials, db=db)
    except HTTPException:
        return None
