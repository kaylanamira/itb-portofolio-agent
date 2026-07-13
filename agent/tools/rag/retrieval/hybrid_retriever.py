import numpy as np
from typing import List, Dict, Any

from core.sql_executor import QueryExecutor
from core.scope import UserScope
from core.config import settings
from agent.tools.rag.core.embedder import embed_text

def compute_rrf(dense_ranks: Dict[str, int], sparse_ranks: Dict[str, int], k: int) -> Dict[str, float]:
    rrf_scores = {}
    all_chunk_ids = set(dense_ranks.keys()).union(set(sparse_ranks.keys()))
    
    for chunk_id in all_chunk_ids:
        dense_score = 1.0 / (k + dense_ranks.get(chunk_id, 1000))
        sparse_score = 1.0 / (k + sparse_ranks.get(chunk_id, 1000))
        rrf_scores[chunk_id] = dense_score + sparse_score
        
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

    async def _dense_search(self, query_embedding: List[float], source_types: List[str], user_scope: UserScope) -> List[Dict[str, Any]]:
        source_types_sql = "ARRAY[" + ",".join([f"'{s}'" for s in source_types]) + "]::varchar[]"
        embedding_sql = f"'{list(query_embedding)}'::vector"
        
        query = f"""
            SELECT vc.chunk_id, vc.chunk_text, vc.source_type, vc.tipe_konten, 
                   vc.embedding::text as embedding_str
            FROM analitik.vector_chunks vc
            LEFT JOIN analitik.v_akademik_portofolio vp 
                   ON vc.source_type = 'teks_portofolio' AND vc.kelas_id = vp.kelas_id
            LEFT JOIN analitik.v_akademik_komentar_mahasiswa vk 
                   ON vc.source_type = 'komentar_mahasiswa' AND vc.kelas_id = vk.kelas_id
            WHERE vc.source_type = ANY({source_types_sql})
              AND (vp.kelas_id IS NOT NULL OR vk.kelas_id IS NOT NULL)
            ORDER BY vc.embedding <=> {embedding_sql}
            LIMIT {self.fetch_k};
        """
        
        result = await self.executor.execute(query, user_scope)
        return result.rows

    async def _sparse_search(self, query: str, source_types: List[str], user_scope: UserScope) -> List[Dict[str, Any]]:
        query_fmt = ' | '.join(query.split())
        source_types_sql = "ARRAY[" + ",".join([f"'{s}'" for s in source_types]) + "]::varchar[]"
        query_fmt_escaped = query_fmt.replace("'", "''")
        
        query_sql = f"""
            SELECT vc.chunk_id, vc.chunk_text, vc.source_type, vc.tipe_konten
            FROM analitik.vector_chunks vc
            LEFT JOIN analitik.v_akademik_portofolio vp 
                   ON vc.source_type = 'teks_portofolio' AND vc.kelas_id = vp.kelas_id
            LEFT JOIN analitik.v_akademik_komentar_mahasiswa vk 
                   ON vc.source_type = 'komentar_mahasiswa' AND vc.kelas_id = vk.kelas_id
            WHERE vc.source_type = ANY({source_types_sql})
              AND (vp.kelas_id IS NOT NULL OR vk.kelas_id IS NOT NULL)
              AND vc.fts_vector @@ to_tsquery('indonesian', '{query_fmt_escaped}')
            ORDER BY ts_rank(vc.fts_vector, to_tsquery('indonesian', '{query_fmt_escaped}')) DESC
            LIMIT {self.fetch_k};
        """
        
        result = await self.executor.execute(query_sql, user_scope)
        return result.rows

    async def retrieve(self, query: str, user_scope: UserScope, source_types: List[str] = None) -> List[Dict[str, Any]]:
        if not source_types:
            source_types = ['teks_portofolio', 'komentar_mahasiswa']
            
        query_embedding = embed_text(query)
        
        dense_results = await self._dense_search(query_embedding, source_types, user_scope)
        sparse_results = await self._sparse_search(query, source_types, user_scope)
        
        chunk_map = {}
        for row in dense_results:
            chunk_map[str(row['chunk_id'])] = row
        for row in sparse_results:
            if str(row['chunk_id']) not in chunk_map:
                chunk_map[str(row['chunk_id'])] = row

        dense_ranks = {str(r['chunk_id']): idx for idx, r in enumerate(dense_results)}
        sparse_ranks = {str(r['chunk_id']): idx for idx, r in enumerate(sparse_results)}
        
        rrf_scores = compute_rrf(dense_ranks, sparse_ranks, k=self.rrf_k)
        
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
