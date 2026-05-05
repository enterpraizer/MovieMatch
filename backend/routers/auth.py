import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response

import metrics
from jose import JWTError, jwt

from config import get_settings
from dependencies import get_current_user, get_redis
from exceptions import (
    AccountDisabledError,
    EmailAlreadyTakenError,
    InvalidCredentialsError,
    TokenExpiredError,
    TokenRevokedError,
)
from schemas.auth import (
    ChangePasswordRequest,
    DeleteAccountRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    ResendVerificationRequest,
    TokenResponse,
    UpdateProfileRequest,
    UserResponse,
    UserStatsResponse,
    VerifyEmailRequest,
    VerifyEmailResponse,
)

router = APIRouter()

_BCRYPT_ROUNDS = 12
_MAX_PW_BYTES = 72


def _hash_password(password: str) -> str:
    pw = password.encode("utf-8")[:_MAX_PW_BYTES]
    return bcrypt.hashpw(pw, bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    try:
        pw = password.encode("utf-8")[:_MAX_PW_BYTES]
        return bcrypt.checkpw(pw, hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


_DUMMY_HASH = _hash_password("dummy-password-for-timing-safety")


def _new_verification_token() -> tuple[str, str]:
    """Return (raw_token, sha256_hash). Only the hash lives in DB."""
    raw = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return raw, token_hash


async def _issue_verification_token(user_id: str, email: str) -> None:
    """Create a fresh token row, invalidate previous unused ones, dispatch email."""
    from db.database import execute_write
    from services.email import send_verification_email

    raw, token_hash = _new_verification_token()
    settings = get_settings()
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.email_verification_ttl_minutes
    )
    # Mark any previous unused tokens as used so an old link can't race this one.
    await execute_write(
        "UPDATE email_verification_tokens SET used_at = now() "
        "WHERE user_id = $1::uuid AND used_at IS NULL",
        user_id,
    )
    await execute_write(
        "INSERT INTO email_verification_tokens (user_id, token_hash, expires_at) "
        "VALUES ($1::uuid, $2, $3)",
        user_id,
        token_hash,
        expires_at,
    )
    await send_verification_email(email, raw)


def _create_jwt(user_id: str, token_type: str, expires_delta: timedelta) -> tuple[str, str]:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    jti = str(uuid.uuid4())
    payload = {
        "sub": user_id,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
        "jti": jti,
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)
    return token, jti


def _build_tokens(user_id: str) -> TokenResponse:
    settings = get_settings()
    access_delta = timedelta(minutes=settings.access_token_expire_minutes)
    refresh_delta = timedelta(days=settings.refresh_token_expire_days)
    access_token, _ = _create_jwt(user_id, "access", access_delta)
    refresh_token, _ = _create_jwt(user_id, "refresh", refresh_delta)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=int(access_delta.total_seconds()),
    )


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(data: RegisterRequest) -> TokenResponse:
    from db.database import execute_one

    existing = await execute_one("SELECT id FROM users WHERE email = $1", data.email)
    if existing is not None:
        raise EmailAlreadyTakenError()

    password_hash = _hash_password(data.password)

    user = await execute_one(
        """
        INSERT INTO users (email, password_hash, display_name)
        VALUES ($1, $2, $3)
        RETURNING id::text AS id
        """,
        data.email,
        password_hash,
        data.display_name,
    )
    if user is None:
        raise InvalidCredentialsError()

    structlog.get_logger().info("user_registered", user_id=user["id"])
    metrics.auth_events.labels(event="register").inc()
    # Fire-and-forget: don't block the response on SMTP; user will see the
    # "check your inbox" screen immediately and can hit /resend-verification
    # if the first dispatch fails silently.
    try:
        await _issue_verification_token(user["id"], data.email)
    except Exception as e:
        structlog.get_logger().warning("verification_dispatch_failed", error=str(e))
    return _build_tokens(user["id"])


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest) -> TokenResponse:
    from db.database import execute_one

    user = await execute_one(
        "SELECT id::text AS id, email, password_hash, is_active FROM users WHERE email = $1",
        data.email,
    )
    hash_to_verify = user["password_hash"] if user else _DUMMY_HASH
    is_valid = _verify_password(data.password, hash_to_verify)

    if user is None or not is_valid:
        metrics.auth_events.labels(event="login_failure").inc()
        raise InvalidCredentialsError()
    if not user["is_active"]:
        metrics.auth_events.labels(event="login_failure").inc()
        raise AccountDisabledError()

    await execute_one(
        "UPDATE users SET last_login_at = now() WHERE id = $1::uuid RETURNING id",
        user["id"],
    )
    structlog.get_logger().info("user_login", user_id=user["id"])
    metrics.auth_events.labels(event="login_success").inc()
    return _build_tokens(user["id"])


