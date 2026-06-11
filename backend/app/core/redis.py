import json
import logging
from typing import Optional, Any
import redis.asyncio as aioredis
from app.core.config import get_settings

logger = logging.getLogger(__name__)

_redis_client: Optional[aioredis.Redis] = None


async def get_redis() -> Optional[aioredis.Redis]:
    global _redis_client
    if _redis_client is None:
        try:
            settings = get_settings()
            if not settings.REDIS_URL:
                return None
            _redis_client = aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
            )
            await _redis_client.ping()
        except Exception as e:
            logger.warning(f"Redis unavailable: {e}")
            _redis_client = None
    return _redis_client


async def cache_get(key: str) -> Optional[Any]:
    try:
        redis = await get_redis()
        if redis is None:
            return None
        value = await redis.get(key)
        if value is None:
            return None
        return json.loads(value)
    except Exception as e:
        logger.warning(f"Cache get failed for {key}: {e}")
        return None


async def cache_set(key: str, data: Any, ttl: int = 3600) -> bool:
    try:
        redis = await get_redis()
        if redis is None:
            return False
        await redis.setex(key, ttl, json.dumps(data))
        return True
    except Exception as e:
        logger.warning(f"Cache set failed for {key}: {e}")
        return False


async def cache_delete_pattern(pattern: str) -> int:
    try:
        redis = await get_redis()
        if redis is None:
            return 0
        keys = await redis.keys(pattern)
        print("PATTERN:", pattern)
        print("MATCHED KEYS:", keys)
        if keys:
            deleted = await redis.delete(*keys)
            print("DELETED:", deleted)
            return deleted
        return 0
    except Exception as e:
        logger.warning(f"Cache delete failed for {pattern}: {e}")
        return 0