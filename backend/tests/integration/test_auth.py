import time

from httpx import Client


def test_register_success(api: Client) -> None:
    email = f"reg_{int(time.time()*1000)}@test.com"
    resp = api.post(
        "/v1/auth/register",
        json={"email": email, "password": "NewPass123!", "display_name": "New"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0


def test_register_duplicate_email(api: Client) -> None:
    email = f"dup_{int(time.time()*1000)}@test.com"
    payload = {"email": email, "password": "Pass1234!", "display_name": "Dup"}
    r1 = api.post("/v1/auth/register", json=payload)
    assert r1.status_code == 201

    r2 = api.post("/v1/auth/register", json=payload)
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "EMAIL_TAKEN"


def test_register_weak_password(api: Client) -> None:
    resp = api.post(
        "/v1/auth/register",
        json={"email": "weak@test.com", "password": "short", "display_name": "W"},
    )
    assert resp.status_code == 422


def test_login_success(api: Client, fresh_user: dict) -> None:
    resp = api.post(
        "/v1/auth/login",
        json={"email": fresh_user["email"], "password": "TestPass123!"},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_login_wrong_password(api: Client, fresh_user: dict) -> None:
    resp = api.post(
        "/v1/auth/login",
        json={"email": fresh_user["email"], "password": "WrongPassword1!"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_login_nonexistent_user(api: Client) -> None:
    resp = api.post(
        "/v1/auth/login",
        json={"email": "nouser@nowhere.com", "password": "Whatever1!"},
    )
    assert resp.status_code == 401


def test_refresh_token_rotation(api: Client, fresh_user: dict) -> None:
    old_refresh = fresh_user["refresh_token"]
    resp = api.post("/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert resp.status_code == 200
    new_tokens = resp.json()
    assert new_tokens["access_token"] != fresh_user["access_token"]

    resp2 = api.post("/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert resp2.status_code == 401


def test_logout_blacklists_refresh(api: Client, fresh_user: dict) -> None:
    refresh = fresh_user["refresh_token"]
    resp = api.post("/v1/auth/logout", json={"refresh_token": refresh})
    assert resp.status_code == 204

    resp2 = api.post("/v1/auth/refresh", json={"refresh_token": refresh})
    assert resp2.status_code == 401


def test_protected_endpoint_without_token(api: Client) -> None:
    resp = api.get("/v1/ratings/me")
    assert resp.status_code == 401
