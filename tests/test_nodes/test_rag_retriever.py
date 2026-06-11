import pytest
from tests.conftest import load_cases
from agent.nodes.rag_retriever import rag_retriever

pytestmark = [pytest.mark.asyncio, pytest.mark.rag_phase2, pytest.mark.skip(reason="RAG retriever is Phase 2 scaffold and should not run yet")]


@pytest.mark.parametrize("case", load_cases("rag_retriever_cases.json"))
async def test_rag_retriever_placeholder_returns_dict(case, make_state, scope_kaprodi):
    state = make_state(
        query=case["query"],
        scope=scope_kaprodi,
        plan=[{"task": case["task"], "tool": "rag"}],
    )
    result = await rag_retriever(state)
    assert isinstance(result, dict), "rag_retriever must return a dict"


@pytest.mark.parametrize("case", load_cases("rag_retriever_cases.json"))
async def test_rag_retriever_placeholder_sets_rag_result(case, make_state, scope_kaprodi):
    state = make_state(
        query=case["query"],
        scope=scope_kaprodi,
        plan=[{"task": case["task"], "tool": "rag"}],
    )
    result = await rag_retriever(state)
    assert "rag_chunks" in result, "rag_retriever must set 'rag_chunks'"
    assert isinstance(result["rag_chunks"], list)


@pytest.mark.skip(reason="RAG retrieval quality metrics are deferred to Phase 2 when real vector store is wired")
def test_rag_retriever_ragas_metrics_placeholder():
    pass
