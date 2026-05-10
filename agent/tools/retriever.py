from __future__ import annotations

import asyncio
import logging
import math
import re
from collections.abc import Sequence
from typing import Any

from psycopg import sql

from agent.tools.cache import CacheKeys, cache
from agent.tools.embeddings import EmbeddingClient, embedding_client
from agent.tools.rag_models import RAGChunk, RAGRetrievalRequest, RAGRetrievalResult
from core.config import settings
from core.database import get_db_connection
from core.scope import UserScope

logger = logging.getLogger(__name__)

SCOPE_OVERRIDE_COLUMNS = frozenset({
    "kode_mk",
    "kode_prodi",
    "kode_fakultas",
    "no_kelas",
    "semester",
    "tahun_ajaran",
    "jenjang",
})


class HybridRetriever:
    def __init__(self, embedding_client: EmbeddingClient = embedding_client):
        self.embedding_client = embedding_client

    async def retrieve(
        self,
        request: RAGRetrievalRequest,
        user_scope: UserScope,
    ) -> RAGRetrievalResult:
        query_embedding = await self.embedding_client.embed_query(request.query)
        cached = await _get_semantic_cached_chunks(request, user_scope, query_embedding)
        if cached is not None:
            return RAGRetrievalResult(
                query=request.query,
                chunks=[RAGChunk.model_validate(chunk) for chunk in cached],
                cache_hit=True,
            )

        lexical_query = _build_lexical_query(request.query, request.keywords)

        dense_rows, lexical_rows = await asyncio.gather(
            self._dense_search(request, user_scope, query_embedding),
            self._lexical_search(request, user_scope, lexical_query),
        )
        # 4. RRF fusion -> unified ranked list, top RAG_TOP_K_AFTER_RRF
        chunks = _fuse_ranked_results(dense_rows, lexical_rows)
        chunks = chunks[: request.top_k_after_rrf]
        
        # 5. Cross-encoder rerank -> conditional: diagnostic / analytical_hybrid
        if request.query_type in ("diagnostic", "analytical_hybrid"):
            # TODO: Implement cross-encoder reranking here when model is available
            # chunks = _cross_encoder_rerank(chunks, request)
            pass

        # 6. MMR (conditional) -> for komentar_mahasiswa sources only -> top RAG_TOP_K_FINAL
        chunks = _final_select(chunks, request)

        # 7. Parent expansion -> rrf_score >= RAG_PARENT_EXPAND_THRESHOLD
        chunks = await self._expand_parents(chunks, user_scope)

        serialized = [chunk.model_dump(mode="json") for chunk in chunks]
        await _store_semantic_cached_chunks(request, user_scope, query_embedding, serialized)
        return RAGRetrievalResult(query=request.query, chunks=chunks)

    async def _dense_search(
        self,
        request: RAGRetrievalRequest,
        user_scope: UserScope,
        embedding: Sequence[float],
    ) -> list[dict[str, Any]]:
        where_sql, params = _build_where_clause(request, user_scope)
        embedding_literal = "[" + ",".join(f"{float(value):.8f}" for value in embedding) + "]"
        query = sql.SQL("""
            SELECT
                chunk_id, source_type, source_id, kelas_id, tipe_konten::text AS tipe_konten,
                chunk_index, chunk_text, kode_mk, kode_prodi, kode_fakultas, no_kelas,
                semester, tahun_ajaran, nama_mk, nama_prodi, nama_fakultas, jenjang,
                semua_dosen_id, semua_dosen_nama, kelas_label,
                1 - (embedding <=> %s::vector) AS score
            FROM vector_chunks
            WHERE embedding IS NOT NULL AND {where_clause}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """).format(where_clause=where_sql)
        return await _fetch_rows(query, [embedding_literal, *params, embedding_literal, request.top_k_after_rrf], user_scope)

    async def _lexical_search(
        self,
        request: RAGRetrievalRequest,
        user_scope: UserScope,
        lexical_query: str,
    ) -> list[dict[str, Any]]:
        where_sql, params = _build_where_clause(request, user_scope)
        # 1. Fetch up to 500 broad candidates via FTS
        query = sql.SQL("""
            SELECT
                chunk_id, source_type, source_id, kelas_id, tipe_konten::text AS tipe_konten,
                chunk_index, chunk_text, kode_mk, kode_prodi, kode_fakultas, no_kelas,
                semester, tahun_ajaran, nama_mk, nama_prodi, nama_fakultas, jenjang,
                semua_dosen_id, semua_dosen_nama, kelas_label
            FROM vector_chunks
            WHERE fts_vector @@ websearch_to_tsquery('simple', %s)
              AND {where_clause}
            LIMIT 500
        """).format(where_clause=where_sql)
        
        candidates = await _fetch_rows(query, [lexical_query, *params], user_scope)
        if not candidates:
            return []

        from rank_bm25 import BM25Okapi
        
        # 2. Tokenize documents and query (preserving term frequency)
        tokenized_corpus = [_tokenize_list(c["chunk_text"]) for c in candidates]
        tokenized_query = _tokenize_list(lexical_query)
        
        # 3. Calculate True BM25
        bm25 = BM25Okapi(tokenized_corpus)
        scores = bm25.get_scores(tokenized_query)
        
        for i, candidate in enumerate(candidates):
            candidate["score"] = float(scores[i])
            
        ranked = sorted(candidates, key=lambda x: x["score"], reverse=True)
        return ranked[:request.top_k_after_rrf]

    async def _expand_parents(self, chunks: list[RAGChunk], user_scope: UserScope) -> list[RAGChunk]:
        expandable_ids = [
            chunk.source_id
            for chunk in chunks
            if chunk.source_type == "teks_portofolio"
            and chunk.rrf_score >= settings.RAG_PARENT_EXPAND_THRESHOLD
        ]
        if not expandable_ids:
            return chunks
        async with get_db_connection() as conn:
            async with conn.transaction():
                await conn.execute(
                    sql.SQL("SET LOCAL app.user_id = {}").format(sql.Literal(str(user_scope.user_id)))
                )
                cur = await conn.execute(
                    """
                    SELECT teks_id, konten
                    FROM teks_portofolio
                    WHERE teks_id = ANY(%s::uuid[])
                      AND konten IS NOT NULL
                    """,
                    ([str(value) for value in expandable_ids],),
                )
                rows = await cur.fetchall()
            content_by_id = {row[0]: row[1] for row in rows}

        expanded: list[RAGChunk] = []
        for chunk in chunks:
            parent_text = content_by_id.get(chunk.source_id)
            if parent_text:
                expanded.append(chunk.model_copy(update={
                    "chunk_text": parent_text,
                    "expanded_from_parent": True,
                }))
            else:
                expanded.append(chunk)
        return expanded


