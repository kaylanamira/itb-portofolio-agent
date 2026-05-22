"""
Hybrid Retriever — pgvector + HyDE
====================================
Dense + sparse retrieval inside Postgres, with optional HyDE query
transformation for subjective/semantic queries.

Pipeline:
  1. Query intent classification — should HyDE be used?
  2a. [Standard] embed query directly
  2b. [HyDE]     LLM generates N hypothetical docs → embed → mean pool
  3. Dense ANN search  — pgvector <=> cosine, HNSW index
  4. Sparse FTS search — tsvector + ts_rank_cd, GIN index
  5. RRF fusion        — Reciprocal Rank Fusion (Cormack et al., 2009)
  6. Cross-encoder rerank (Nogueira & Cho, 2019)
  7. CRAG relevance gate + retry (Yan et al., 2024)

References:
  Gao et al. (2022). "HyDE." arXiv:2212.10496.
  Cormack et al. (2009). "Reciprocal Rank Fusion." SIGIR 2009.
  Nogueira & Cho (2019). "Passage Re-ranking with BERT." arXiv:1901.04085.
  Yan et al. (2024). "CRAG: Corrective RAG." arXiv:2401.15884.
"""

from __future__ import annotations

import json
import logging
import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import psycopg2
import psycopg2.extras

from tools.rag.config import EmbeddingConfig, RetrievalConfig, VectorDBConfig
from tools.rag.core.embedder import EmbeddingModel
from tools.rag.core.models import RetrievalResult, RetrievedChunk
from tools.rag.retrieval.hyde import HyDETransformer, QueryIntent, QueryIntentClassifier, RetrievalStrategy

logger = logging.getLogger(__name__)

_DENSE_SQL = """
SELECT
    chunk_id,
    doc_id,
    chunk_text,
    metadata,
    1 - (embedding <=> %(query_vec)s::vector) AS score
FROM {table}
WHERE embedding IS NOT NULL
  {filter_clause}
ORDER BY embedding <=> %(query_vec)s::vector
LIMIT %(limit)s;
"""

_SPARSE_SQL = """
WITH id_matches AS (
    SELECT chunk_id, doc_id, chunk_text, metadata,
           ts_rank_cd(fts_id, plainto_tsquery('indonesian', %(query_text)s)) AS score
    FROM {table}
    WHERE fts_id @@ plainto_tsquery('indonesian', %(query_text)s)
      {filter_clause}
),
en_matches AS (
    SELECT chunk_id, doc_id, chunk_text, metadata,
           ts_rank_cd(fts_en, plainto_tsquery('english', %(query_text)s)) AS score
    FROM {table}
    WHERE fts_en @@ plainto_tsquery('english', %(query_text)s)
      {filter_clause}
),
si_matches AS (
    SELECT chunk_id, doc_id, chunk_text, metadata,
           ts_rank_cd(fts_si, plainto_tsquery('simple', %(query_text)s)) AS score
    FROM {table}
    WHERE fts_si @@ plainto_tsquery('simple', %(query_text)s)
      {filter_clause}
),
all_matches AS (
    SELECT chunk_id, doc_id, chunk_text, metadata, score FROM id_matches
    UNION ALL
    SELECT chunk_id, doc_id, chunk_text, metadata, score FROM en_matches
    UNION ALL
    SELECT chunk_id, doc_id, chunk_text, metadata, score FROM si_matches
)
SELECT
    chunk_id,
    doc_id,
    chunk_text,
    metadata,
    SUM(score) AS score           -- reward chunks matching multiple lang columns
FROM all_matches
GROUP BY chunk_id, doc_id, chunk_text, metadata
ORDER BY score DESC
LIMIT %(limit)s;
"""

_JSONB_FILTER = "AND metadata @> %(filter_json)s::jsonb"


