-- RAG retrieval support for BGE-M3 embeddings and Postgres full-text search.

CREATE EXTENSION IF NOT EXISTS "vector";

DROP INDEX IF EXISTS idx_vc_embedding_hnsw;

ALTER TABLE vector_chunks
    ALTER COLUMN embedding TYPE VECTOR(1024)
    USING NULL;

ALTER TABLE vector_chunks
    ADD COLUMN IF NOT EXISTS fts_vector TSVECTOR;

CREATE OR REPLACE FUNCTION fn_vector_chunks_fts()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.fts_vector := to_tsvector('simple', COALESCE(NEW.chunk_text, ''));
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_vector_chunks_fts ON vector_chunks;
CREATE TRIGGER trg_vector_chunks_fts
    BEFORE INSERT OR UPDATE OF chunk_text ON vector_chunks
    FOR EACH ROW EXECUTE FUNCTION fn_vector_chunks_fts();

UPDATE vector_chunks
SET fts_vector = to_tsvector('simple', COALESCE(chunk_text, ''))
WHERE fts_vector IS NULL;

CREATE INDEX IF NOT EXISTS idx_vc_fts ON vector_chunks USING GIN(fts_vector);
CREATE INDEX IF NOT EXISTS idx_vc_embedding_hnsw
    ON vector_chunks USING hnsw (embedding vector_cosine_ops)
    WHERE embedding IS NOT NULL;

CREATE TABLE IF NOT EXISTS conversation_history (
    memory_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id    UUID NOT NULL,
    user_id       UUID REFERENCES pengguna(user_id),
    turn_index    INTEGER NOT NULL,
    role          VARCHAR(10) NOT NULL CHECK (role IN ('user', 'assistant')),
    content       TEXT NOT NULL,
    query_type    VARCHAR(30),
    entities_json JSONB,
    summary       TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at    TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_conv_hist_session
    ON conversation_history(session_id, turn_index);

CREATE INDEX IF NOT EXISTS idx_conv_hist_expiry
    ON conversation_history(expires_at);
