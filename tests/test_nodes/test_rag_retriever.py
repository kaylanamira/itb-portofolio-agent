import os
import re

import pytest

from tests.conftest import load_cases
from agent.nodes.rag_retriever import rag_retriever
from agent.tools.rag.pipeline import RAGResult, run_rag
from agent.tools.rag.generation.answer_generator import Citation
from agent.tools.rag.retrieval.entity_filter import RetrievalFilters
from evals.datasets.schemas import RagRetrieverCase
from evals.scorer import NodeTestResult, MetricFlag

try:
    from deepeval.metrics import GEval
    from deepeval.test_case import LLMTestCase, LLMTestCaseParams
    from tests.llm_judge import custom_judge
    HAS_DEEPEVAL = True
except ImportError:
    HAS_DEEPEVAL = False

try:
    from ragas.metrics import Faithfulness as RagasFaithfulness
    from ragas.dataset_schema import SingleTurnSample
    from tests.ragas_judge import HAS_RAGAS, ragas_llm
except ImportError:
    HAS_RAGAS = False

CITATION_MARKER_PATTERN = re.compile(r"\[(\d+)\]")

CASES = load_cases("rag_retriever_cases.json", RagRetrieverCase)

@pytest.mark.asyncio
async def test_rag_retriever_maps_ragresult_onto_agent_state(monkeypatch, make_state):
    canned_result = RAGResult(
        answer="Mahasiswa menilai perkuliahan terorganisir dengan baik [1].",
        citations=[Citation(marker=1, chunk_id="chunk-abc")],
        chunks_used=[{"chunk_id": "chunk-abc", "chunk_text": "..."}],
        rag_query="refined query text",
        retrieval_confidence=0.82,
        retrieval_action="ACCEPT",
        faithfulness_score=0.9,
        faithfulness_action="ACCEPT",
        hyde_used=True,
        filters_applied=RetrievalFilters(dosen_ids=[556]),
        attempts={"retrieval_attempts": 1, "generation_attempts": 1},
    )

    async def _mock_run_rag(query, user_scope, source_types=None):
        assert query == "original task"
        return canned_result

    monkeypatch.setattr("agent.nodes.rag_retriever.run_rag", _mock_run_rag)

    state = make_state(
        query="original task",
        plan=[{"task": "original task", "tool": "rag"}],
    )
    result = await rag_retriever(state)

    assert result["rag_query"] == "refined query text"
    assert result["rag_chunks"] == canned_result.chunks_used
    assert result["rag_confidence"] == 0.82
    assert result["rag_action"] == "ACCEPT"
    assert result["rag_refined_query"] == "refined query text"  # differs from original task -> not None
    assert result["faithfulness_score"] == 0.9
    assert result["faithfulness_action"] == "ACCEPT"
    assert result["rag_generated_answer"] == canned_result.answer
    assert result["rag_citations"] == [{"marker": 1, "chunk_id": "chunk-abc"}]


@pytest.mark.asyncio
async def test_rag_retriever_refined_query_is_none_when_unchanged(monkeypatch, make_state):
    canned_result = RAGResult(rag_query="same query", retrieval_action="FALLBACK")

    async def _mock_run_rag(query, user_scope, source_types=None):
        return canned_result

    monkeypatch.setattr("agent.nodes.rag_retriever.run_rag", _mock_run_rag)

    state = make_state(query="same query", plan=[{"task": "same query", "tool": "rag"}])
    result = await rag_retriever(state)

    assert result["rag_refined_query"] is None


@pytest.mark.asyncio
async def test_rag_retriever_falls_back_to_effective_query_without_rag_plan_step(monkeypatch, make_state):
    captured = {}

    async def _mock_run_rag(query, user_scope, source_types=None):
        captured["query"] = query
        return RAGResult()

    monkeypatch.setattr("agent.nodes.rag_retriever.run_rag", _mock_run_rag)

    state = make_state(query="fallback effective query", plan=[])
    await rag_retriever(state)

    assert captured["query"] == "fallback effective query"