class HybridRetriever:
    def __init__(
        self,
        embedding_config: EmbeddingConfig,
        retrieval_config: RetrievalConfig,
        vdb_config: VectorDBConfig,
        dsn: str,
        domain: str = "porto",
        user_id: Optional[str] = None,
        llm_fn=None,
        n_hypothetical: int = 3,
    ):
        self.cfg = retrieval_config
        self.vdb_cfg = vdb_config
        self.dsn = dsn
        self.domain = domain
        self.user_id = user_id
        self._embedder = EmbeddingModel.get_instance(embedding_config)
        self._reranker = self._init_reranker()
        self._classifier = QueryIntentClassifier()

        # HyDE transformer — None means disabled
        self._hyde: Optional[HyDETransformer] = None
        if llm_fn is not None:
            self._hyde = HyDETransformer(
                llm_fn=llm_fn,
                embedder=self._embedder,
                n_hypothetical=n_hypothetical,
                domain=domain,
            )

    def set_hyde(self, hyde: HyDETransformer) -> None:
        """Inject a pre-built HyDETransformer (e.g. for sharing an LLM instance)."""
        self._hyde = hyde

    def retrieve(
        self,
        query: str,
        metadata_filter: Optional[Dict[str, Any]] = None,
        attempt: int = 1,
        force_hyde: Optional[bool] = None,
        top_k_dense_override: Optional[int] = None,
        top_k_rerank_override: Optional[int] = None,
    ) -> RetrievalResult:
        # Classify intent & derive strategy
        intent = self._classifier.classify(query)
        strategy = RetrievalStrategy.for_intent(
            intent,
            base_top_k_dense=self.cfg.top_k_dense,
            base_top_k_rerank=self.cfg.top_k_rerank,
        )
        logger.info(f"[Retriever] {self._classifier.explain(query)}")

        # Merge overrides (caller > strategy > config)
        top_k_dense  = top_k_dense_override  or strategy["top_k_dense_override"]
        top_k_rerank = top_k_rerank_override or strategy["top_k_rerank_override"]
        use_hyde     = force_hyde if force_hyde is not None else strategy["force_hyde"]

        # Get query vector
        query_vec = self._get_query_vector(query, use_hyde)

        # Retrieve
        conn = self._connect()
        try:
            dense_results  = self._dense_search(conn, query_vec, metadata_filter, top_k_dense)
            sparse_results = self._sparse_search(conn, query, metadata_filter)
        finally:
            conn.close()

        fused    = self._reciprocal_rank_fusion(dense_results, sparse_results)
        reranked = self._rerank(query, fused)
        is_relevant = self._check_relevance(reranked)

        result = RetrievalResult(
            query=query,
            chunks=reranked[:top_k_rerank],
            is_relevant=is_relevant,
            attempt=attempt,
        )

        # CRAG retry
        if not is_relevant and attempt < self.cfg.max_retry_attempts:
            reformulated = self._reformulate_query(query)
            logger.info(
                f"[CRAG] Low relevance (attempt {attempt}). "
                f"Reformulating: '{query}' → '{reformulated}'"
            )
            retry = self.retrieve(
                reformulated,
                metadata_filter=metadata_filter,
                attempt=attempt + 1,
                force_hyde=use_hyde,
                top_k_dense_override=top_k_dense,
                top_k_rerank_override=top_k_rerank,
            )
            retry.reformulated_query = reformulated
            if self._best_score(retry.chunks) > self._best_score(result.chunks):
                return retry

        return result

    def _should_use_hyde(self, query: str, force: Optional[bool]) -> bool:
        if force is not None:
            return force and self._hyde is not None
        return self._hyde is not None and self._classifier.needs_hyde(query)

    def _get_query_vector(self, query: str, use_hyde: bool) -> str:
        """
        Return a pgvector-compatible literal string for the query vector.
        Uses HyDE mean embedding when activated, standard query embedding otherwise.
        """
        if use_hyde and self._hyde is not None:
            vec: np.ndarray = self._hyde.transform(query)
        else:
            vec = self._embedder.embed_query(query)
        return self._vec_literal(vec)

    def _dense_search(
        self,
        conn,
        query_vec: str,
        metadata_filter: Optional[Dict[str, Any]],
        top_k: Optional[int] = None,
    ) -> List[RetrievedChunk]:
        filter_clause, filter_params = self._build_filter(metadata_filter)
        sql = _DENSE_SQL.format(table=self._table, filter_clause=filter_clause)
        params = {"query_vec": query_vec, "limit": top_k or self.cfg.top_k_dense, **filter_params}
        rows = self._fetchall(conn, sql, params)
        return [self._row_to_chunk(r, dense_score=float(r["score"])) for r in rows]

    def _sparse_search(
        self,
        conn,
        query: str,
        metadata_filter: Optional[Dict[str, Any]],
    ) -> List[RetrievedChunk]:
        filter_clause, filter_params = self._build_filter(metadata_filter)
        sql = _SPARSE_SQL.format(table=self._table, filter_clause=filter_clause)
        params = {
            "query_text": query,
            "limit": self.cfg.top_k_sparse,
            **filter_params,
        }
        try:
            rows = self._fetchall(conn, sql, params)
            return [
                self._row_to_chunk(r, sparse_score=float(r["score"]))
                for r in rows if float(r["score"]) > 0
            ]
        except Exception as e:
            logger.warning(f"Sparse search failed: {e}. Returning empty.")
            return []

    def _reciprocal_rank_fusion(
        self,
        dense: List[RetrievedChunk],
        sparse: List[RetrievedChunk],
    ) -> List[RetrievedChunk]:
        k = self.cfg.rrf_k
        scores: Dict[str, float] = {}
        chunk_map: Dict[str, RetrievedChunk] = {}

        for rank, chunk in enumerate(dense, start=1):
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + 1.0 / (k + rank)
            chunk_map[chunk.chunk_id] = chunk

        for rank, chunk in enumerate(sparse, start=1):
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + 1.0 / (k + rank)
            if chunk.chunk_id not in chunk_map:
                chunk_map[chunk.chunk_id] = chunk
            else:
                chunk_map[chunk.chunk_id].sparse_score = chunk.sparse_score

        fused = []
        for cid, rrf_score in sorted(scores.items(), key=lambda x: -x[1]):
            c = chunk_map[cid]
            c.score = rrf_score
            fused.append(c)
        return fused

    def _rerank(self, query: str, chunks: List[RetrievedChunk]) -> List[RetrievedChunk]:
        if not chunks or self._reranker is None:
            return chunks
        pairs = [[query, c.text] for c in chunks]
        scores = self._reranker.predict(pairs)
        for chunk, score in zip(chunks, scores):
            chunk.score = float(score)
        return sorted(chunks, key=lambda c: -c.score)

    def _check_relevance(self, chunks: List[RetrievedChunk]) -> bool:
        if not chunks:
            return False
        sigmoid = 1.0 / (1.0 + math.exp(-chunks[0].score))
        return sigmoid >= self.cfg.relevance_threshold

    def _best_score(self, chunks: List[RetrievedChunk]) -> float:
        if not chunks:
            return 0.0
        return 1.0 / (1.0 + math.exp(-chunks[0].score))

    def _reformulate_query(self, query: str) -> str:
        """HyDE-inspired keyword expansion fallback when LLM not available."""
        expansions = {
            "fasilitas": "fasilitas sarana prasarana gedung laboratorium perpustakaan",
            "dosen": "dosen pengajar tenaga pengajar lecturer",
            "nilai": "nilai grade IPK prestasi akademik",
            "kepuasan": "kepuasan puas tidak puas tingkat kepuasan",
            "lucu": "humor kocak gokil bercanda cerita seru receh",
            "mengharukan": "terharu sedih emosional berkesan menyentuh hati",
        }
        for keyword, expansion in expansions.items():
            if keyword in query.lower():
                return f"{query} {expansion}"
        return query

    @property
    def _table(self) -> str:
        return (self.vdb_cfg.wisudawan_table
                if self.domain == "wisudawan"
                else self.vdb_cfg.porto_table)

    def _connect(self):
        conn = psycopg2.connect(self.dsn)
        conn.autocommit = False
        if self.user_id:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL app.user_id = %s", (str(self.user_id),))
        return conn

    @staticmethod
    def _fetchall(conn, sql: str, params: Dict[str, Any]) -> List[Dict]:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    @staticmethod
    def _build_filter(
        metadata_filter: Optional[Dict[str, Any]]
    ) -> Tuple[str, Dict[str, Any]]:
        if not metadata_filter:
            return "", {}
        clean = {k: v for k, v in metadata_filter.items() if v is not None}
        if not clean:
            return "", {}
        return _JSONB_FILTER, {"filter_json": json.dumps(clean)}

    @staticmethod
    def _row_to_chunk(
        row: Dict[str, Any],
        dense_score: float = 0.0,
        sparse_score: float = 0.0,
    ) -> RetrievedChunk:
        meta = row.get("metadata") or {}
        if isinstance(meta, str):
            meta = json.loads(meta)
        return RetrievedChunk(
            chunk_id=row["chunk_id"],
            doc_id=row["doc_id"],
            text=row["chunk_text"],
            metadata=meta,
            score=float(row.get("score", 0.0)),
            dense_score=dense_score,
            sparse_score=sparse_score,
        )

    @staticmethod
    def _vec_literal(arr: np.ndarray) -> str:
        return "[" + ",".join(f"{v:.8f}" for v in arr) + "]"

    def _init_reranker(self):
        try:
            from sentence_transformers import CrossEncoder
            logger.info(f"Loading reranker: {self.cfg.reranker_model}")
            return CrossEncoder(self.cfg.reranker_model)
        except Exception as e:
            logger.warning(f"Reranker not loaded: {e}. Using RRF scores only.")
            return None