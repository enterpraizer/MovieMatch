import time
from typing import Any

from httpx import Client


def test_watchlist_roundtrip(
    api: Client, auth_headers: dict[str, str], seed_movies: list[int]
) -> None:
    mid = seed_movies[0]
    assert api.get("/v1/watchlist", headers=auth_headers).json() == []

    resp = api.post(f"/v1/watchlist/{mid}", headers=auth_headers)
    assert resp.status_code == 201
    assert resp.json() == {"movie_id": mid, "in_watchlist": True}
    # Adding twice is idempotent.
    assert api.post(f"/v1/watchlist/{mid}", headers=auth_headers).status_code == 201

    items = api.get("/v1/watchlist", headers=auth_headers).json()
    assert [m["id"] for m in items] == [mid]
    assert api.get("/v1/watchlist/ids", headers=auth_headers).json() == [mid]

    assert api.delete(f"/v1/watchlist/{mid}", headers=auth_headers).status_code == 204
    assert api.get("/v1/watchlist/ids", headers=auth_headers).json() == []


def test_watchlist_unknown_movie(api: Client, auth_headers: dict[str, str]) -> None:
    resp = api.post("/v1/watchlist/999999", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "MOVIE_NOT_FOUND"


def test_watchlist_requires_auth(api: Client) -> None:
    assert api.get("/v1/watchlist").status_code == 401


def test_watchlist_mutation_requires_verified_email(api: Client, seed_movies: list[int]) -> None:
    email = f"wl_unverified_{time.time_ns()}@test.com"
    reg = api.post(
        "/v1/auth/register",
        json={"email": email, "password": "TestPass123!", "display_name": "Unverified"},
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    resp = api.post(f"/v1/watchlist/{seed_movies[0]}", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "EMAIL_NOT_VERIFIED"


def test_delete_all_ratings(
    api: Client, auth_headers: dict[str, str], seed_movies: list[int]
) -> None:
    for mid in seed_movies[:3]:
        api.post("/v1/ratings", json={"movie_id": mid, "score": 4.0}, headers=auth_headers)
    assert len(api.get("/v1/ratings/me", headers=auth_headers).json()["items"]) == 3

    assert api.delete("/v1/ratings/me", headers=auth_headers).status_code == 204
    assert api.get("/v1/ratings/me", headers=auth_headers).json()["items"] == []
    # Nothing left to delete: still a clean 204.
    assert api.delete("/v1/ratings/me", headers=auth_headers).status_code == 204


def test_ratings_pagination(
    api: Client, auth_headers: dict[str, str], seed_movies: list[int]
) -> None:
    for mid in seed_movies[:4]:
        api.post("/v1/ratings", json={"movie_id": mid, "score": 3.5}, headers=auth_headers)

    first: dict[str, Any] = api.get("/v1/ratings/me?limit=2", headers=auth_headers).json()
    assert len(first["items"]) == 2
    assert first["next_cursor"] is not None

    second: dict[str, Any] = api.get(
        f"/v1/ratings/me?limit=2&cursor={first['next_cursor']}", headers=auth_headers
    ).json()
    assert len(second["items"]) >= 1
    seen = {i["movie_id"] for i in first["items"]}
    assert seen.isdisjoint({i["movie_id"] for i in second["items"]})
