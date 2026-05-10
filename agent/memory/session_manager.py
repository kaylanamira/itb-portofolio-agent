from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from agent.tools.cache import CacheKeys, cache
from core.config import settings
from core.database import get_db_connection

logger = logging.getLogger(__name__)


class SessionManager:
    def __init__(self, session_id: str):
        self.session_id = session_id

    async def append_message(self, role: str, content: str) -> None:
        await cache.push_json_trimmed(
            key=CacheKeys.session_messages(self.session_id),
            value={
                "role": role,
                "content": content,
                "ts": datetime.now(UTC).isoformat(),
            },
            max_items=settings.MEMORY_SHORT_TERM_TURNS,
            ttl_seconds=settings.MEMORY_SESSION_TTL_SECONDS,
        )

    async def get_recent_messages(self) -> list[dict]:
        return await cache.get_json_list(CacheKeys.session_messages(self.session_id))

    async def set_entities(self, entities: dict) -> None:
        await cache.hset_json(
            key=CacheKeys.session_entities(self.session_id),
            mapping=entities,
            ttl_seconds=settings.MEMORY_SESSION_TTL_SECONDS,
        )

    async def get_entities(self) -> dict:
        return await cache.hgetall_json(CacheKeys.session_entities(self.session_id))

    async def set_summary(self, summary: str) -> None:
        await cache.set_json(
            CacheKeys.session_summary(self.session_id),
            summary,
            settings.MEMORY_SESSION_TTL_SECONDS,
        )

    async def get_summary(self) -> str | None:
        value = await cache.get_json(CacheKeys.session_summary(self.session_id))
        return value if isinstance(value, str) else None

    async def next_turn_index(self) -> int | None:
        session_uuid = _parse_uuid(self.session_id)
        if session_uuid is None:
            return None
        try:
            async with get_db_connection() as conn:
                cur = await conn.execute(
                    """
                    SELECT COALESCE(MAX(turn_index), 0) + 1
                    FROM conversation_history
                    WHERE session_id = %s::uuid
                    """,
                    (str(session_uuid),),
                )
                row = await cur.fetchone()
                return int(row[0]) if row else 1
        except Exception as exc:
            logger.warning("Could not read next conversation turn index: %s", exc)
            return None

    async def save_turn(
        self,
        user_id: UUID,
        turn_index: int,
        role: str,
        content: str,
        query_type: str | None = None,
        entities: dict | None = None,
        summary: str | None = None,
    ) -> None:
        session_uuid = _parse_uuid(self.session_id)
        if session_uuid is None:
            logger.info("Skipping long-term memory save for non-UUID session_id=%s", self.session_id)
            return
        expires_at = datetime.now(UTC) + timedelta(days=settings.MEMORY_LONG_TERM_DAYS)
        try:
            async with get_db_connection() as conn:
                await conn.execute(
                    """
                    INSERT INTO conversation_history (
                        session_id, user_id, turn_index, role, content,
                        query_type, entities_json, summary, expires_at
                    )
                    VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, %s::jsonb, %s, %s)
                    """,
                    (
                        str(session_uuid),
                        str(user_id),
                        turn_index,
                        role,
                        content,
                        query_type,
                        json.dumps(entities or {}),
                        summary,
                        expires_at,
                    ),
                )
        except Exception as exc:
            logger.warning("Could not persist conversation turn: %s", exc)


def get_session_manager(session_id: str) -> SessionManager:
    return SessionManager(session_id)


def _parse_uuid(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None
