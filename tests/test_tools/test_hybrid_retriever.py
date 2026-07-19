import pytest

from agent.tools.rag.retrieval.hybrid_retriever import (
    compute_rrf,
    maximal_marginal_relevance,
    HybridRetriever,
)
from agent.tools.rag.retrieval.entity_filter import RetrievalFilters
from core.sql_executor import PsycopgExecutor


def test_compute_rrf_two_lists_agree():
    dense = {"a": 0, "b": 1}
    sparse = {"a": 0, "b": 1}
    scores = compute_rrf([dense, sparse], k=60)
    assert scores["a"] > scores["b"]


def test_compute_rrf_rewards_agreement_across_lists():
    # "a" ranked well in all three branches; "b" only appears in one.
    list1 = {"a": 0, "b": 5}
    list2 = {"a": 1}
    list3 = {"a": 0}
    scores = compute_rrf([list1, list2, list3], k=60)
    assert scores["a"] > scores["b"]


def test_compute_rrf_missing_chunk_uses_sentinel_rank():
    # "only_in_one" appears in a single list; still gets *some* score via the
    # sentinel rank in the lists it's absent from, but less than a chunk that
    # appears at rank 0 in every list.
    lists = [{"only_in_one": 0}, {}, {}]
    scores = compute_rrf(lists, k=60)
    assert scores["only_in_one"] > 0


def test_compute_rrf_empty_lists_returns_empty():
    assert compute_rrf([{}, {}], k=60) == {}


def test_mmr_returns_all_chunks_when_fewer_than_k():
    chunks = [{"chunk_id": "1"}, {"chunk_id": "2"}]
    result = maximal_marginal_relevance(
        query_embedding=[1.0, 0.0],
        chunk_embeddings=[[1.0, 0.0], [0.9, 0.1]],
        chunks=chunks,
        lambda_mult=0.7,
        k=5,
    )
    assert result == chunks


def test_mmr_prefers_diverse_second_pick():
    chunks = [{"chunk_id": "0"}, {"chunk_id": "1"}, {"chunk_id": "2"}]
    query_embedding = [1.0, 0.0]
    chunk_embeddings = [
        [1.0, 0.0],   # chunk 0: identical to query
        [0.99, 0.01],  # chunk 1: near-duplicate of chunk 0
        [0.0, 1.0],   # chunk 2: orthogonal to query, but diverse
    ]
    result = maximal_marginal_relevance(
        query_embedding=query_embedding,
        chunk_embeddings=chunk_embeddings,
        chunks=chunks,
        lambda_mult=0.5,
        k=2,
    )
    result_ids = [c["chunk_id"] for c in result]
    assert result_ids[0] == "0"
    assert result_ids[1] == "2"


def test_hybrid_retriever_filter_sql_empty_filters():
    retriever = HybridRetriever(executor=PsycopgExecutor())
    filter_sql, params = retriever._filter_sql(RetrievalFilters())
    assert filter_sql == ""
    assert params is None


def test_hybrid_retriever_filter_sql_dosen_and_tahun():
    retriever = HybridRetriever(executor=PsycopgExecutor())
    filters = RetrievalFilters(dosen_ids=[556], tahun=[2024])
    filter_sql, params = retriever._filter_sql(filters)
    assert "dosen_ids @> %s::int[]" in filter_sql
    assert "tahun = ANY(%s)" in filter_sql
    assert params == ([556], [2024])


@pytest.mark.asyncio
async def test_dosen_scope_only_sees_own_komentar_chunks(scope_dosen):
    retriever = HybridRetriever(executor=PsycopgExecutor())
    results = await retriever.retrieve(
        query="pendapat mahasiswa tentang perkuliahan",
        user_scope=scope_dosen,
        source_types=["komentar_mahasiswa"],
    )
    dosen_id = scope_dosen.active_role.dosen_id
    for chunk in results:
        assert dosen_id in (chunk.get("dosen_ids") or []), (
            "RLS violation: dosen scope returned a komentar_mahasiswa chunk not authored "
            "for their own dosen_id"
        )
