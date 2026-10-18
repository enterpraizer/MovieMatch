import io
from typing import Any

from httpx import Client

PNG_HEADER = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def test_collaborative_cold_start_uses_popularity(
    api: Client, auth_headers: dict[str, str], seed_movies: list[int]
) -> None:
    resp = api.post(
        "/v1/recommendations/collaborative", json={"ratings": [], "limit": 5}, headers=auth_headers
    )
    assert resp.status_code == 200
    data: dict[str, Any] = resp.json()
    assert data["model_version"] == "popularity"
    assert data["cached"] is False

    again = api.post(
        "/v1/recommendations/collaborative", json={"ratings": [], "limit": 5}, headers=auth_headers
    )
    assert again.json()["cached"] is True


def test_collaborative_falls_back_when_recsys_is_down(
    api: Client, auth_headers: dict[str, str], seed_movies: list[int]
) -> None:
    ratings = [{"movie_id": mid, "score": 4.0} for mid in seed_movies[:4]]
    resp = api.post(
        "/v1/recommendations/collaborative",
        json={"ratings": ratings, "limit": 5},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["model_version"] == "popularity"
    assert all(i["reason"] == "Popular (ML unavailable)" for i in data["items"])


def test_collaborative_uses_stored_ratings_when_body_is_empty(
    api: Client, auth_headers: dict[str, str], seed_movies: list[int]
) -> None:
    for mid in seed_movies[:3]:
        api.post("/v1/ratings", json={"movie_id": mid, "score": 4.5}, headers=auth_headers)
    resp = api.post("/v1/recommendations/collaborative", json={}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["items"] is not None


def test_collaborative_requires_auth(api: Client) -> None:
    assert api.post("/v1/recommendations/collaborative", json={}).status_code == 401


def test_search_falls_back_when_nlp_is_down(api: Client, seed_movies: list[int]) -> None:
    resp = api.post("/v1/recommendations/search", json={"query": "space opera", "limit": 3})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) <= 3
    assert all(i["reason"] == "Popular (search unavailable)" for i in data["items"])


def test_search_validates_query(api: Client) -> None:
    assert api.post("/v1/recommendations/search", json={"query": "a"}).status_code == 422


def test_emotion_requires_auth(api: Client) -> None:
    files = {"image": ("a.png", io.BytesIO(PNG_HEADER), "image/png")}
    assert api.post("/v1/recommendations/emotion", files=files).status_code == 401


def test_emotion_rejects_non_image(api: Client, auth_headers: dict[str, str]) -> None:
    files = {"image": ("a.txt", io.BytesIO(b"definitely not an image"), "text/plain")}
    resp = api.post("/v1/recommendations/emotion", files=files, headers=auth_headers)
    assert resp.status_code in (400, 415, 422)
    assert resp.json()["error"]["code"] == "INVALID_IMAGE"


def test_emotion_reports_ml_unavailable(api: Client, auth_headers: dict[str, str]) -> None:
    files = {"image": ("a.png", io.BytesIO(PNG_HEADER), "image/png")}
    resp = api.post("/v1/recommendations/emotion", files=files, headers=auth_headers)
    assert resp.status_code in (502, 503)
    assert resp.json()["error"]["code"] == "ML_SERVICE_UNAVAILABLE"
