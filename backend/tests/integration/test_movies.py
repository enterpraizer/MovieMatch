import pytest
from httpx import Client

from tests.conftest import Db


def test_list_movies(api: Client) -> None:
    resp = api.get("/v1/movies?limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert isinstance(data["items"], list)


def test_list_movies_with_data(api: Client, seed_movies: list[int]) -> None:
    resp = api.get("/v1/movies?limit=5")
    assert resp.status_code == 200
    assert len(resp.json()["items"]) <= 5


def test_get_movie_not_found(api: Client) -> None:
    resp = api.get("/v1/movies/999999")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "MOVIE_NOT_FOUND"


def test_get_movie_found(api: Client, seed_movies: list[int]) -> None:
    mid = seed_movies[0]
    resp = api.get(f"/v1/movies/{mid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == mid
    assert "title" in data
    assert "genres" in data


def test_trending_returns_list(api: Client) -> None:
    resp = api.get("/v1/movies/trending")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_health_endpoint(api: Client) -> None:
    resp = api.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_ready_endpoint(api: Client) -> None:
    resp = api.get("/ready")
    data = resp.json()
    assert data["checks"]["database"] == "ok"
    assert data["checks"]["redis"] == "ok"


def _link_genre(db: Db, movie_id: int, slug: str) -> None:
    db.execute(
        "INSERT INTO movie_genres (movie_id, genre_id) "
        "SELECT $1, id FROM genres WHERE slug = $2 ON CONFLICT DO NOTHING",
        movie_id,
        slug,
    )


@pytest.mark.parametrize("order_by", ["popularity", "rating", "year"])
def test_list_movies_ordering(api: Client, seed_movies: list[int], order_by: str) -> None:
    resp = api.get(f"/v1/movies?limit=10&order_by={order_by}")
    assert resp.status_code == 200
    assert len(resp.json()["items"]) >= 1


def test_list_movies_filters(api: Client, db: Db, seed_movies: list[int]) -> None:
    mid = seed_movies[5]  # year 2006
    _link_genre(db, mid, "action")
    resp = api.get("/v1/movies?year_from=2006&year_to=2006&min_rating=0.5&genres=action&limit=50")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert mid in [m["id"] for m in items]
    assert all(m["year"] == 2006 for m in items)
    assert all("Action" in m["genres"] for m in items)


def test_list_movies_cursor_pagination(api: Client, seed_movies: list[int]) -> None:
    first = api.get("/v1/movies?limit=3&order_by=popularity").json()
    assert len(first["items"]) == 3
    assert first["next_cursor"] is not None
    nxt = api.get(f"/v1/movies?limit=3&cursor={first['next_cursor']}")
    assert nxt.status_code == 200


def test_list_movies_rejects_bad_params(api: Client) -> None:
    assert api.get("/v1/movies?limit=0").status_code == 422
    assert api.get("/v1/movies?order_by=nonsense").status_code == 422
    assert api.get("/v1/movies?min_rating=9").status_code == 422


def test_search_movies(api: Client, seed_movies: list[int]) -> None:
    resp = api.get("/v1/movies/search?q=Test Movie")
    assert resp.status_code == 200
    assert 1 <= len(resp.json()) <= 10
    assert api.get("/v1/movies/search?q=zzzzqqqq-no-such-title").json() == []
    assert api.get("/v1/movies/search").status_code == 422


def test_movie_detail_is_cached(api: Client, seed_movies: list[int]) -> None:
    mid = seed_movies[1]
    first = api.get(f"/v1/movies/{mid}").json()
    second = api.get(f"/v1/movies/{mid}").json()  # served from Redis
    assert first == second
    assert first["credits"] == []


def test_movie_detail_includes_credits(api: Client, db: Db, seed_movies: list[int]) -> None:
    mid = seed_movies[6]
    person_id = db.fetch("INSERT INTO people (name) VALUES ('Test Actor') RETURNING id")[0]["id"]
    db.execute(
        "INSERT INTO movie_credits (movie_id, person_id, role, character_name, order_index) "
        "VALUES ($1, $2, 'actor', 'Hero', 0)",
        mid,
        person_id,
    )
    data = api.get(f"/v1/movies/{mid}").json()
    assert data["credits"][0]["person"]["name"] == "Test Actor"
    assert data["credits"][0]["character_name"] == "Hero"


def test_trending_is_cached(api: Client, seed_movies: list[int]) -> None:
    assert api.get("/v1/movies/trending").status_code == 200
    assert api.get("/v1/movies/trending").status_code == 200


def test_onboarding_movies(api: Client, seed_movies: list[int]) -> None:
    resp = api.get("/v1/movies/onboarding?limit=10")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert api.get("/v1/movies/onboarding?limit=10").status_code == 200  # cache hit


def test_similar_movies_without_embedding_uses_genres(
    api: Client, db: Db, seed_movies: list[int]
) -> None:
    a, b = seed_movies[7], seed_movies[8]
    _link_genre(db, a, "comedy")
    _link_genre(db, b, "comedy")
    resp = api.get(f"/v1/movies/{a}/similar?limit=5")
    assert resp.status_code == 200
    assert b in [m["id"] for m in resp.json()]


def test_similar_movies_with_embedding(api: Client, db: Db, seed_movies: list[int]) -> None:
    a, b = seed_movies[2], seed_movies[3]
    for mid, hot in ((a, 0), (b, 1)):
        vec = "[" + ",".join("1" if i == hot else "0" for i in range(768)) + "]"
        db.execute("UPDATE movies SET embedding = $2::vector WHERE id = $1", mid, vec)
    resp = api.get(f"/v1/movies/{a}/similar?limit=5")
    assert resp.status_code == 200
    assert b in [m["id"] for m in resp.json()]


def test_similar_movies_not_found(api: Client) -> None:
    resp = api.get("/v1/movies/999999/similar")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "MOVIE_NOT_FOUND"


def test_ready_reports_degraded_ml_services(api: Client) -> None:
    resp = api.get("/ready")
    assert resp.json()["checks"]["recsys"] == "degraded"


def test_metrics_endpoint(api: Client) -> None:
    resp = api.get("/metrics")
    assert resp.status_code == 200
    assert "http_requests_total" in resp.text or "python_info" in resp.text