@router.post("/verify-email", response_model=VerifyEmailResponse)
async def verify_email(data: VerifyEmailRequest) -> VerifyEmailResponse:
    from db.database import execute_one, execute_write

    token_hash = hashlib.sha256(data.token.encode("utf-8")).hexdigest()
    row = await execute_one(
        """
        SELECT t.id, t.user_id::text AS user_id, t.expires_at, t.used_at,
               u.email, u.email_verified
        FROM email_verification_tokens t
        JOIN users u ON u.id = t.user_id
        WHERE t.token_hash = $1
        """,
        token_hash,
    )
    if row is None:
        raise HTTPException(
            status_code=400,
            detail={"code": "TOKEN_INVALID", "message": "Link is invalid."},
        )

    # Idempotent: if already used (because the same user clicked twice, or the
    # account is already verified), just reply 200 with already_verified=true.
    if row["email_verified"]:
        return VerifyEmailResponse(email=row["email"], already_verified=True)

    if row["used_at"] is not None:
        raise HTTPException(
            status_code=400,
            detail={"code": "TOKEN_USED", "message": "Link was already used."},
        )
    if row["expires_at"] < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=400,
            detail={"code": "TOKEN_EXPIRED", "message": "Link has expired. Request a new one."},
        )

    await execute_write(
        "UPDATE users SET email_verified = TRUE WHERE id = $1::uuid",
        row["user_id"],
    )
    await execute_write(
        "UPDATE email_verification_tokens SET used_at = now() WHERE id = $1",
        row["id"],
    )
    structlog.get_logger().info("email_verified", user_id=row["user_id"])
    metrics.auth_events.labels(event="email_verified").inc()
    return VerifyEmailResponse(email=row["email"], already_verified=False)


@router.post("/resend-verification", status_code=204)
async def resend_verification(
    data: ResendVerificationRequest, redis: Any = Depends(get_redis)
) -> Response:
    from db.database import execute_one

    # Light rate limit: max 3 resends per email per 5 minutes.
    key = f"resend_verif:{data.email.lower()}"
    cnt = await redis.incr(key)
    if cnt == 1:
        await redis.expire(key, 300)
    if cnt > 3:
        raise HTTPException(
            status_code=429,
            detail={"code": "RATE_LIMITED", "message": "Too many attempts. Try again later."},
        )

    user = await execute_one(
        "SELECT id::text AS id, email, email_verified FROM users WHERE email = $1",
        data.email,
    )
    # Respond 204 whether or not the email exists — avoids account enumeration.
    if user is None or user["email_verified"]:
        return Response(status_code=204)

    try:
        await _issue_verification_token(user["id"], user["email"])
    except Exception as e:
        structlog.get_logger().warning("resend_failed", error=str(e))
    return Response(status_code=204)


