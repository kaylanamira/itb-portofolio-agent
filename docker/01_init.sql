-- docker/init.sql
-- Runs automatically on first container boot (empty volume).
-- Subsequent starts skip this file entirely.

-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Enable pg_trgm (optional — useful for fuzzy text matching later)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Indonesian full-text search dictionary
-- 'indonesian' uses the built-in Snowball stemmer that ships with Postgres.
-- Verify it works:
-- SELECT to_tsvector('indonesian', 'fasilitas kampus laboratorium');
-- If you see tokens, the dictionary is available.

-- The RAG schema tables (wisudawan_vector_chunks, etc.) are created lazily
-- by VectorIndexer.ensure_schema() on first run — no DDL needed here.