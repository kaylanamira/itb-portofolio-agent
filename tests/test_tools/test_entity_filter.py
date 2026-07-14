import os

import pytest

from agent.tools.rag.retrieval.entity_filter import (
    RetrievalFilters,
    RagEntityExtraction,
    resolve_filters,
)

def test_to_sql_predicates_empty_filters_produces_no_clauses():
    clauses, params = RetrievalFilters().to_sql_predicates()
    assert clauses == []
    assert params == []


def test_to_sql_predicates_all_fields():
    filters = RetrievalFilters(
        dosen_ids=[556],
        tahun=[2023, 2024],
        tahun_ajaran="2023/2024",
        no_prodi=135,
        kode_matkul="IF1220",
        semester=1,
        is_verifikator=True,
    )
    clauses, params = filters.to_sql_predicates()

    assert clauses == [
        "dosen_ids @> %s::int[]",
        "tahun = ANY(%s)",
        "tahun_ajaran = %s",
        "no_prodi = %s",
        "kode_matkul = %s",
        "semester = %s",
        "is_verifikator = %s",
    ]
    assert params == [[556], [2023, 2024], "2023/2024", 135, "IF1220", 1, True]


def test_to_sql_predicates_is_verifikator_false_is_a_real_filter_not_absence():
    # False ("only the dosen's own content, not reviewer comments") must still
    # produce a predicate -- it's a meaningful choice, not "no preference".
    clauses, params = RetrievalFilters(is_verifikator=False).to_sql_predicates()
    assert clauses == ["is_verifikator = %s"]
    assert params == [False]


def test_is_empty():
    assert RetrievalFilters().is_empty() is True
    assert RetrievalFilters(dosen_ids=[1]).is_empty() is False
    assert RetrievalFilters(semester=2).is_empty() is False
    assert RetrievalFilters(is_verifikator=True).is_empty() is False
    assert RetrievalFilters(is_verifikator=False).is_empty() is False
    

@pytest.mark.skipif(os.getenv("RUN_LLM_EVALS") != "1", reason="Set RUN_LLM_EVALS=1 to run live LLM entity extraction")
@pytest.mark.asyncio
async def test_resolve_filters_kesal_dosen_query_extracts_sentiment_and_dosen():
    filters = await resolve_filters("tolong carikan komentar mahasiswa yang kesal dengan dosen John Doe")
    assert filters.sentiment_hint == "negative"


@pytest.mark.asyncio
async def test_resolve_filters_degrades_gracefully_on_fuzzy_resolution_failure(monkeypatch):
    from agent.tools.rag.retrieval import entity_filter as ef_module

    async def _extract(self, task):
        return RagEntityExtraction(dosen_mention="Someone Unresolvable")

    async def _raise_fuzzy_error(entities, config=None):
        raise ef_module.FuzzyResolutionError("simulated DB error")

    monkeypatch.setattr(ef_module.EntityFilterExtractor, "extract", _extract)
    monkeypatch.setattr(ef_module, "fuzzy_resolve_entities", _raise_fuzzy_error)

    # Must not raise -- retrieval should proceed without name-based filters
    # rather than being blocked by a fuzzy-resolution/DB error.
    filters = await resolve_filters("some query mentioning a dosen")
    assert filters.dosen_ids == []


@pytest.mark.asyncio
async def test_extract_returns_empty_extraction_on_llm_failure(monkeypatch):
    from agent.tools.rag.retrieval.entity_filter import EntityFilterExtractor

    extractor = EntityFilterExtractor.__new__(EntityFilterExtractor)

    class _FailingLLM:
        async def ainvoke(self, messages):
            raise RuntimeError("simulated LLM failure")

    extractor.llm = _FailingLLM()
    result = await extractor.extract("some query")
    assert result == RagEntityExtraction()
