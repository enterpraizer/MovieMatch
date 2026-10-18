import asyncio
import os
import signal
import subprocess
import time
import urllib.request
from collections.abc import Iterator
from typing import Any

import asyncpg
import pytest
import redis
from httpx import Client

TEST_DB = "moviematch_test"
TEST_PORT = 8099
BASE_URL = f"http://localhost:{TEST_PORT}"

os.environ.update(
    {
        "POSTGRES_URL": f"postgresql+asyncpg://moviematch:changeme@localhost:5432/{TEST_DB}",
        "REDIS_URL": "redis://localhost:6379/2",
        "SECRET_KEY": "test-secret-key-minimum-32-characters-long",
        "TMDB_API_KEY": "test_key_not_used",
        "ML_RECSYS_URL": "http://mock-recsys:9999",
        "ML_NLP_URL": "http://mock-nlp:9999",
        "ML_CV_URL": "http://mock-cv:9999",
        "LOG_LEVEL": "WARNING",
    }
)


@pytest.fixture(scope="session", autouse=True)
def test_server() -> Iterator[subprocess.Popen[bytes]]:
    loop = asyncio.new_event_loop()

    async def _create_db() -> None:
        conn = await asyncpg.connect("postgresql://moviematch:changeme@localhost:5432/moviematch")
        try:
            await conn.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = $1",
                TEST_DB,
            )
            await conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
            await conn.execute(f"CREATE DATABASE {TEST_DB}")
        finally:
            await conn.close()

        conn = await asyncpg.connect(f"postgresql://moviematch:changeme@localhost:5432/{TEST_DB}")
        try:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            await conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
            await conn.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
        finally:
            await conn.close()

    loop.run_until_complete(_create_db())

    # Cached API responses are keyed by ids from the (freshly recreated) test database,
    # so drop anything left over from a previous run.
    cache = redis.Redis.from_url(os.environ["REDIS_URL"])
    cache.flushdb()
    cache.close()

    env = os.environ.copy()
    result = subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, f"Alembic failed:\n{result.stderr}"

    proc = subprocess.Popen(
        [
            "uv",
            "run",
            "uvicorn",
            "main:app",
            "--port",
            str(TEST_PORT),
            "--log-level",
            "warning",
        ],
        env=env,
    )

    for _ in range(30):
        try:
            urllib.request.urlopen(f"{BASE_URL}/health", timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    else:
        proc.kill()
        raise RuntimeError("Test server failed to start")

    yield proc

    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()

    async def _drop() -> None:
        try:
            conn = await asyncpg.connect(
                "postgresql://moviematch:changeme@localhost:5432/moviematch"
            )
            await conn.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = $1",
                TEST_DB,
            )
            await conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
            await conn.close()
        except Exception:
            pass

    loop.run_until_complete(_drop())
    loop.close()


@pytest.fixture(scope="session")
def api(test_server: subprocess.Popen[bytes]) -> Iterator[Client]:
    with Client(base_url=BASE_URL, timeout=10.0) as client:
        yield client


@pytest.fixture(autouse=True)
def flush_rate_limits() -> None:
    r = redis.Redis.from_url(os.environ["REDIS_URL"])
    for key in r.scan_iter("rl:*"):
        r.delete(key)
    r.close()


class Db:
    """Tiny synchronous helper for arranging/inspecting rows in the test database."""

    @staticmethod
    def _run(sql: str, args: tuple[Any, ...], fetch: bool) -> list[dict[str, Any]]:
        async def _go() -> list[dict[str, Any]]:
            conn = await asyncpg.connect(
                f"postgresql://moviematch:changeme@localhost:5432/{TEST_DB}"
            )
            try:
                if fetch:
                    return [dict(r) for r in await conn.fetch(sql, *args)]
                await conn.execute(sql, *args)
                return []
            finally:
                await conn.close()

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_go())
        finally:
            loop.close()

    def execute(self, sql: str, *args: Any) -> None:
        self._run(sql, args, fetch=False)

    def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        return self._run(sql, args, fetch=True)


@pytest.fixture(scope="session")
def db(test_server: subprocess.Popen[bytes]) -> Db:
    return Db()


def _mark_email_verified(email: str) -> None:
    """Mutating endpoints (ratings, watchlist) require a verified email.

    The verification token is only delivered by e-mail (stored hashed), so
    tests flip the flag directly in the database.
    """
    Db().execute("UPDATE users SET email_verified = TRUE WHERE email = $1", email)


@pytest.fixture()
def fresh_user(api: Client) -> dict[str, Any]:
    ts = int(time.time() * 1000)
    email = f"user_{ts}@test.com"
    resp = api.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": "TestPass123!",
            "display_name": "Test User",
        },
    )
    assert resp.status_code == 201, f"Register failed: {resp.text}"
    data: dict[str, Any] = resp.json()
    data["email"] = email
    _mark_email_verified(email)
    return data


@pytest.fixture()
def auth_headers(fresh_user: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {fresh_user['access_token']}"}


@pytest.fixture()
def seed_movies(test_server: subprocess.Popen[bytes]) -> list[int]:
    loop = asyncio.new_event_loop()

    async def _seed() -> list[int]:
        conn = await asyncpg.connect(f"postgresql://moviematch:changeme@localhost:5432/{TEST_DB}")
        try:
            for name, slug in [("Comedy", "comedy"), ("Drama", "drama"), ("Action", "action")]:
                await conn.execute(
                    "INSERT INTO genres (name, slug) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                    name,
                    slug,
                )
            ids: list[int] = []
            ts = int(time.time() * 1000)
            for i in range(1, 11):
                mid = await conn.fetchval(
                    """INSERT INTO movies (title, year, avg_rating, rating_count,
                                          popularity_score, description)
                       VALUES ($1, $2, $3, $4, $5, $6) RETURNING id""",
                    f"Test Movie {ts}_{i}",
                    2000 + i,
                    round(3.0 + (i % 20) * 0.1, 1),
                    50 * i,
                    float(i) / 10.0,
                    f"A test movie about topic {i}",
                )
                ids.append(mid)
            return ids
        finally:
            await conn.close()

    ids = loop.run_until_complete(_seed())
    loop.close()
    return ids
