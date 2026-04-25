from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

import asyncpg
import structlog

_pool: asyncpg.Pool | None = None


async def init_db_pool() -> None:
    global _pool
    from config import get_settings

    settings = get_settings()
    dsn = settings.postgres_url.replace("postgresql+asyncpg://", "postgresql://")

    _pool = await asyncpg.create_pool(
        dsn=dsn,
        min_size=5,
        max_size=20,
        command_timeout=30,
        max_inactive_connection_lifetime=300,
        statement_cache_size=100,
    )

    async with _pool.acquire() as conn:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        await conn.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    structlog.get_logger().info("db_pool_initialized", min_size=5, max_size=20)


async def close_db_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        structlog.get_logger().info("db_pool_closed")


@asynccontextmanager
async def get_connection() -> AsyncGenerator[asyncpg.Connection, None]:
    if _pool is None:
        raise RuntimeError("Database pool not initialized. Call init_db_pool() first.")
    async with _pool.acquire() as conn:
        yield conn


async def execute_query(query: str, *args: Any) -> list[dict[str, Any]]:
    """Execute SELECT and return all rows as list of dicts."""
    async with get_connection() as conn:
        rows = await conn.fetch(query, *args)
        return [dict(row) for row in rows]


async def execute_one(query: str, *args: Any) -> dict[str, Any] | None:
    """Execute SELECT and return first row as dict or None."""
    async with get_connection() as conn:
        row = await conn.fetchrow(query, *args)
        return dict(row) if row else None


async def execute_write(query: str, *args: Any) -> str:
    """Execute INSERT/UPDATE/DELETE and return PostgreSQL status string."""
    async with get_connection() as conn:
        return str(await conn.execute(query, *args))


async def execute_val(query: str, *args: Any) -> Any:
    """Execute query and return single scalar value."""
    async with get_connection() as conn:
        return await conn.fetchval(query, *args)
