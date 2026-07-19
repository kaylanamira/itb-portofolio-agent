import os
import re

import pytest

from agent.tools.rag.generation.answer_generator import AnswerGenerator, GeneratedAnswer, Citation

CITATION_MARKER_PATTERN = re.compile(r"\[(\d+)\]")

SAMPLE_CHUNKS = [
    {"chunk_id": "aaa", "source_type": "komentar_mahasiswa", "tipe_konten": "komentar",
     "chunk_text": "Perkuliahan terorganisir dengan baik dan dosen responsif."},
    {"chunk_id": "bbb", "source_type": "teks_portofolio", "tipe_konten": "refleksi_pelaksanaan_perkuliahan",
     "chunk_text": "Dosen menyampaikan bahwa mahasiswa cukup aktif berdiskusi."},
]


@pytest.mark.asyncio
async def test_generate_returns_insufficient_context_when_no_chunks():
    generator = AnswerGenerator.__new__(AnswerGenerator)
    result = await generator.generate("some query", [])
    assert result.insufficient_context is True
    assert result.answer == ""


@pytest.mark.asyncio
async def test_generate_parses_citations_from_mocked_llm():
    generator = AnswerGenerator.__new__(AnswerGenerator)

    class _MockResponse:
        content = (
            '{"answer": "Mahasiswa menilai perkuliahan terorganisir dengan baik [1].", '
            '"citations": [{"marker": 1, "chunk_id": "aaa"}], '
            '"insufficient_context": false}'
        )

    class _MockLLM:
        async def ainvoke(self, messages):
            return _MockResponse()

    generator.llm = _MockLLM()
    result = await generator.generate("bagaimana pendapat mahasiswa?", SAMPLE_CHUNKS)

    assert isinstance(result, GeneratedAnswer)
    markers_in_answer = {int(m) for m in CITATION_MARKER_PATTERN.findall(result.answer)}
    citation_markers = {c.marker for c in result.citations}
    assert markers_in_answer.issubset(citation_markers), (
        "every [n] marker used in the answer text must have a corresponding citation entry"
    )
    assert result.citations == [Citation(marker=1, chunk_id="aaa")]


@pytest.mark.asyncio
async def test_generate_degrades_gracefully_on_llm_failure():
    generator = AnswerGenerator.__new__(AnswerGenerator)

    class _FailingLLM:
        async def ainvoke(self, messages):
            raise RuntimeError("simulated LLM failure")

    generator.llm = _FailingLLM()
    result = await generator.generate("some query", SAMPLE_CHUNKS)
    assert result.insufficient_context is True


@pytest.mark.asyncio
async def test_regenerate_with_critique_falls_back_to_previous_answer_on_failure():
    generator = AnswerGenerator.__new__(AnswerGenerator)

    class _FailingLLM:
        async def ainvoke(self, messages):
            raise RuntimeError("simulated LLM failure")

    generator.llm = _FailingLLM()
    result = await generator.regenerate_with_critique(
        "query", SAMPLE_CHUNKS, previous_answer="original answer", unsupported_claims=["claim X"],
    )
    assert result.answer == "original answer"
    assert result.insufficient_context is True


@pytest.mark.skipif(os.getenv("RUN_LLM_EVALS") != "1", reason="Set RUN_LLM_EVALS=1 to run live LLM generation")
@pytest.mark.asyncio
async def test_generate_live_answer_cites_chunks():
    generator = AnswerGenerator()
    result = await generator.generate("bagaimana pendapat mahasiswa tentang perkuliahan?", SAMPLE_CHUNKS)
    if not result.insufficient_context:
        assert CITATION_MARKER_PATTERN.search(result.answer), "generated answer should cite at least one chunk"
