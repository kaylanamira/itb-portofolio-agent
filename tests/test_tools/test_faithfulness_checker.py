import os

import pytest

from agent.tools.rag.evaluation.faithfulness_checker import (
    FaithfulnessChecker,
    ClaimVerification,
    FaithfulnessOutput,
)

try:
    from tests.ragas_judge import HAS_RAGAS, ragas_llm  # noqa: F401
except ImportError:
    HAS_RAGAS = False


@pytest.mark.asyncio
async def test_check_computes_score_from_supported_ratio(monkeypatch):
    checker = FaithfulnessChecker.__new__(FaithfulnessChecker)

    class _MockResponse:
        content = (
            '{"claims": ['
            '{"claim": "A", "supported": true, "supporting_chunk_id": "c1"},'
            '{"claim": "B", "supported": true, "supporting_chunk_id": "c2"},'
            '{"claim": "C", "supported": false, "supporting_chunk_id": null}'
            "]}"
        )

    class _MockLLM:
        async def ainvoke(self, messages):
            return _MockResponse()

    checker.llm = _MockLLM()
    result = await checker.check("some answer with three claims", [{"chunk_id": "c1", "chunk_text": "..."}])

    assert result.score == pytest.approx(2 / 3, rel=1e-3)
    assert len(result.claims) == 3
    assert all(isinstance(c, ClaimVerification) for c in result.claims)
    assert result.claims[0].supported is True
    assert result.claims[2].supported is False
    assert result.claims[2].supporting_chunk_id is None


@pytest.mark.asyncio
async def test_check_empty_answer_returns_zero_without_llm_call():
    checker = FaithfulnessChecker.__new__(FaithfulnessChecker)

    class _ShouldNotBeCalledLLM:
        async def ainvoke(self, messages):
            raise AssertionError("LLM should not be called for an empty answer")

    checker.llm = _ShouldNotBeCalledLLM()
    result = await checker.check("", [{"chunk_id": "c1", "chunk_text": "..."}])
    assert result.score == 0.0
    assert result.claims == []


@pytest.mark.asyncio
async def test_check_no_claims_extracted_returns_zero_score():
    checker = FaithfulnessChecker.__new__(FaithfulnessChecker)

    class _MockResponse:
        content = '{"claims": []}'

    class _MockLLM:
        async def ainvoke(self, messages):
            return _MockResponse()

    checker.llm = _MockLLM()
    result = await checker.check("an answer", [{"chunk_id": "c1", "chunk_text": "..."}])
    assert result.score == 0.0


@pytest.mark.asyncio
async def test_check_degrades_gracefully_on_llm_failure():
    checker = FaithfulnessChecker.__new__(FaithfulnessChecker)

    class _FailingLLM:
        async def ainvoke(self, messages):
            raise RuntimeError("simulated LLM failure")

    checker.llm = _FailingLLM()
    result = await checker.check("an answer", [{"chunk_id": "c1", "chunk_text": "..."}])
    assert result == FaithfulnessOutput(claims=[], score=0.0)


@pytest.mark.skipif(os.getenv("RUN_LLM_EVALS") != "1", reason="Set RUN_LLM_EVALS=1 to run live LLM faithfulness checks")
@pytest.mark.asyncio
async def test_faithfulness_checker_flags_unsupported_claim():
    checker = FaithfulnessChecker()
    chunks = [{"chunk_id": "c1", "chunk_text": "Mahasiswa menilai perkuliahan terorganisir dengan baik."}]
    # The answer asserts something (grading fairness) that isn't in the chunk at all.
    answer = "Dosen dinilai sangat adil dalam memberikan nilai kepada semua mahasiswa."
    result = await checker.check(answer, chunks)
    assert result.score < 0.9