async def _decode(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except jwt.ExpiredSignatureError:
        raise TokenExpiredError()
    except JWTError:
        raise TokenRevokedError()


@router.post("/refresh", response_model=TokenResponse)
async def refresh(data: RefreshRequest, redis: Any = Depends(get_redis)) -> TokenResponse:
    payload = await _decode(data.refresh_token)
    if payload.get("type") != "refresh":
        raise TokenRevokedError()

    jti = payload.get("jti", "")
    if await redis.get(f"blacklist:{jti}"):
        raise TokenRevokedError()

    user_id = payload.get("sub", "")
    revoked_raw = await redis.get(f"user_revoked:{user_id}")
    if revoked_raw is not None:
        revoked_at = int(revoked_raw)
        token_iat = int(payload.get("iat", 0))
        if token_iat < revoked_at:
            raise TokenRevokedError()

    exp_ts = int(payload.get("exp", 0))
    now_ts = int(datetime.now(timezone.utc).timestamp())
    remaining = max(exp_ts - now_ts, 1)
    await redis.setex(f"blacklist:{jti}", remaining, "1")

    return _build_tokens(user_id)


@router.post("/logout", status_code=204)
async def logout(data: RefreshRequest, redis: Any = Depends(get_redis)) -> Response:
    settings = get_settings()
    metrics.auth_events.labels(event="logout").inc()
    try:
        payload = jwt.decode(
            data.refresh_token,
            settings.secret_key,
            algorithms=[settings.algorithm],
            options={"verify_exp": False},
        )
        jti = payload.get("jti", "")
        exp_ts = int(payload.get("exp", 0))
        now_ts = int(datetime.now(timezone.utc).timestamp())
        remaining = max(exp_ts - now_ts, 1)
        if jti:
            await redis.setex(f"blacklist:{jti}", remaining, "1")
    except JWTError:
        pass
    return Response(status_code=204)


def _to_user_response(row: dict[str, Any]) -> UserResponse:
    return UserResponse(
        id=row["id"],
        email=row["email"],
        display_name=row["display_name"],
        avatar_url=row.get("avatar_url"),
        bio=row.get("bio"),
        email_verified=bool(row.get("email_verified", True)),
        created_at=row["created_at"].isoformat(),
        last_login_at=row["last_login_at"].isoformat() if row.get("last_login_at") else None,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict[str, Any] = Depends(get_current_user)) -> UserResponse:
    from db.database import execute_one

    row = await execute_one(
        "SELECT id::text AS id, email, display_name, avatar_url, bio, "
        "       email_verified, created_at, last_login_at "
        "FROM users WHERE id = $1::uuid",
        current_user["id"],
    )
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "USER_NOT_FOUND"})
    return _to_user_response(dict(row))


@router.patch("/me", response_model=UserResponse)
async def update_me(
    data: UpdateProfileRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> UserResponse:
    from db.database import execute_one

    updates: list[str] = []
    values: list[Any] = []
    idx = 1
    if data.display_name is not None:
        updates.append(f"display_name = ${idx}")
        values.append(data.display_name)
        idx += 1
    if data.avatar_url is not None:
        updates.append(f"avatar_url = ${idx}")
        values.append(data.avatar_url or None)
        idx += 1
    if data.bio is not None:
        updates.append(f"bio = ${idx}")
        values.append(data.bio or None)
        idx += 1

    if not updates:
        raise HTTPException(status_code=400, detail={"code": "NO_FIELDS"})

    updates.append("updated_at = now()")
    values.append(current_user["id"])
    query = (
        f"UPDATE users SET {', '.join(updates)} WHERE id = ${idx}::uuid "
        "RETURNING id::text AS id, email, display_name, avatar_url, bio, "
        "          email_verified, created_at, last_login_at"
    )
    row = await execute_one(query, *values)
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "USER_NOT_FOUND"})
    return _to_user_response(dict(row))


