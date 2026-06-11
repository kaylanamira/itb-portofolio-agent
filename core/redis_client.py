import logging
import redis.asyncio as aioredis
from core.config import settings

logger = logging.getLogger(__name__)

# Instance global
_redis_client: aioredis.Redis | None = None

async def init_redis() -> None:
    global _redis_client
    _redis_client = aioredis.from_url(
        settings.REDIS_URL,
        decode_responses=True, 
    )

    await _redis_client.ping()
    logger.info("Redis connected: %s", settings.REDIS_URL)


async def close_redis() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
        logger.info("Redis connection closed.")


def get_redis() -> aioredis.Redis:
    if _redis_client is None:
        raise RuntimeError(
            "Redis belum diinisialisasi. "
            "Pastikan init_redis() dipanggil di lifespan aplikasi."
        )
    return _redis_client