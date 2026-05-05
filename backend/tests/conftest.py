import asyncio
import os
import signal
import subprocess
import time

import asyncpg
import pytest
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
def test_server():
    loop = asyncio.new_event_loop()

    async def _create_db():
        conn = await asyncpg.connect(
            "postgresql://moviematch:changeme@localhost:5432/moviematch"
        )
        try:
            await conn.execute(
                f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname='{TEST_DB}'"
            )
            await conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
            await conn.execute(f"CREATE DATABASE {TEST_DB}")
        finally:
            await conn.close()

        conn = await asyncpg.connect(
            f"postgresql://moviematch:changeme@localhost:5432/{TEST_DB}"
        )
        try:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            await conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
            await conn.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
        finally:
            await conn.close()

    loop.run_until_complete(_create_db())

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
            "uv", "run", "uvicorn", "main:app",
            "--port", str(TEST_PORT),
            "--log-level", "warning",
        ],
        env=env,
    )

    import urllib.request

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

    async def _drop():
        try:
            conn = await asyncpg.connect(
                "postgresql://moviematch:changeme@localhost:5432/moviematch"
            )
            await conn.execute(
                f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname='{TEST_DB}'"
            )
            await conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
            await conn.close()
        except Exception:
            pass

    loop.run_until_complete(_drop())
    loop.close()


@pytest.fixture(scope="session")
def api(test_server) -> Client:
    with Client(base_url=BASE_URL, timeout=10.0) as client:
        yield client


@pytest.fixture(autouse=True)
def flush_rate_limits():
    import redis

    r = redis.from_url(os.environ["REDIS_URL"])
    for key in r.scan_iter("rl:*"):
        r.delete(key)
    r.close()


@pytest.fixture()
def fresh_user(api: Client) -> dict:
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
    data = resp.json()
    data["email"] = email
    return data


@pytest.fixture()
def auth_headers(fresh_user: dict) -> dict:
    return {"Authorization": f"Bearer {fresh_user['access_token']}"}


@pytest.fixture()
def seed_movies(test_server) -> list[int]:
    import asyncpg as apg

    loop = asyncio.new_event_loop()

    async def _seed():
        conn = await apg.connect(
            f"postgresql://moviematch:changeme@localhost:5432/{TEST_DB}"
        )
        try:
            for name, slug in [("Comedy", "comedy"), ("Drama", "drama"), ("Action", "action")]:
                await conn.execute(
                    "INSERT INTO genres (name, slug) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                    name, slug,
                )
            ids = []
            ts = int(time.time() * 1000)
            for i in range(1, 11):
                mid = await conn.fetchval(
                    """INSERT INTO movies (title, year, avg_rating, rating_count,
                                          popularity_score, description)
                       VALUES ($1, $2, $3, $4, $5, $6) RETURNING id""",
                    f"Test Movie {ts}_{i}", 2000 + i,
                    round(3.0 + (i % 20) * 0.1, 1), 50 * i,
                    float(i) / 10.0, f"A test movie about topic {i}",
                )
                ids.append(mid)
            return ids
        finally:
            await conn.close()

    ids = loop.run_until_complete(_seed())
    loop.close()
    return ids