async def _fetch_rows(query: sql.Composable, params: list[Any], user_scope: UserScope) -> list[dict[str, Any]]:
    async with get_db_connection() as conn:
        async with conn.transaction():
            await conn.execute(
                sql.SQL("SET LOCAL app.user_id = {}").format(sql.Literal(str(user_scope.user_id)))
            )
            cur = await conn.execute(query, params)
            rows = await cur.fetchall()
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in rows]


def _build_where_clause(request: RAGRetrievalRequest, user_scope: UserScope) -> tuple[sql.Composable, list[Any]]:
    scope_where, scope_params = user_scope.scope_where("teks_portofolio")
    clauses: list[sql.Composable] = [sql.SQL(scope_where)]
    params: list[Any] = [*scope_params]

    if request.source_types:
        clauses.append(sql.SQL("source_type = ANY(%s::text[])"))
        params.append(request.source_types)
    if request.tipe_konten:
        clauses.append(sql.SQL("tipe_konten::text = ANY(%s::text[])"))
        params.append(request.tipe_konten)
    for key, value in (request.scope_override or {}).items():
        if key not in SCOPE_OVERRIDE_COLUMNS or value is None:
            continue
        clauses.append(sql.SQL("{} = %s").format(sql.Identifier(key)))
        params.append(value)

    return sql.SQL(" AND ").join(clauses), params


