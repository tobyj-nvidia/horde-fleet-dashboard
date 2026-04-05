import asyncio
import aiomysql
from dashboard.config import settings

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


async def get_db():
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn
