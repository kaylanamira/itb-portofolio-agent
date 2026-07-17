import numpy as np
from typing import List, Dict, Any, Optional

from core.sql_executor import QueryExecutor
from core.scope import UserScope
from core.config import settings
from agent.tools.rag.core.embedder import aembed_query_text
from agent.tools.rag.retrieval.entity_filter import RetrievalFilters

_RRF_MISSING_RANK_SENTINEL = 1000

# Metadata columns returned alongside chunk_text — used downstream for citations
# (source provenance shown to the user) and to let RLS-invariant tests verify
# that returned rows actually respect the caller's scope.
_METADATA_COLUMNS = (
    "chunk_id, chunk_text, source_type, tipe_konten, kelas_id, "
    "kode_matkul, nama_matkul, tahun, tahun_ajaran, no_prodi, kode_prodi, "
    "kode_fakultas, dosen_ids, dosen_names, is_verifikator"
)


def compute_rrf(rank_lists: List[Dict[str, int]], k: int) -> Dict[str, float]:
    """Reciprocal Rank Fusion over N rank-lists (dense, sparse, and any number of
    HyDE-hypothesis dense branches). Each rank_list maps chunk_id -> 0-based rank
    within that retrieval branch; a chunk absent from a branch is scored as if
    ranked at _RRF_MISSING_RANK_SENTINEL in that branch.
    """
    rrf_scores: Dict[str, float] = {}
    all_chunk_ids = set()
    for ranks in rank_lists:
        all_chunk_ids.update(ranks.keys())

    for chunk_id in all_chunk_ids:
        rrf_scores[chunk_id] = sum(
            1.0 / (k + ranks.get(chunk_id, _RRF_MISSING_RANK_SENTINEL))
            for ranks in rank_lists
        )

    return rrf_scores


def maximal_marginal_relevance(
    query_embedding: List[float],
    chunk_embeddings: List[List[float]],
    chunks: List[Dict[str, Any]],
    lambda_mult: float,
    k: int
) -> List[Dict[str, Any]]:
    if not chunks:
        return []

    if len(chunks) <= k:
        return chunks

    q_emb = np.array(query_embedding)
    doc_embs = np.array(chunk_embeddings)

    q_norm = np.linalg.norm(q_emb)
    doc_norms = np.linalg.norm(doc_embs, axis=1)

    doc_norms[doc_norms == 0] = 1e-10
    q_norm = q_norm if q_norm != 0 else 1e-10

    sim_to_query = np.dot(doc_embs, q_emb) / (doc_norms * q_norm)

    selected_indices = []
    unselected_indices = list(range(len(chunks)))

    best_idx = int(np.argmax(sim_to_query))
    selected_indices.append(best_idx)
    unselected_indices.remove(best_idx)

    while len(selected_indices) < k and unselected_indices:
        best_score = -np.inf
        best_idx_to_add = -1

        for idx in unselected_indices:
            sim_q = sim_to_query[idx]
            sim_selected = 0.0

            for s_idx in selected_indices:
                s_emb = doc_embs[s_idx]
                s_norm = doc_norms[s_idx]
                c_emb = doc_embs[idx]
                c_norm = doc_norms[idx]

                sim_s = np.dot(s_emb, c_emb) / (s_norm * c_norm)
                if sim_s > sim_selected:
                    sim_selected = sim_s

            mmr_score = lambda_mult * sim_q - (1 - lambda_mult) * sim_selected

            if mmr_score > best_score:
                best_score = mmr_score
                best_idx_to_add = idx

        if best_idx_to_add != -1:
            selected_indices.append(best_idx_to_add)
            unselected_indices.remove(best_idx_to_add)

    return [chunks[i] for i in selected_indices]


class HybridRetriever:
    def __init__(self, executor: QueryExecutor):
        self.executor = executor
        self.top_k = settings.RAG_TOP_K_FINAL
        self.rrf_k = settings.RAG_RRF_K
        self.fetch_k = settings.RAG_TOP_K_AFTER_RRF
        self.mmr_lambda = settings.RAG_MMR_LAMBDA

    def _filter_sql(self, filters: Optional[RetrievalFilters]) -> tuple[str, tuple]:
        if filters is None:
            return "", None
        clauses, params = filters.to_sql_predicates()
        if not clauses:
            return "", None
        return "".join(f" AND {c}" for c in clauses), tuple(params)

    async def _dense_search(
        self,
        query_embedding: List[float],
        source_types: List[str],
        user_scope: UserScope,
        filters: Optional[RetrievalFilters] = None,
    ) -> List[Dict[str, Any]]:
        source_types_sql = "ARRAY[" + ",".join([f"'{s}'" for s in source_types]) + "]::varchar[]"
        embedding_sql = f"'{list(query_embedding)}'::vector"
        filter_sql, filter_params = self._filter_sql(filters)

        # RLS is enforced natively on analitik.vector_chunks (pol_vector_chunks,
        # db/schema_vector_chunks.sql) via SET LOCAL app.* in PsycopgExecutor —
        # no join to v_akademik_* views needed for row security anymore.
        query = f"""
            SELECT {_METADATA_COLUMNS}, embedding::text as embedding_str
            FROM analitik.vector_chunks
            WHERE source_type = ANY({source_types_sql})
            {filter_sql}
            ORDER BY embedding <=> {embedding_sql}
            LIMIT {self.fetch_k};
        """

        result = await self.executor.execute(query, user_scope, params=filter_params)
        return result.rows

    async def _sparse_search(
        self,
        query: str,
        source_types: List[str],
        user_scope: UserScope,
        filters: Optional[RetrievalFilters] = None,
    ) -> List[Dict[str, Any]]:
        query_fmt = ' | '.join(query.split())
        source_types_sql = "ARRAY[" + ",".join([f"'{s}'" for s in source_types]) + "]::varchar[]"
        query_fmt_escaped = query_fmt.replace("'", "''")
        filter_sql, filter_params = self._filter_sql(filters)

        query_sql = f"""
            SELECT {_METADATA_COLUMNS}
            FROM analitik.vector_chunks
            WHERE source_type = ANY({source_types_sql})
              AND fts_vector @@ to_tsquery('indonesian', '{query_fmt_escaped}')
            {filter_sql}
            ORDER BY ts_rank(fts_vector, to_tsquery('indonesian', '{query_fmt_escaped}')) DESC
            LIMIT {self.fetch_k};
        """

        result = await self.executor.execute(query_sql, user_scope, params=filter_params)
        return result.rows

    async def retrieve(
        self,
        query: str,
        user_scope: UserScope,
        source_types: Optional[List[str]] = None,
        filters: Optional[RetrievalFilters] = None,
        hyde_embeddings: Optional[List[List[float]]] = None,
    ) -> List[Dict[str, Any]]:
        """Hybrid dense+sparse retrieval fused via RRF, diversified via MMR.

        hyde_embeddings (if provided) are additional dense-search query vectors —
        each becomes its own parallel retrieval branch fused into the same RRF
        ranking alongside the original-query dense+sparse branches (Multi-HyDE,
        Gao et al. 2022), not a replacement for the original-query search.
        """
        if not source_types:
            source_types = ['teks_portofolio', 'komentar_mahasiswa']

        query_embedding = await aembed_query_text(query)

        dense_results = await self._dense_search(query_embedding, source_types, user_scope, filters)
        sparse_results = await self._sparse_search(query, source_types, user_scope, filters)

        rank_lists: List[Dict[str, int]] = [
            {str(r['chunk_id']): idx for idx, r in enumerate(dense_results)},
            {str(r['chunk_id']): idx for idx, r in enumerate(sparse_results)},
        ]
        chunk_map: Dict[str, Any] = {}
        for row in dense_results + sparse_results:
            chunk_map.setdefault(str(row['chunk_id']), row)

        if hyde_embeddings:
            for hyde_embedding in hyde_embeddings:
                hyde_results = await self._dense_search(hyde_embedding, source_types, user_scope, filters)
                rank_lists.append({str(r['chunk_id']): idx for idx, r in enumerate(hyde_results)})
                for row in hyde_results:
                    chunk_map.setdefault(str(row['chunk_id']), row)

        rrf_scores = compute_rrf(rank_lists, k=self.rrf_k)

        sorted_chunk_ids = sorted(rrf_scores.keys(), key=lambda cid: rrf_scores[cid], reverse=True)
        top_fusion_chunks = [chunk_map[cid] for cid in sorted_chunk_ids[:self.fetch_k]]

        valid_chunks_for_mmr = []
        chunk_embeddings = []

        for chunk in top_fusion_chunks:
            if 'embedding_str' in chunk and chunk['embedding_str']:
                emb_str = chunk['embedding_str'].strip('[]')
                emb_list = [float(x) for x in emb_str.split(',')]
                chunk_embeddings.append(emb_list)
                valid_chunks_for_mmr.append(chunk)

        if len(valid_chunks_for_mmr) < self.top_k:
            return top_fusion_chunks[:self.top_k]

        final_chunks = maximal_marginal_relevance(
            query_embedding=query_embedding,
            chunk_embeddings=chunk_embeddings,
            chunks=valid_chunks_for_mmr,
            lambda_mult=self.mmr_lambda,
            k=self.top_k
        )

        return final_chunks
