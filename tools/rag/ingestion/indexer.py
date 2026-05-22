"""
Vector Store Indexer — pgvector (multilingual FTS)
===================================================
Embeds chunks and upserts into Postgres with TWO tsvector columns:
  fts_id  — to_tsvector('indonesian', chunk_text)
  fts_en  — to_tsvector('english',    chunk_text)
  fts_si  — to_tsvector('simple',     chunk_text)   ← catches code-mixed

Language is detected at ingestion time and stored in metadata["lang"].
Sparse search then queries the appropriate column(s) based on query language.

Why three columns instead of one?
  A single 'indonesian' tsvector silently produces garbage tokens for
  English text ("work" → no match, "hard" → no match), causing sparse
  search to return empty results for English/mixed chunks. Two dedicated
  columns + 'simple' as a universal fallback ensures every chunk is
  reachable by keyword search regardless of language.

References:
  Postgres FTS docs: https://www.postgresql.org/docs/current/textsearch.html
  pgvector: https://github.com/pgvector/pgvector
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras
from tqdm import tqdm

from tools.rag.config import EmbeddingConfig, VectorDBConfig
from tools.rag.core.embedder import EmbeddingModel
from tools.rag.core.models import Chunk
from tools.rag.ingestion.lang_detect import detect_language

logger = logging.getLogger(__name__)

_PORTO_SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE vector_chunks
    ADD COLUMN IF NOT EXISTS chunk_text  TEXT,
    ADD COLUMN IF NOT EXISTS metadata    JSONB    DEFAULT '{{}}',
    ADD COLUMN IF NOT EXISTS embedding   vector({dim}),
    ADD COLUMN IF NOT EXISTS fts_id      tsvector
        GENERATED ALWAYS AS (to_tsvector('indonesian', COALESCE(chunk_text, ''))) STORED,
    ADD COLUMN IF NOT EXISTS fts_en      tsvector
        GENERATED ALWAYS AS (to_tsvector('english',    COALESCE(chunk_text, ''))) STORED,
    ADD COLUMN IF NOT EXISTS fts_si      tsvector
        GENERATED ALWAYS AS (to_tsvector('simple',     COALESCE(chunk_text, ''))) STORED;

CREATE INDEX IF NOT EXISTS idx_vc_embedding_hnsw
    ON vector_chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = {hnsw_m}, ef_construction = {hnsw_ef});

CREATE INDEX IF NOT EXISTS idx_vc_fts_id ON vector_chunks USING gin(fts_id);
CREATE INDEX IF NOT EXISTS idx_vc_fts_en ON vector_chunks USING gin(fts_en);
CREATE INDEX IF NOT EXISTS idx_vc_fts_si ON vector_chunks USING gin(fts_si);
CREATE INDEX IF NOT EXISTS idx_vc_metadata ON vector_chunks USING gin(metadata jsonb_path_ops);
"""

_WISUDAWAN_SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS {table} (
    chunk_id    TEXT         PRIMARY KEY,
    doc_id      TEXT         NOT NULL,
    domain      TEXT         NOT NULL DEFAULT 'wisudawan',
    chunk_text  TEXT         NOT NULL,
    metadata    JSONB        NOT NULL DEFAULT '{{}}',
    embedding   vector({dim}),
    fts_id      tsvector
        GENERATED ALWAYS AS (to_tsvector('indonesian', COALESCE(chunk_text, ''))) STORED,
    fts_en      tsvector
        GENERATED ALWAYS AS (to_tsvector('english',    COALESCE(chunk_text, ''))) STORED,
    fts_si      tsvector
        GENERATED ALWAYS AS (to_tsvector('simple',     COALESCE(chunk_text, ''))) STORED
);

CREATE INDEX IF NOT EXISTS idx_{safe}_embedding_hnsw
    ON {table}
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = {hnsw_m}, ef_construction = {hnsw_ef});

CREATE INDEX IF NOT EXISTS idx_{safe}_fts_id ON {table} USING gin(fts_id);
CREATE INDEX IF NOT EXISTS idx_{safe}_fts_en ON {table} USING gin(fts_en);
CREATE INDEX IF NOT EXISTS idx_{safe}_fts_si ON {table} USING gin(fts_si);
CREATE INDEX IF NOT EXISTS idx_{safe}_metadata ON {table} USING gin(metadata jsonb_path_ops);
"""

_PORTO_UPSERT_SQL = """
INSERT INTO vector_chunks
    (chunk_id, doc_id, domain, chunk_text, metadata, embedding, kelas_id)
VALUES
    (%(chunk_id)s, %(doc_id)s, %(domain)s, %(chunk_text)s,
     %(metadata)s::jsonb, %(embedding)s::vector, %(kelas_id)s::uuid)
ON CONFLICT (chunk_id) DO UPDATE SET
    chunk_text = EXCLUDED.chunk_text,
    metadata   = EXCLUDED.metadata,
    embedding  = EXCLUDED.embedding;
"""

_WISUDAWAN_UPSERT_SQL = """
INSERT INTO {table}
    (chunk_id, doc_id, domain, chunk_text, metadata, embedding)
