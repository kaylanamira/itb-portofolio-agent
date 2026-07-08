CREATE SCHEMA IF NOT EXISTS agent_memory;

CREATE TABLE IF NOT EXISTS agent_memory.chat_sessions (
    session_id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    active_role TEXT NOT NULL,
    title TEXT,
    summary TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_memory.chat_messages (
    message_id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES agent_memory.chat_sessions(session_id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL,
    turn_index INTEGER NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    query_type TEXT,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_memory_chat_messages_session
    ON agent_memory.chat_messages (session_id, turn_index, message_id);

CREATE INDEX IF NOT EXISTS idx_agent_memory_chat_sessions_user
    ON agent_memory.chat_sessions (user_id, updated_at DESC);
