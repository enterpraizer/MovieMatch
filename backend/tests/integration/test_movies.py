from httpx import Client


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
