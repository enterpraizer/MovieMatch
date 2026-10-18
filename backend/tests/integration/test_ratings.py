import time

from httpx import Client


def test_rate_movie(api: Client, auth_headers: dict[str, str], seed_movies: list[int]) -> None:
    mid = seed_movies[0]
    resp = api.post(
        "/v1/ratings",
        json={"movie_id": mid, "score": 4.5},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["movie_id"] == mid
    assert data["score"] == 4.5


def test_rate_nonexistent_movie(api: Client, auth_headers: dict[str, str]) -> None:
    resp = api.post(
        "/v1/ratings",
        json={"movie_id": 999999, "score": 3.0},
        headers=auth_headers,
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "MOVIE_NOT_FOUND"


def test_rate_requires_auth(api: Client, seed_movies: list[int]) -> None:
    resp = api.post(
        "/v1/ratings",
        json={"movie_id": seed_movies[0], "score": 3.0},
    )
    assert resp.status_code == 401


def test_upsert_rating(api: Client, auth_headers: dict[str, str], seed_movies: list[int]) -> None:
    mid = seed_movies[1]
    api.post("/v1/ratings", json={"movie_id": mid, "score": 3.0}, headers=auth_headers)
    resp = api.post(
        "/v1/ratings",
        json={"movie_id": mid, "score": 5.0},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["score"] == 5.0


def test_list_my_ratings(api: Client, auth_headers: dict[str, str], seed_movies: list[int]) -> None:
    mid = seed_movies[2]
    api.post("/v1/ratings", json={"movie_id": mid, "score": 4.0}, headers=auth_headers)
    resp = api.get("/v1/ratings/me", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert any(r["movie_id"] == mid for r in data["items"])


def test_delete_rating(api: Client, auth_headers: dict[str, str], seed_movies: list[int]) -> None:
    mid = seed_movies[3]
    api.post("/v1/ratings", json={"movie_id": mid, "score": 2.5}, headers=auth_headers)
    resp = api.delete(f"/v1/ratings/{mid}", headers=auth_headers)
    assert resp.status_code == 204


def test_delete_nonexistent_rating(api: Client, auth_headers: dict[str, str]) -> None:
    resp = api.delete("/v1/ratings/999999", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "RATING_NOT_FOUND"


def test_rate_requires_verified_email(api: Client, seed_movies: list[int]) -> None:
    email = f"unverified_{int(time.time() * 1000)}@test.com"
    resp = api.post(
        "/v1/auth/register",
        json={"email": email, "password": "TestPass123!", "display_name": "Unverified"},
    )
    assert resp.status_code == 201
    token = resp.json()["access_token"]
    resp = api.post(
        "/v1/ratings",
        json={"movie_id": seed_movies[0], "score": 3.0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "EMAIL_NOT_VERIFIED"