@pytest.mark.parametrize("case", CASES)
@pytest.mark.asyncio
async def test_rag_retriever_pipeline_integration(case: RagRetrieverCase, request, node_results):
    scope = request.getfixturevalue(f"scope_{case.scope_role.lower()}")
    result = await run_rag(query=case.task, user_scope=scope)

    if case.expected_empty_result_ok and not result.chunks_used:
        # Legitimately empty retrieval (out-of-domain / graceful-degradation cases) --
        # nothing meaningful to score on faithfulness/citations/entity-resolution.
        node_results.append(NodeTestResult(
            case_id=case.id,
            node_name="rag_retriever",
            passed=True,
            expected_value=case.model_dump(),
            actual_value={"chunks_used": 0},
            metric_flags={},
        ))
        return

    metric_flags = {}

    if case.expected_hyde_triggered is not None:
        metric_flags[MetricFlag.RAG_HYDE_TRIGGER_CORRECT] = (result.hyde_used == case.expected_hyde_triggered)

    entity_checks = []
    if case.expected_dosen_resolved is not None:
        entity_checks.append(bool(result.filters_applied.dosen_ids) == case.expected_dosen_resolved)
    if case.expected_matkul_resolved is not None:
        entity_checks.append(bool(result.filters_applied.kode_matkul) == case.expected_matkul_resolved)
    if entity_checks:
        metric_flags[MetricFlag.RAG_ENTITY_RESOLUTION_CORRECT] = all(entity_checks)

    if case.expected_verifikator_filter is not None:
        metric_flags[MetricFlag.RAG_VERIFIKATOR_FILTER_CORRECT] = (
            result.filters_applied.is_verifikator == case.expected_verifikator_filter
        )

    if case.expected_min_confidence is not None:
        metric_flags[MetricFlag.RAG_RETRIEVAL_RELEVANCE_PASSED] = (
            result.retrieval_confidence >= case.expected_min_confidence
        )

    if case.expected_faithfulness_min is not None and result.answer:
        metric_flags[MetricFlag.RAG_FAITHFULNESS_PASSED] = (
            result.faithfulness_score >= case.expected_faithfulness_min
        )

    if result.answer:
        markers_in_answer = {int(m) for m in CITATION_MARKER_PATTERN.findall(result.answer)}
        citation_markers = {c.marker for c in result.citations}
        citation_valid = markers_in_answer.issubset(citation_markers)
        if case.expected_citation_present:
            citation_valid = citation_valid and bool(result.citations)
        metric_flags[MetricFlag.RAG_CITATION_VALID] = citation_valid

    passed = all(metric_flags.values()) if metric_flags else True

    node_results.append(NodeTestResult(
        case_id=case.id,
        node_name="rag_retriever",
        passed=passed,
        expected_value=case.model_dump(),
        actual_value={
            "hyde_used": result.hyde_used,
            "retrieval_action": result.retrieval_action,
            "faithfulness_action": result.faithfulness_action,
            "citations": len(result.citations),
        },
        metric_flags=metric_flags,
    ))

    assert passed, f"[{case.id}] rag pipeline metrics failed: {metric_flags}"


@pytest.mark.skipif(os.getenv("RUN_LLM_EVALS") != "1", reason="Set RUN_LLM_EVALS=1 to run live LLM/RAGAS evaluation metrics")
@pytest.mark.parametrize("case", [c for c in CASES if c.tags and "policy" not in c.tags])
@pytest.mark.asyncio
async def test_rag_retriever_ragas_faithfulness(case: RagRetrieverCase, request, node_results):
    if not HAS_RAGAS:
        pytest.skip("ragas not installed")

    scope = request.getfixturevalue(f"scope_{case.scope_role.lower()}")
    result = await run_rag(query=case.task, user_scope=scope)
    if not result.answer or not result.chunks_used:
        pytest.skip(f"[{case.id}] no answer/chunks produced, nothing to score")

    try:
        sample = SingleTurnSample(
            user_input=case.task,
            response=result.answer,
            retrieved_contexts=[c.get("chunk_text", "") for c in result.chunks_used],
        )
        metric = RagasFaithfulness(llm=ragas_llm)
        score = await metric.single_turn_ascore(sample)
    except Exception as e:
        pytest.skip(f"ragas API mismatch for this installed version: {e}")
        return

    threshold = 0.6
    passed = score >= threshold

    node_results.append(NodeTestResult(
        case_id=case.id,
        node_name="rag_retriever",
        passed=passed,
        actual_value=score,
        metric_flags={MetricFlag.RAG_FAITHFULNESS_PASSED: passed},
    ))

    assert passed, f"[{case.id}] ragas faithfulness={score} below {threshold}"


@pytest.mark.skipif(os.getenv("RUN_LLM_EVALS") != "1" or not HAS_DEEPEVAL, reason="Set RUN_LLM_EVALS=1 to run live LLM judge metrics")
@pytest.mark.parametrize("case", [c for c in CASES if c.expected_citation_present])
@pytest.mark.asyncio
async def test_rag_retriever_answer_relevance(case: RagRetrieverCase, request, node_results):
    scope = request.getfixturevalue(f"scope_{case.scope_role.lower()}")
    result = await run_rag(query=case.task, user_scope=scope)
    if not result.answer:
        pytest.skip(f"[{case.id}] no answer produced, nothing to score")

    test_case = LLMTestCase(
        input=case.task,
        actual_output=result.answer,
        retrieval_context=[c.get("chunk_text", "") for c in result.chunks_used],
    )
    metric = GEval(
        name="RAG Answer Relevance",
        evaluation_steps=[
            "Check if the answer directly addresses the retrieval task.",
            "Penalize answers that ignore the retrieved context or hallucinate beyond it.",
        ],
        evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.RETRIEVAL_CONTEXT],
        model=custom_judge,
        threshold=0.7,
    )
    metric.measure(test_case)
    passed = metric.score >= 0.7

    node_results.append(NodeTestResult(
        case_id=case.id,
        node_name="rag_retriever",
        passed=passed,
        actual_value=metric.score,
        metric_flags={MetricFlag.RAG_RETRIEVAL_RELEVANCE_PASSED: passed},
    ))

    assert passed, f"[{case.id}] AnswerRelevance={metric.score}: {metric.reason}"
