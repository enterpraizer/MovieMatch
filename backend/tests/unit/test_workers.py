from typing import Any

import asyncpg
import pytest

from workers.tasks import analytics, recommendations


class FakeConn:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = rows or []
        self.executed: list[tuple[str, tuple[Any, ...]]] = []
        self.closed = False

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        return self.rows

    async def execute(self, query: str, *args: Any) -> str:
        self.executed.append((query, args))
        return "OK"

    async def close(self) -> None:
        self.closed = True


def _patch_connect(monkeypatch: pytest.MonkeyPatch, module: Any, conn: FakeConn) -> None:
    async def connect(dsn: str) -> FakeConn:
        assert dsn.startswith("postgresql://")
        return conn

    monkeypatch.setattr(asyncpg, "connect", connect)


def test_parse_vector() -> None:
    assert recommendations._parse_vector(None, 3).tolist() == [0.0, 0.0, 0.0]
    assert recommendations._parse_vector("[1, 2.5,3]", 3).tolist() == [1.0, 2.5, 3.0]
    assert recommendations._parse_vector([4, 5], 2).tolist() == [4.0, 5.0]


@pytest.mark.parametrize(
    "task",
    [analytics.update_popularity_scores, analytics.recompute_movie_ratings],
)
def test_analytics_tasks_run_sql(monkeypatch: pytest.MonkeyPatch, task: Any) -> None:
    conn = FakeConn()
    _patch_connect(monkeypatch, analytics, conn)
    task()
    assert len(conn.executed) == 1
    assert conn.closed


def test_refresh_user_embedding_writes_normalised_mean(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        {"embedding": [1.0, 0.0], "score": 5.0},
        {"embedding": "[0.0, 1.0]", "score": 5.0},
    ]
    conn = FakeConn(rows)
    _patch_connect(monkeypatch, recommendations, conn)
    recommendations.refresh_user_embedding.run("user-1")
    (query, args) = conn.executed[0]
    assert "INSERT INTO user_embeddings" in query
    assert args[0] == "user-1"
    assert args[1] == "[0.707107,0.707107]"
    assert conn.closed


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [{"embedding": [0.0, 0.0], "score": 4.0}],
        [{"embedding": [1.0, 0.0], "score": 0.0}],
    ],
)
def test_refresh_user_embedding_skips_without_signal(
    monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, Any]]
) -> None:
    conn = FakeConn(rows)
    _patch_connect(monkeypatch, recommendations, conn)
    recommendations.refresh_user_embedding.run("user-1")
    assert conn.executed == []
    assert conn.closed


def test_refresh_user_embedding_retries_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def connect(dsn: str) -> FakeConn:
        raise OSError("db down")

    monkeypatch.setattr(asyncpg, "connect", connect)
    retried: list[Exception] = []

    class RetryRequestedError(Exception):
        pass

    def fake_retry(exc: Exception) -> RetryRequestedError:
        retried.append(exc)
        return RetryRequestedError()

    monkeypatch.setattr(recommendations.refresh_user_embedding, "retry", fake_retry, raising=False)
    with pytest.raises(RetryRequestedError):
        recommendations.refresh_user_embedding.run("user-1")
    assert isinstance(retried[0], OSError)


def test_refresh_all_movie_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx
    import respx

    monkeypatch.setenv("ML_NLP_URL", "http://mock-nlp:9999")
    with respx.mock:
        route = respx.post("http://mock-nlp:9999/reindex").respond(json={"queued": 3})
        recommendations.refresh_all_movie_embeddings.run()
        assert route.called

    with respx.mock:
        respx.post("http://mock-nlp:9999/reindex").mock(side_effect=httpx.ConnectError("down"))

        class RetryRequestedError(Exception):
            pass

        def fake_retry(exc: Exception) -> RetryRequestedError:
            return RetryRequestedError()

        monkeypatch.setattr(
            recommendations.refresh_all_movie_embeddings, "retry", fake_retry, raising=False
        )
        with pytest.raises(RetryRequestedError):
            recommendations.refresh_all_movie_embeddings.run()
