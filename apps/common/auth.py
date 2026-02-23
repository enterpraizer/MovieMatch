from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext

from apps.common.schemas import LoginResponse, TokenPayload
from apps.common.settings import settings

password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return password_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return password_context.verify(password, password_hash)


def _create_token(user_id: int, email: str, token_type: str, expires_delta: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_token_pair(user_id: int, email: str) -> LoginResponse:
    access_expires = timedelta(minutes=settings.access_token_expire_minutes)
    refresh_expires = timedelta(days=settings.refresh_token_expire_days)
    access_token = _create_token(user_id=user_id, email=email, token_type="access", expires_delta=access_expires)
    refresh_token = _create_token(user_id=user_id, email=email, token_type="refresh", expires_delta=refresh_expires)
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user_id=user_id,
        expires_in=settings.access_token_expire_minutes * 60,
    )


def decode_token(token: str, expected_type: str) -> TokenPayload:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    token_payload = TokenPayload.model_validate(payload)
    if token_payload.type != expected_type:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
    return token_payload


def require_access_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> TokenPayload:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization token")
    return decode_token(credentials.credentials, expected_type="access")

