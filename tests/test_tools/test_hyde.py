import os

import pytest

from agent.tools.rag.retrieval.hyde import should_use_hyde, MultiHydeGenerator
from agent.state import DetectedEntities
from core.config import settings

try:
    from tests.llm_judge import custom_judge  # noqa: F401
    HAS_LLM_JUDGE = True
except ImportError:
    HAS_LLM_JUDGE = False


SENTIMENT_QUERIES = [
    "tolong carikan komentar mahasiswa yang kesal dengan dosen John Doe",
    "bagaimana pendapat mahasiswa tentang praktikum semester ini?",
    "rangkumkan keluhan mahasiswa terhadap kelas IF1220",
    "mahasiswa yang puas dengan pengajaran dosen X",
]

PRECISE_QUERIES = [
    "Apa syarat kelulusan S1 Informatika?",
    "Apa materi minggu ke-3 IF1220?",
    "Berapa SKS mata kuliah IF1220?",
]


@pytest.mark.parametrize("query", SENTIMENT_QUERIES)
def test_should_use_hyde_fires_on_sentiment_keywords(query):
    assert should_use_hyde(query) is True


@pytest.mark.parametrize("query", PRECISE_QUERIES)
def test_should_use_hyde_skips_precise_factual_queries(query):
    # Precise queries are long/specific enough and contain no sentiment vocabulary.
    assert should_use_hyde(query) is False


def test_should_use_hyde_fires_on_short_query_without_anchor_entity():
    entities = DetectedEntities()  # nothing resolved
    assert should_use_hyde("carikan info kelas itu", entities=entities) is True


def test_should_use_hyde_skips_when_anchor_entity_resolved():
    entities = DetectedEntities(resolved_dosen_id=556)
    assert should_use_hyde("carikan info kelas itu", entities=entities) is False


def test_should_use_hyde_respects_disabled_setting(monkeypatch):
    monkeypatch.setattr(settings, "RAG_HYDE_ENABLED", False)
    assert should_use_hyde(SENTIMENT_QUERIES[0]) is False


@pytest.mark.skipif(os.getenv("RUN_LLM_EVALS") != "1", reason="Set RUN_LLM_EVALS=1 to run live LLM HyDE generation")
@pytest.mark.asyncio
async def test_multi_hyde_generates_n_diverse_hypotheses():
    generator = MultiHydeGenerator()
    hypotheses = await generator.generate("komentar mahasiswa yang kesal dengan dosen", n=3)
    assert 1 <= len(hypotheses) <= 3
    assert all(isinstance(h, str) and h.strip() for h in hypotheses)
