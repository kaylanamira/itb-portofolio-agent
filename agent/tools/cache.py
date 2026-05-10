from __future__ import annotations

import hashlib
import json
import logging
from enum import Enum
from typing import Any

from core.config import settings

logger = logging.getLogger(__name__)


class CacheKind(str, Enum):
    EMBEDDING = "emb"
    RETRIEVAL = "ret"
    SQL_RESULT = "sql"
    RESPONSE = "resp"
    SESSION_MESSAGES = "session_messages"
    SESSION_ENTITIES = "session_entities"
    SESSION_SUMMARY = "session_summary"
    SESSION_CONTEXT = "session_context"


class CacheKeys:
    @staticmethod
    def embedding(text: str) -> str:
        return f"{CacheKind.EMBEDDING.value}:{_generate_cache_key(text)}"

    @staticmethod
    def retrieval_index(payload: dict, scope_fingerprint: str) -> str:
        return f"{CacheKind.RETRIEVAL.value}:index:{_generate_cache_key({'payload': payload, 'scope': scope_fingerprint})}"

    @staticmethod
    def retrieval_semantic(scope_fingerprint: str) -> str:
        return f"{CacheKind.RETRIEVAL.value}:semantic:{scope_fingerprint}"

    @staticmethod
    def sql_result(sql_text: str, params: list[Any], scope_fingerprint: str) -> str:
        return f"{CacheKind.SQL_RESULT.value}:{_generate_cache_key({'sql': sql_text, 'params': params, 'scope': scope_fingerprint})}"

    @staticmethod
    def response(query: str, scope_fingerprint: str) -> str:
        return f"{CacheKind.RESPONSE.value}:{_generate_cache_key({'query': query, 'scope': scope_fingerprint})}"

    @staticmethod
    def session_messages(session_id: str) -> str:
        return f"session:{session_id}:messages"

    @staticmethod
    def session_entities(session_id: str) -> str:
        return f"session:{session_id}:entities"

    @staticmethod
    def session_summary(session_id: str) -> str:
        return f"session:{session_id}:summary"

    @staticmethod
    def session_context(session_id: str) -> str:
        return f"session:{session_id}:context"

    @staticmethod
    def scope_fingerprint(scope: Any) -> str:
        if hasattr(scope, "model_dump"):
            payload = scope.model_dump(mode="json")
        else:
            payload = scope
        return _generate_cache_key(payload)


class CacheClient:
    def __init__(self, url: str = settings.REDIS_URL):
        self.url = url
        self._client: Any | None = None

    async def client(self) -> Any | None:
        if self._client is not None:
            return self._client
        try:
            from redis.asyncio import Redis
            self._client = Redis.from_url(self.url, decode_responses=True)
            return self._client
        except Exception as exc:
            logger.warning("Redis unavailable: %s", exc)
            return None

    async def get_json(self, key: str) -> Any | None:
        client = await self.client()
        if client is None:
            return None
        value = await client.get(key)
        return json.loads(value) if value else None

    async def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        client = await self.client()
        if client is None:
            return
        await client.set(key, json.dumps(value, default=str), ex=ttl_seconds)

    async def get_json_list(self, key: str) -> list[dict]:
        client = await self.client()
        if client is None:
            return []
        values = await client.lrange(key, 0, -1)
        return [json.loads(value) for value in reversed(values)]

    async def push_json_trimmed(
        self,
        key: str,
        value: dict,
        max_items: int,
        ttl_seconds: int,
    ) -> None:
        client = await self.client()
        if client is None:
            return
        await client.lpush(key, json.dumps(value, default=str))
        await client.ltrim(key, 0, max_items - 1)
        await client.expire(key, ttl_seconds)

    async def hset_json(self, key: str, mapping: dict[str, Any], ttl_seconds: int) -> None:
        client = await self.client()
        if client is None:
            return
        await client.hset(key, mapping={name: json.dumps(value, default=str) for name, value in mapping.items()})
        await client.expire(key, ttl_seconds)

    async def hgetall_json(self, key: str) -> dict[str, Any]:
        client = await self.client()
        if client is None:
            return {}
        values = await client.hgetall(key)
        return {name: json.loads(value) for name, value in values.items()}


cache = CacheClient()


def _generate_cache_key(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()
