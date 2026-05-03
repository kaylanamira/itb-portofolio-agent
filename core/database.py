import psycopg
from psycopg_pool import AsyncConnectionPool
from contextlib import asynccontextmanager
from typing import AsyncGenerator
import logging
from core.config import settings

logger = logging.getLogger(__name__)

# The connection string uses standard format: postgresql://user:pass@host:port/dbname
db_url = settings.DATABASE_URL
if db_url.startswith("postgresql+psycopg://"):
    db_url = db_url.replace("postgresql+psycopg://", "postgresql://")
elif db_url.startswith("postgresql+asyncpg://"):
    db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")

pool = AsyncConnectionPool(
    conninfo=db_url,
    min_size=1,
    max_size=10,
    timeout=30.0,
    open=False, # We open it in lifespan
)

@asynccontextmanager
async def get_db_connection() -> AsyncGenerator[psycopg.AsyncConnection, None]:
    """Yields an async connection from the pool."""
    async with pool.connection() as conn:
        yield conn

async def init_db_pool():
    logger.info("Initializing Database Pool...")
    await pool.open()

async def close_db_pool():
    logger.info("Closing Database Pool...")
    await pool.close()
