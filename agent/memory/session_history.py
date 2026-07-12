from __future__ import annotations

import logging
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from agent.llm import get_llm
from agent.prompts.conversation_summary import build_conversation_summary_messages
from core.config import settings
from core.redis_client import get_redis
from core.scope import UserScope

logger = logging.getLogger(__name__)


class ConversationMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str
    ts: str | None = None
    metadata: dict | None = None


class ConversationHistory(BaseModel):
    session_id: str
    summary: str | None = None
    messages: list[ConversationMessage] = Field(default_factory=list)


class SessionHistoryStore:
    def __init__(self) -> None:
        self.ttl_seconds = settings.MEMORY_SESSION_TTL_SECONDS
        self.max_turns = settings.MEMORY_SHORT_TERM_TURNS

    def messages_key(self, session_id: str) -> str:
        return f"chat:{session_id}:messages"

    def summary_key(self, session_id: str) -> str:
        return f"chat:{session_id}:summary"

    async def load_history(self, session_id: str) -> ConversationHistory:
        try:
            redis = get_redis()
            raw_messages = await redis.lrange(self.messages_key(session_id), 0, -1)
            summary = await redis.get(self.summary_key(session_id))
        except Exception as exc:
            logger.warning("Failed to load conversation history: %s", exc)
            return ConversationHistory(session_id=session_id)

        messages = []
        for raw in raw_messages:
            try:
                messages.append(ConversationMessage.model_validate_json(raw))
            except Exception:
                logger.warning("Skipping invalid conversation message for session=%s", session_id)

        return ConversationHistory(session_id=session_id, summary=summary, messages=messages)

    async def save_turn(
        self,
        session_id: str,
        user_message: str,
        assistant_message: str,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        messages = [
            ConversationMessage(role="user", content=user_message, ts=now),
            ConversationMessage(role="assistant", content=assistant_message, ts=now),
        ]

        try:
            redis = get_redis()
            key = self.messages_key(session_id)
            await redis.rpush(key, *[message.model_dump_json() for message in messages])
            await redis.expire(key, self.ttl_seconds)
            await redis.expire(self.summary_key(session_id), self.ttl_seconds)
        except Exception as exc:
            logger.warning("Failed to append conversation turn: %s", exc)

    async def summarize_history(self, session_id: str) -> None:
        max_messages = self.max_turns * 2

        try:
            redis = get_redis()
            key = self.messages_key(session_id)
            message_count = await redis.llen(key)
            overflow_count = message_count - max_messages
            if overflow_count <= 0:
                return

            raw_messages = await redis.lrange(key, 0, overflow_count - 1)
            previous_summary = await redis.get(self.summary_key(session_id))
            messages = []
            for raw in raw_messages:
                try:
                    messages.append(ConversationMessage.model_validate_json(raw))
                except Exception:
                    logger.warning("Skipping invalid message during summarization for session=%s", session_id)

            summary = await self._summarize_messages(previous_summary, messages)
            await redis.setex(self.summary_key(session_id), self.ttl_seconds, summary)
            await redis.ltrim(key, overflow_count, -1)
            await redis.expire(key, self.ttl_seconds)
        except Exception as exc:
            logger.warning("Failed to summarize conversation history: %s", exc)

    async def save_turn_to_archive(
        self,
        session_id: str,
        user_scope: UserScope,
        user_message: str,
        assistant_message: str,
        query_type: str | None = None,
        summary: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        if not settings.CHAT_ARCHIVE_ENABLED:
            return

        import json
        metadata_json = json.dumps(metadata) if metadata else None

        try:
            from core.database import get_db_connection

            async with get_db_connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        INSERT INTO agent_memory.chat_sessions (session_id, user_id, active_role, summary)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (session_id) DO UPDATE SET
                            summary = COALESCE(EXCLUDED.summary, agent_memory.chat_sessions.summary),
                            updated_at = now()
                        """,
                        (
                            session_id,
                            user_scope.user_id,
                            user_scope.role.value,
                            summary,
                        ),
                    )
                    await cur.execute(
                        """
                        SELECT COALESCE(MAX(turn_index), 0) + 1
                        FROM agent_memory.chat_messages
                        WHERE session_id = %s
                        """,
                        (session_id,),
                    )
                    row = await cur.fetchone()
                    turn_index = row[0] if row else 1
                    await cur.executemany(
                        """
                        INSERT INTO agent_memory.chat_messages
                            (session_id, user_id, turn_index, role, content, query_type, metadata)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        [
                            (session_id, user_scope.user_id, turn_index, "user", user_message, query_type, None),
                            (session_id, user_scope.user_id, turn_index, "assistant", assistant_message, query_type, metadata_json),
                        ],
                    )
                await conn.commit()
        except Exception as exc:
            logger.warning("Failed to archive conversation turn: %s", exc)

    async def _summarize_messages(
        self,
        previous_summary: str | None,
        messages: list[ConversationMessage],
    ) -> str:
        if not messages:
            return previous_summary or ""

        try:
            llm = get_llm("query_rewriter", force_json=False)
            prompt_messages = build_conversation_summary_messages(
                previous_summary=previous_summary,
                messages=[message.model_dump() for message in messages],
            )
            response = await llm.ainvoke(
                [
                    SystemMessage(content=prompt_messages[0]["content"]),
                    HumanMessage(content=prompt_messages[1]["content"]),
                ]
            )
            content = str(response.content).strip()
            if content:
                return content
        except Exception as exc:
            logger.warning("Failed to generate conversation summary: %s", exc)

        return self._fallback_summary(previous_summary, messages)

    def _fallback_summary(
        self,
        previous_summary: str | None,
        messages: list[ConversationMessage],
    ) -> str:
        parts = [previous_summary.strip()] if previous_summary else []
        for message in messages[-6:]:
            content = " ".join(message.content.split())
            if content:
                parts.append(f"{message.role}: {content[:240]}")
        return "\n".join(parts)[-2000:]


_session_history_store = SessionHistoryStore()


def get_session_history_store() -> SessionHistoryStore:
    return _session_history_store