@router.post("/change-password", status_code=204)
async def change_password(
    data: ChangePasswordRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> Response:
    from db.database import execute_one

    row = await execute_one(
        "SELECT password_hash FROM users WHERE id = $1::uuid",
        current_user["id"],
    )
    if row is None or not _verify_password(data.current_password, row["password_hash"]):
        raise InvalidCredentialsError()

    new_hash = _hash_password(data.new_password)
    await execute_one(
        "UPDATE users SET password_hash = $1, updated_at = now() WHERE id = $2::uuid "
        "RETURNING id",
        new_hash,
        current_user["id"],
    )
    structlog.get_logger().info("password_changed", user_id=current_user["id"])
    metrics.auth_events.labels(event="password_change").inc()
    return Response(status_code=204)


@router.delete("/me", status_code=204)
async def delete_me(
    data: DeleteAccountRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    redis: Any = Depends(get_redis),
) -> Response:
    from db.database import execute_one
    from services.cache import invalidate_user

    row = await execute_one(
        "SELECT password_hash FROM users WHERE id = $1::uuid",
        current_user["id"],
    )
    if row is None or not _verify_password(data.password, row["password_hash"]):
        raise InvalidCredentialsError()

    user_id = current_user["id"]

    # DB cascade handles: ratings, watchlist, user_embeddings (ON DELETE CASCADE)
    await execute_one(
        "DELETE FROM users WHERE id = $1::uuid RETURNING id",
        user_id,
    )
    # Wipe personalised caches (recommendation results keyed by user_id)
    await invalidate_user(redis, str(user_id))
    # Block any outstanding refresh tokens for this user. We can't enumerate
    # issued JTIs (JWTs are stateless), so we plant a per-user "revoked after"
    # marker; refresh checks it against the token's iat.
    settings = get_settings()
    ttl = int(timedelta(days=settings.refresh_token_expire_days).total_seconds())
    revoked_at = int(datetime.now(timezone.utc).timestamp())
    await redis.setex(f"user_revoked:{user_id}", ttl, str(revoked_at))

    structlog.get_logger().info("account_deleted", user_id=str(user_id))
    metrics.auth_events.labels(event="account_delete").inc()
    return Response(status_code=204)


@router.get("/me/stats", response_model=UserStatsResponse)
async def get_me_stats(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> UserStatsResponse:
    from db.database import execute_one, execute_query

    summary = await execute_one(
        """
        SELECT COUNT(*)::int AS total,
               AVG(score)::float AS avg_score,
               MIN(created_at) AS first_at,
               MAX(created_at) AS last_at
        FROM ratings WHERE user_id = $1::uuid
        """,
        current_user["id"],
    )
    total = int(summary["total"]) if summary else 0

    genres: list[dict[str, Any]] = []
    score_dist: dict[str, int] = {}
    if total > 0:
        genre_rows = await execute_query(
            """
            SELECT g.slug, g.name, COUNT(*)::int AS cnt
            FROM ratings r
            JOIN movie_genres mg ON mg.movie_id = r.movie_id
            JOIN genres g ON g.id = mg.genre_id
            WHERE r.user_id = $1::uuid
            GROUP BY g.id, g.slug, g.name
            ORDER BY cnt DESC
            LIMIT 10
            """,
            current_user["id"],
        )
        genres = [dict(r) for r in genre_rows]

        dist_rows = await execute_query(
            """
            SELECT score::text AS score, COUNT(*)::int AS cnt
            FROM ratings WHERE user_id = $1::uuid
            GROUP BY score ORDER BY score
            """,
            current_user["id"],
        )
        score_dist = {r["score"]: int(r["cnt"]) for r in dist_rows}

    return UserStatsResponse(
        total_ratings=total,
        avg_rating=float(summary["avg_score"]) if summary and summary["avg_score"] is not None else None,
        first_rated_at=summary["first_at"].isoformat() if summary and summary["first_at"] else None,
        last_rated_at=summary["last_at"].isoformat() if summary and summary["last_at"] else None,
        top_genres=[{"slug": g["slug"], "name": g["name"], "count": g["cnt"]} for g in genres],
        score_distribution=score_dist,
    )
