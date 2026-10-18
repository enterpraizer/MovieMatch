from typing import Any

import pytest

from exceptions import MLServiceUnavailableError
from services import cv_client, nlp_client, recsys_client
from services import recommendations as svc

ROWS = [
    {
        "id": 1,
        "title": "One",
        "year": 2000,
        "avg_rating": 4.0,
        "poster_path": "/p.jpg",
        "genres": ["Drama"],
    },
    {
        "id": 2,
        "title": "Two",
        "year": None,
        "avg_rating": None,
        "poster_path": "http://x/p.jpg",
        "genres": None,
    },
]


@pytest.fixture()
def fake_db(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, tuple[Any, ...]]]:
    calls: list[tuple[str, tuple[Any, ...]]] = []

    async def fake_query(query: str, *args: Any) -> list[dict[str, Any]]:
        calls.append((query, args))
        return [dict(r) for r in ROWS]

    monkeypatch.setattr(svc, "execute_query", fake_query)
    return calls


def test_poster_url() -> None:
    assert svc._poster_url(None) is None
    assert svc._poster_url("") is None
    assert svc._poster_url("http://a/b.jpg") == "http://a/b.jpg"
    assert svc._poster_url("/b.jpg") == f"{svc.TMDB_IMG_BASE}/b.jpg"


async def test_enrich_skips_empty_candidates(fake_db: list[Any]) -> None:
    assert await svc._enrich_recommendations([]) == []
    assert await svc._enrich_recommendations([{"score": 1}]) == []
    assert fake_db == []


async def test_popularity_fallback_with_and_without_genres(fake_db: list[Any]) -> None:
    await svc._popularity_fallback(5)
    await svc._popularity_fallback(5, genres=["Drama"])
    assert "JOIN movie_genres" in fake_db[1][0]
    assert fake_db[1][1] == (["Drama"], 5)


async def test_search_orders_by_nlp_ranking(
    monkeypatch: pytest.MonkeyPatch, fake_db: list[Any]
) -> None:
    async def fake_search(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return [{"movie_id": 2, "rrf_score": 0.9}, {"movie_id": 1, "score": 0.5}]

    monkeypatch.setattr(nlp_client, "search", fake_search)
    result = await svc.get_search_recommendations("noir", 10, None, "req-1")
    assert [i.movie_id for i in result.items] == [2, 1]
    assert [i.score for i in result.items] == [0.9, 0.5]
    assert result.items[0].reason == "Matches 'noir'"


async def test_search_falls_back_when_nlp_down(
    monkeypatch: pytest.MonkeyPatch, fake_db: list[Any]
) -> None:
    async def down(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        raise MLServiceUnavailableError("nlp")

    monkeypatch.setattr(nlp_client, "search", down)
    result = await svc.get_search_recommendations("noir", 10, None, "req-1")
    assert {i.reason for i in result.items} == {"Popular (search unavailable)"}


@pytest.mark.parametrize(
    ("detected", "expected_emotion"),
    [
        ({"emotion": "HAPPY", "confidence": 0.7}, "happy"),
        ({"emotion": "bewildered", "confidence": 0.1}, "bewildered"),
        ({}, "neutral"),
    ],
)
async def test_emotion_recommendations(
    monkeypatch: pytest.MonkeyPatch,
    fake_db: list[Any],
    detected: dict[str, Any],
    expected_emotion: str,
) -> None:
    async def fake_detect(image: bytes) -> dict[str, Any]:
        return detected

    monkeypatch.setattr(cv_client, "detect_emotion", fake_detect)
    result = await svc.get_emotion_recommendations(b"img", 10, "req-2")
    assert result.emotion == expected_emotion
    assert result.emotion_message in svc.EMOTION_VERDICT.values()
    assert len(result.items) == 2
    expected_genres = svc.EMOTION_TO_GENRES.get(expected_emotion, svc.EMOTION_TO_GENRES["neutral"])
    assert fake_db[0][1][0] == expected_genres


async def test_collaborative_personalised_path(
    monkeypatch: pytest.MonkeyPatch, fake_db: list[Any]
) -> None:
    from tests.unit.test_cache import FakeRedis

    async def fake_recs(ratings: list[dict[str, Any]], k: int) -> list[dict[str, Any]]:
        return [{"movie_id": 1, "score": 0.2}, {"movie_id": 2, "score": 0.8}]

    monkeypatch.setattr(recsys_client, "get_recommendations", fake_recs)
    redis: Any = FakeRedis()
    ratings = [{"movie_id": i, "score": 4.0} for i in range(5)]

    result = await svc.get_collaborative_recommendations("u1", ratings, 10, None, redis, "r1")
    assert [i.movie_id for i in result.items] == [2, 1]
    assert result.model_version == svc.MODEL_VERSION
    assert result.items[0].reason == "Based on your ratings"

    cached = await svc.get_collaborative_recommendations("u1", ratings, 10, None, redis, "r2")
    assert cached.cached is True
    assert cached.request_id == "r2"