VALUES
    (%(chunk_id)s, %(doc_id)s, %(domain)s, %(chunk_text)s,
     %(metadata)s::jsonb, %(embedding)s::vector)
ON CONFLICT (chunk_id) DO UPDATE SET
    chunk_text = EXCLUDED.chunk_text,
    metadata   = EXCLUDED.metadata,
    embedding  = EXCLUDED.embedding;
"""

_DELETE_BY_DOC_SQL = "DELETE FROM {table} WHERE doc_id = %(doc_id)s;"


class VectorIndexer:
    def __init__(
        self,
        embedding_config: EmbeddingConfig,
        vdb_config: VectorDBConfig,
        dsn: str,
        user_id: Optional[str] = None,
    ):
        self.embedding_config = embedding_config
        self.vdb_config = vdb_config
        self.dsn = dsn
        self.user_id = user_id
        self._embedder = EmbeddingModel.get_instance(embedding_config)

    def ensure_schema(self) -> None:
        dim    = self.vdb_config.embedding_dimension
        m      = self.vdb_config.hnsw_m
        ef     = self.vdb_config.hnsw_ef_construction
        wtable = self.vdb_config.wisudawan_table
        safe   = wtable.replace(".", "_")

        conn = self._connect()
        try:
            with conn.cursor() as cur:
                # Porto DDL alters the existing vector_chunks table from porto_schema.sql.
                # Skip safely if porto schema has not been applied yet.
                try:
                    cur.execute(_PORTO_SCHEMA_SQL.format(dim=dim, hnsw_m=m, hnsw_ef=ef))
                    conn.commit()
                except Exception as e:
                    logger.warning(f"Porto schema DDL skipped (porto_schema.sql not applied?): {e}")
                    conn.rollback()
                cur.execute(_WISUDAWAN_SCHEMA_SQL.format(
                    table=wtable, safe=safe, dim=dim, hnsw_m=m, hnsw_ef=ef
                ))
            conn.commit()
        finally:
            conn.close()
        logger.info("pgvector schema ready (fts_id + fts_en + fts_si).")

    def index_chunks(self, chunks: List[Chunk], batch_size: int = 64) -> int:
        if not chunks:
            return 0

        # Detect language for every chunk and stamp into metadata
        self._stamp_language(chunks)

        domain_groups: Dict[str, List[Chunk]] = {}
        for chunk in chunks:
            domain_groups.setdefault(chunk.domain, []).append(chunk)

        total = 0
        conn = self._connect()
        try:
            for domain, domain_chunks in domain_groups.items():
                total += self._upsert_domain(conn, domain, domain_chunks, batch_size)
            conn.commit()
        finally:
            conn.close()
        return total

    @staticmethod
    def _stamp_language(chunks: List[Chunk]) -> None:
        """
        Detect language of each chunk and store as metadata["lang"].
        Runs in-process — lingua is fast (~0.5ms per chunk on CPU).
        """
        for chunk in chunks:
            if "lang" not in chunk.metadata:
                chunk.metadata["lang"] = detect_language(chunk.text)

    def _upsert_domain(
        self,
        conn,
        domain: str,
        chunks: List[Chunk],
        batch_size: int,
    ) -> int:
        table      = self._table_for(domain)
        upsert_sql = (
            _PORTO_UPSERT_SQL
            if domain == "porto"
            else _WISUDAWAN_UPSERT_SQL.format(table=table)
        )

        logger.info(f"Embedding {len(chunks)} chunks for '{domain}'...")
        all_embeddings = self._embedder.embed_passages([c.text for c in chunks])

        upserted = 0
        with conn.cursor() as cur:
            for i in tqdm(range(0, len(chunks), batch_size), desc=f"Upserting {table}"):
                batch      = chunks[i : i + batch_size]
                batch_embs = all_embeddings[i : i + batch_size]

                rows = [
                    {
                        "chunk_id":   chunk.chunk_id,
                        "doc_id":     chunk.doc_id,
                        "domain":     chunk.domain,
                        "chunk_text": chunk.text,
                        "metadata":   json.dumps(chunk.metadata),
                        "embedding":  self._vec_literal(emb),
                        "kelas_id":   chunk.metadata.get("kelas_id") if domain == "porto" else None,
                    }
                    for chunk, emb in zip(batch, batch_embs)
                ]
                psycopg2.extras.execute_batch(cur, upsert_sql, rows)
                upserted += len(batch)

        logger.info(f"Upserted {upserted} chunks into '{table}'")
        return upserted

    def delete_by_doc_id(self, doc_id: str, domain: str) -> None:
        table = self._table_for(domain)
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(_DELETE_BY_DOC_SQL.format(table=table), {"doc_id": doc_id})
            conn.commit()
        finally:
            conn.close()

    def _connect(self):
        conn = psycopg2.connect(self.dsn)
        if self.user_id:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL app.user_id = %s", (str(self.user_id),))
        return conn

    def _table_for(self, domain: str) -> str:
        return (
            self.vdb_config.wisudawan_table
            if domain == "wisudawan"
            else self.vdb_config.porto_table
        )

    @staticmethod
    def _vec_literal(arr) -> str:
        return "[" + ",".join(f"{v:.8f}" for v in arr) + "]"