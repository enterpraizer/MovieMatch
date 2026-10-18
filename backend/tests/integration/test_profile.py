import hashlib
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import Client

from tests.conftest import Db


def _register(api: Client, prefix: str = "prof") -> dict[str, Any]:
    email = f"{prefix}_{time.time_ns()}@test.com"
    resp = api.post(
        "/v1/auth/register",
        json={"email": email, "password": "TestPass123!", "display_name": "Profile User"},
    )
    assert resp.status_code == 201
    data: dict[str, Any] = resp.json()
    data["email"] = email
    data["headers"] = {"Authorization": f"Bearer {data['access_token']}"}
    return data


def _insert_token(db: Db, email: str, raw: str, *, expires_in: timedelta, used: bool) -> None:
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    db.execute(
        "INSERT INTO email_verification_tokens (user_id, token_hash, expires_at, used_at) "
        "SELECT id, $2, $3, $4 FROM users WHERE email = $1",
        email,
        token_hash,
        datetime.now(UTC) + expires_in,
        datetime.now(UTC) if used else None,
    )


def test_get_me(api: Client, auth_headers: dict[str, str], fresh_user: dict[str, Any]) -> None:
    resp = api.get("/v1/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == fresh_user["email"]
    assert data["email_verified"] is True


def test_get_me_requires_auth(api: Client) -> None:
    assert api.get("/v1/auth/me").status_code == 401


def test_invalid_token_rejected(api: Client) -> None:
    resp = api.get("/v1/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "INVALID_TOKEN"


def test_refresh_token_is_not_an_access_token(api: Client, fresh_user: dict[str, Any]) -> None:
    resp = api.get(
        "/v1/auth/me", headers={"Authorization": f"Bearer {fresh_user['refresh_token']}"}
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "INVALID_TOKEN_TYPE"


def test_access_token_is_not_a_refresh_token(api: Client, fresh_user: dict[str, Any]) -> None:
    resp = api.post("/v1/auth/refresh", json={"refresh_token": fresh_user["access_token"]})
    assert resp.status_code == 401


def test_refresh_with_garbage_token(api: Client) -> None:
    resp = api.post("/v1/auth/refresh", json={"refresh_token": "garbage"})
    assert resp.status_code == 401


def test_logout_with_garbage_token_is_noop(api: Client) -> None:
    assert api.post("/v1/auth/logout", json={"refresh_token": "garbage"}).status_code == 204


def test_update_profile(api: Client, auth_headers: dict[str, str]) -> None:
    resp = api.patch(
        "/v1/auth/me",
        json={"display_name": "Renamed", "bio": "Loves noir", "avatar_url": "https://x.io/a.png"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["display_name"] == "Renamed"
    assert data["bio"] == "Loves noir"
    assert data["avatar_url"] == "https://x.io/a.png"

    # Empty string clears optional fields.
    resp = api.patch("/v1/auth/me", json={"bio": "", "avatar_url": ""}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["bio"] is None
    assert resp.json()["avatar_url"] is None


def test_update_profile_requires_a_field(api: Client, auth_headers: dict[str, str]) -> None:
    resp = api.patch("/v1/auth/me", json={}, headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "NO_FIELDS"


def test_change_password(api: Client) -> None:
    user = _register(api, "chpw")
    resp = api.post(
        "/v1/auth/change-password",
        json={"current_password": "TestPass123!", "new_password": "BrandNew456!"},
        headers=user["headers"],
    )
    assert resp.status_code == 204

    old = api.post("/v1/auth/login", json={"email": user["email"], "password": "TestPass123!"})
    assert old.status_code == 401
    new = api.post("/v1/auth/login", json={"email": user["email"], "password": "BrandNew456!"})
    assert new.status_code == 200


def test_change_password_wrong_current(api: Client, auth_headers: dict[str, str]) -> None:
    resp = api.post(
        "/v1/auth/change-password",
        json={"current_password": "WrongPass1!", "new_password": "BrandNew456!"},
        headers=auth_headers,
    )
    assert resp.status_code == 401


def test_change_password_weak_new_password(api: Client, auth_headers: dict[str, str]) -> None:
    resp = api.post(
        "/v1/auth/change-password",
        json={"current_password": "TestPass123!", "new_password": "alllowercase1"},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_delete_account(api: Client) -> None:
    user = _register(api, "del")
    wrong = api.request(
        "DELETE", "/v1/auth/me", json={"password": "Nope12345"}, headers=user["headers"]
    )
    assert wrong.status_code == 401

    resp = api.request(
        "DELETE", "/v1/auth/me", json={"password": "TestPass123!"}, headers=user["headers"]
    )
    assert resp.status_code == 204
    assert api.get("/v1/auth/me", headers=user["headers"]).status_code == 401
    login = api.post("/v1/auth/login", json={"email": user["email"], "password": "TestPass123!"})
    assert login.status_code == 401


def test_stats_empty(api: Client, auth_headers: dict[str, str]) -> None:
    resp = api.get("/v1/auth/me/stats", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_ratings"] == 0
    assert data["avg_rating"] is None
    assert data["top_genres"] == []
    assert data["score_distribution"] == {}


def test_stats_with_ratings(
    api: Client, db: Db, auth_headers: dict[str, str], seed_movies: list[int]
) -> None:
    db.execute(
        "INSERT INTO movie_genres (movie_id, genre_id) "
        "SELECT $1, id FROM genres WHERE slug = 'drama' ON CONFLICT DO NOTHING",
        seed_movies[0],
    )
    for mid, score in ((seed_movies[0], 4.0), (seed_movies[1], 5.0)):
        resp = api.post("/v1/ratings", json={"movie_id": mid, "score": score}, headers=auth_headers)
        assert resp.status_code == 201

    data = api.get("/v1/auth/me/stats", headers=auth_headers).json()
    assert data["total_ratings"] == 2
    assert data["avg_rating"] == 4.5
    assert data["first_rated_at"] is not None
    assert data["last_rated_at"] is not None
    assert {g["slug"] for g in data["top_genres"]} == {"drama"}
    assert sum(data["score_distribution"].values()) == 2


def test_verify_email_flow(api: Client, db: Db) -> None:
    user = _register(api, "verify")
    raw = f"raw-token-{time.time_ns()}"
    _insert_token(db, user["email"], raw, expires_in=timedelta(hours=1), used=False)

    me = api.get("/v1/auth/me", headers=user["headers"]).json()
    assert me["email_verified"] is False

    resp = api.post("/v1/auth/verify-email", json={"token": raw})
    assert resp.status_code == 200
    assert resp.json() == {"email": user["email"], "already_verified": False}
    assert api.get("/v1/auth/me", headers=user["headers"]).json()["email_verified"] is True

    # Clicking the same link again is idempotent.
    again = api.post("/v1/auth/verify-email", json={"token": raw})
    assert again.status_code == 200
    assert again.json()["already_verified"] is True


def test_verify_email_unknown_token(api: Client) -> None:
    resp = api.post("/v1/auth/verify-email", json={"token": "x" * 40})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "TOKEN_INVALID"


def test_verify_email_used_token(api: Client, db: Db) -> None:
    user = _register(api, "used")
    raw = f"used-token-{time.time_ns()}"
    _insert_token(db, user["email"], raw, expires_in=timedelta(hours=1), used=True)
    resp = api.post("/v1/auth/verify-email", json={"token": raw})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "TOKEN_USED"


def test_verify_email_expired_token(api: Client, db: Db) -> None:
    user = _register(api, "expired")
    raw = f"expired-token-{time.time_ns()}"
    _insert_token(db, user["email"], raw, expires_in=timedelta(hours=-1), used=False)
    resp = api.post("/v1/auth/verify-email", json={"token": raw})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "TOKEN_EXPIRED"


def test_resend_verification(api: Client, db: Db) -> None:
    user = _register(api, "resend")
    resp = api.post("/v1/auth/resend-verification", json={"email": user["email"]})
    assert resp.status_code == 204
    rows = db.fetch(
        "SELECT t.id FROM email_verification_tokens t JOIN users u ON u.id = t.user_id "
        "WHERE u.email = $1 AND t.used_at IS NULL",
        user["email"],
    )
    # Registration issues one token; resend invalidates it and issues a fresh one.
    assert len(rows) == 1


def test_resend_verification_unknown_email_does_not_leak(api: Client) -> None:
    resp = api.post("/v1/auth/resend-verification", json={"email": "ghost@example.org"})
    assert resp.status_code == 204


def test_resend_verification_is_rate_limited(api: Client) -> None:
    email = f"limited_{time.time_ns()}@test.com"
    codes = [
        api.post("/v1/auth/resend-verification", json={"email": email}).status_code
        for _ in range(4)
    ]
    assert codes == [204, 204, 204, 429]
