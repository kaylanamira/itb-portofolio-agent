from __future__ import annotations

import logging
from enum import Enum, auto
from typing import List

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Intent taxonomy
# ---------------------------------------------------------------------------

class QueryIntent(Enum):
    SUBJECTIVE   = auto() 
    AGGREGATIVE  = auto()
    FACTUAL      = auto()


_AGGREGATIVE_PHRASES = [
    # Frequency / prevalence
    "yang sering", "yang paling sering", "yang banyak", "paling banyak",
    "rata-rata", "pada umumnya", "umumnya", "kebanyakan", "mayoritas",
    "berapa banyak", "seberapa sering", "seberapa besar",
    # Summary / trend
    "apa saja", "apa-apa saja", "hal apa saja", "secara umum",
    "secara keseluruhan", "tren", "pola", "gambaran umum",
    "ringkasan", "rangkuman", "kesimpulan", "overview",
    # Aggregation verbs
    "sebutkan", "daftarkan", "list", "rekap", "rekapitulasi",
    # Comparison
    "perbandingan", "bandingkan", "dibandingkan", "perbedaan antara",
]

_AGGREGATIVE_TOKENS = {
    "keluhan", "masalah", "permasalahan", "kekurangan", "kelemahan",
    "kelebihan", "keunggulan", "harapan", "saran", "rekomendasi",
    "kritik", "pendapat", "opini", "aspirasi", "persepsi",
    "distribusi", "statistik", "proporsi", "persentase",
    "tren", "pola", "tema", "topik", "isu",
}

_SUBJECTIVE_PHRASES = [
    "yang lucu", "yang kocak", "yang mengharukan", "yang unik",
    "yang menarik", "yang inspiratif", "yang berkesan", "yang gokil",
    "yang menyentuh", "yang dramatis", "yang absurd", "yang receh",
    "paling lucu", "paling keren", "paling parah", "paling unik",
    "paling mengharukan", "paling berkesan",
    "cerita yang", "kisah yang", "komentar yang", "jawaban yang",
    "cari contoh", "carikan contoh", "tunjukkan contoh",
]

_SUBJECTIVE_TOKENS = {
    "lucu", "humor", "kocak", "gokil", "absurd", "receh",
    "mengharukan", "menyentuh", "inspiratif",
    "sedih", "menyedihkan", "keren", "aneh", "gila", "lebay",
    "santai", "dramatis", "memorable",
}


class QueryIntentClassifier:
    def classify(self, query: str) -> QueryIntent:
        q = query.lower().strip()

        if self._is_aggregative(q):
            return QueryIntent.AGGREGATIVE

        if self._is_subjective(q):
            return QueryIntent.SUBJECTIVE

        return QueryIntent.FACTUAL

    def needs_hyde(self, query: str) -> bool:
        return self.classify(query) == QueryIntent.SUBJECTIVE

    def explain(self, query: str) -> str:
        intent = self.classify(query)
        q = query.lower()

        if intent == QueryIntent.AGGREGATIVE:
            matched_phrases = [p for p in _AGGREGATIVE_PHRASES if p in q]
            matched_tokens  = set(q.split()) & _AGGREGATIVE_TOKENS
            return (
                f"AGGREGATIVE — use broad retrieval + synthesis, not HyDE. "
                f"Signals: phrases={matched_phrases}, tokens={matched_tokens}"
            )
        if intent == QueryIntent.SUBJECTIVE:
            matched_phrases = [p for p in _SUBJECTIVE_PHRASES if p in q]
            matched_tokens  = set(q.split()) & _SUBJECTIVE_TOKENS
            return (
                f"SUBJECTIVE — HyDE activated. "
                f"Signals: phrases={matched_phrases}, tokens={matched_tokens}"
            )
        return "FACTUAL — standard hybrid retrieval."

    @staticmethod
    def _is_aggregative(q: str) -> bool:
        for phrase in _AGGREGATIVE_PHRASES:
            if phrase in q:
                return True
        tokens = set(q.split())
        return bool(tokens & _AGGREGATIVE_TOKENS)

    @staticmethod
    def _is_subjective(q: str) -> bool:
        for phrase in _SUBJECTIVE_PHRASES:
            if phrase in q:
                return True
        tokens = set(q.split())
        return bool(tokens & _SUBJECTIVE_TOKENS)

class RetrievalStrategy:
    """
    Translates a QueryIntent into concrete retrieval parameters.
    Passed to HybridRetriever.retrieve() to adjust behaviour per intent.
    """

    @staticmethod
    def for_intent(
        intent: QueryIntent,
        base_top_k_dense: int = 10,
        base_top_k_rerank: int = 5,
    ) -> dict:
        if intent == QueryIntent.AGGREGATIVE:
            return {
                "top_k_dense_override":  min(base_top_k_dense * 3, 30),
                "top_k_rerank_override": min(base_top_k_rerank * 3, 15),
                "force_hyde": False,
            }
        if intent == QueryIntent.SUBJECTIVE:
            return {
                "top_k_dense_override":  base_top_k_dense,
                "top_k_rerank_override": base_top_k_rerank,
                "force_hyde": True,
            }
        return {
            "top_k_dense_override":  base_top_k_dense,
            "top_k_rerank_override": base_top_k_rerank,
            "force_hyde": False,
        }

class HyDETransformer:
    def __init__(
        self,
        llm_fn,
        embedder,
        n_hypothetical: int = 3,
        domain: str = "wisudawan",
    ):
        self.llm = llm_fn
        self.embedder = embedder
        self.n = n_hypothetical
        self.domain = domain

    def transform(self, query: str) -> np.ndarray:
        hypotheticals = self._generate_hypotheticals(query)
        if not hypotheticals:
            logger.warning("[HyDE] Generation failed. Falling back to query embedding.")
            return self.embedder.embed_query(query)

        embeddings = self.embedder.embed_passages(hypotheticals)
        mean_vec = embeddings.mean(axis=0)
        norm = np.linalg.norm(mean_vec)
        if norm > 0:
            mean_vec = mean_vec / norm

        logger.info(f"[HyDE] {len(hypotheticals)} hypotheticals generated for: '{query}'")
        return mean_vec

    def _generate_hypotheticals(self, query: str) -> List[str]:
        prompt = self._build_prompt(query)
        response = self.llm(prompt)
        return self._parse(response)

    def _build_prompt(self, query: str) -> str:
        domain_ctx = (
            "survei wisudawan ITB (jawaban mahasiswa tentang pengalaman, "
            "saran, cita-cita, dan kesan selama kuliah)"
            if self.domain == "wisudawan"
            else "portofolio akademik ITB (teks refleksi dosen dan komentar mahasiswa)"
        )
        return (
            f"Kamu membantu sistem pencarian di database {domain_ctx}.\n"
            f"Tugas: tulis {self.n} contoh teks BERBEDA yang akan cocok dengan "
            f"pencarian berikut. Setiap contoh ditulis dari sudut pandang mahasiswa "
            f"ITB yang nyata (1–3 kalimat, tidak perlu penjelasan).\n"
            f"Pisahkan setiap contoh dengan '---'.\n\n"
            f"PENCARIAN: {query}\n\n"
            f"CONTOH:"
        )

    @staticmethod
    def _parse(response: str) -> List[str]:
        parts = [p.strip() for p in response.split("---")]
        return [p for p in parts if len(p) > 20]