def _fuse_ranked_results(dense_rows: list[dict[str, Any]], lexical_rows: list[dict[str, Any]]) -> list[RAGChunk]:
    by_id: dict[Any, dict[str, Any]] = {}
    for rank, row in enumerate(dense_rows, start=1):
        item = by_id.setdefault(row["chunk_id"], row.copy())
        item["dense_rank"] = rank
        item["rrf_score"] = item.get("rrf_score", 0.0) + 1.0 / (settings.RAG_RRF_K + rank)
    for rank, row in enumerate(lexical_rows, start=1):
        item = by_id.setdefault(row["chunk_id"], row.copy())
        item["lexical_rank"] = rank
        item["rrf_score"] = item.get("rrf_score", 0.0) + 1.0 / (settings.RAG_RRF_K + rank)

    chunks = [RAGChunk.model_validate(row) for row in by_id.values()]
    return sorted(chunks, key=lambda chunk: chunk.rrf_score, reverse=True)


def _final_select(chunks: list[RAGChunk], request: RAGRetrievalRequest) -> list[RAGChunk]:
    if not chunks:
        return []
    source_types = set(request.source_types or [chunk.source_type for chunk in chunks])
    should_mmr = bool(source_types & set(settings.RAG_MMR_ENABLED_SOURCES))
    if should_mmr:
        return _mmr_select(chunks, request.top_k)
    return chunks[: request.top_k]


def _mmr_select(chunks: list[RAGChunk], top_k: int) -> list[RAGChunk]:
    selected: list[RAGChunk] = []
    remaining = chunks.copy()
    while remaining and len(selected) < top_k:
        best = max(
            remaining,
            key=lambda chunk: (
                settings.RAG_MMR_LAMBDA * chunk.rrf_score
                - (1 - settings.RAG_MMR_LAMBDA) * _max_text_similarity(chunk, selected)
            ),
        )
        selected.append(best)
        remaining.remove(best)
    return selected


def _max_text_similarity(chunk: RAGChunk, selected: list[RAGChunk]) -> float:
    if not selected:
        return 0.0
    chunk_tokens = _token_set(chunk.chunk_text)
    if not chunk_tokens:
        return 0.0
    return max(_jaccard(chunk_tokens, _token_set(item.chunk_text)) for item in selected)


def _token_set(text: str) -> set[str]:
    return set(_tokenize_list(text))


def _tokenize_list(text: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[A-Za-z0-9_]{3,}", text)]


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _build_lexical_query(query: str, keywords: list[str]) -> str:
    if keywords:
        return " ".join(keywords)
    return query


async def _get_semantic_cached_chunks(
    request: RAGRetrievalRequest,
    user_scope: UserScope,
    query_embedding: Sequence[float],
) -> list[dict] | None:
    entries = await cache.get_json_list(_semantic_index_key(request, user_scope))
    best_entry: dict | None = None
    best_score = -1.0
    for entry in entries:
        cached_embedding = entry.get("embedding")
        if not cached_embedding:
            continue
        score = _cosine_similarity(query_embedding, cached_embedding)
        if score > best_score:
            best_entry = entry
            best_score = score

    if best_entry and best_score >= settings.CACHE_RAG_SEMANTIC_THRESHOLD:
        logger.info(
            "RAG semantic cache hit similarity=%.4f threshold=%.4f",
            best_score,
            settings.CACHE_RAG_SEMANTIC_THRESHOLD,
        )
        return best_entry.get("chunks") or []
    return None


async def _store_semantic_cached_chunks(
    request: RAGRetrievalRequest,
    user_scope: UserScope,
    query_embedding: Sequence[float],
    chunks: list[dict],
) -> None:
    await cache.push_json_trimmed(
        key=_semantic_index_key(request, user_scope),
        value={
            "query": request.query,
            "embedding": [float(value) for value in query_embedding],
            "chunks": chunks,
        },
        max_items=settings.CACHE_RAG_SEMANTIC_INDEX_SIZE,
        ttl_seconds=settings.CACHE_RAG_SESSION_TTL_SECONDS,
    )


def _semantic_index_key(request: RAGRetrievalRequest, user_scope: UserScope) -> str:
    payload = {
        "source_types": request.source_types,
        "tipe_konten": request.tipe_konten,
        "scope_override": request.scope_override,
        "top_k": request.top_k,
        "top_k_after_rrf": request.top_k_after_rrf,
    }
    return CacheKeys.retrieval_index(
        payload=payload,
        scope_fingerprint=CacheKeys.scope_fingerprint(user_scope),
    )


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(float(a) * float(b) for a, b in zip(left, right))
    left_norm = math.sqrt(sum(float(value) * float(value) for value in left))
    right_norm = math.sqrt(sum(float(value) * float(value) for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


retriever = HybridRetriever()
