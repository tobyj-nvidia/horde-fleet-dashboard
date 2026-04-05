import asyncio
import logging
from typing import AsyncGenerator

import aiomysql

from dashboard.config import settings

logger = logging.getLogger(__name__)

_pool: aiomysql.Pool | None = None


async def get_pool() -> aiomysql.Pool:
    global _pool
    if _pool is None:
        _pool = await aiomysql.create_pool(
            host=settings.dolt_host,
            port=settings.dolt_port,
            db=settings.dolt_db,
            user=settings.dolt_user,
            password=settings.dolt_password,
            minsize=settings.pool_min_size,
            maxsize=settings.pool_max_size,
            autocommit=True,
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        await _pool.wait_closed()
        _pool = None


async def get_db() -> AsyncGenerator[aiomysql.Connection, None]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn


async def ping_db() -> bool:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await asyncio.wait_for(cur.execute("SELECT 1"), timeout=settings.query_timeout_sec)
        return True
    except Exception as exc:
        logger.warning("DB ping failed: %s", exc)
        return False
