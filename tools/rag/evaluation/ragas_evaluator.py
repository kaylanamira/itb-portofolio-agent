from __future__ import annotations

import json
import logging
import re
from typing import List, Optional, Tuple

import numpy as np

from tools.rag.config import EvaluationConfig
from tools.rag.core.embedder import EmbeddingModel
from tools.rag.core.models import RAGASScores, RetrievedChunk

logger = logging.getLogger(__name__)


class RAGASEvaluator:
    def __init__(
        self,
        config: EvaluationConfig,
        embedding_model: EmbeddingModel,
        llm_generate_fn,
    ):
        self.config = config
        self._embedder = embedding_model
        self._llm = llm_generate_fn

    def evaluate(
        self,
        query: str,
        answer: str,
        retrieved_chunks: List[RetrievedChunk],
    ) -> RAGASScores:
        """
        Run all three RAGAS metrics and return aggregated scores.
        """
        context_texts = [c.text for c in retrieved_chunks]

        cr = self.context_relevance(query, context_texts)
        fa = self.faithfulness(answer, context_texts)
        ar = self.answer_relevance(query, answer)

        scores = RAGASScores(
            context_relevance=cr,
            faithfulness=fa,
            answer_relevance=ar,
        )
        # Override passed flag with config thresholds
        scores.passed = (
            cr >= self.config.min_context_relevance
            and fa >= self.config.min_faithfulness
            and ar >= self.config.min_answer_relevance
        )

        logger.info(
            f"[RAGAS] CR={cr:.3f} | FA={fa:.3f} | AR={ar:.3f} | "
            f"{'PASS' if scores.passed else 'FAIL'}"
        )
        return scores

    def context_relevance(self, query: str, context_texts: List[str]) -> float:
        """
        For each retrieved chunk, ask the LLM whether it is relevant to the query.
        Score = (number of relevant chunks) / (total chunks).
        """
        if not context_texts:
            return 0.0

        relevant_count = 0
        for chunk_text in context_texts:
            prompt = self._cr_prompt(query, chunk_text)
            response = self._llm(prompt).strip().lower()
            if response.startswith("ya") or response.startswith("yes") or "relevan" in response:
                relevant_count += 1

        return relevant_count / len(context_texts)

    @staticmethod
    def _cr_prompt(query: str, chunk: str) -> str:
        return (
            "Tugasmu adalah menentukan apakah potongan teks berikut relevan untuk menjawab pertanyaan.\n"
            "Jawab hanya dengan 'Ya' atau 'Tidak'.\n\n"
            f"PERTANYAAN: {query}\n\n"
            f"TEKS: {chunk}\n\n"
            "Apakah teks ini relevan untuk menjawab pertanyaan? (Ya/Tidak):"
        )

    def faithfulness(self, answer: str, context_texts: List[str]) -> float:
        if not answer or not context_texts:
            return 0.0

        claims = self._decompose_claims(answer)
        if not claims:
            return 1.0  # No verifiable claims (trivially faithful)

        context_blob = "\n\n".join(context_texts)
        supported = 0
        for claim in claims:
            prompt = self._faithfulness_prompt(claim, context_blob)
            response = self._llm(prompt).strip().lower()
            if response.startswith("ya") or response.startswith("yes") or "didukung" in response:
                supported += 1

        return supported / len(claims)

    def _decompose_claims(self, answer: str) -> List[str]:
        prompt = (
            "Ekstrak semua klaim faktual dari teks berikut sebagai daftar poin singkat.\n"
            "Format: satu klaim per baris, tanpa penomoran.\n\n"
            f"TEKS: {answer}\n\n"
            "KLAIM:"
        )
        response = self._llm(prompt)
        claims = [
            line.strip().lstrip("-•* ")
            for line in response.splitlines()
            if line.strip() and len(line.strip()) > 10
        ]
        return claims[:20]  # Cap to prevent runaway LLM cost

    @staticmethod
    def _faithfulness_prompt(claim: str, context: str) -> str:
        return (
            "Berdasarkan konteks yang diberikan, apakah klaim berikut didukung oleh konteks?\n"
            "Jawab hanya dengan 'Ya' atau 'Tidak'.\n\n"
            f"KONTEKS:\n{context[:3000]}\n\n"  # Truncate to prevent context overflow
            f"KLAIM: {claim}\n\n"
            "Apakah klaim ini didukung oleh konteks? (Ya/Tidak):"
        )

    def answer_relevance(self, query: str, answer: str, n_questions: int = 3) -> float:
        if not answer:
            return 0.0

        hyp_questions = self._generate_hypothetical_questions(answer, n=n_questions)
        if not hyp_questions:
            return 0.5  # Neutral score on failure

        query_emb = self._embedder.embed_query(query)
        hyp_embs = self._embedder.embed_queries(hyp_questions)

        # Cosine similarity
        similarities = hyp_embs @ query_emb
        return float(np.mean(similarities))

    def _generate_hypothetical_questions(
        self, answer: str, n: int = 3
    ) -> List[str]:
        prompt = (
            f"Berdasarkan jawaban berikut, buat {n} pertanyaan berbeda (dalam bahasa yang sama) "
            "yang dapat dijawab oleh teks ini.\n"
            "Format: satu pertanyaan per baris.\n\n"
            f"JAWABAN: {answer[:1500]}\n\n"
            "PERTANYAAN:"
        )
        response = self._llm(prompt)
        questions = [
            line.strip().lstrip("0123456789.-) ")
            for line in response.splitlines()
            if "?" in line and len(line.strip()) > 5
        ]
        return questions[:n]


class RAGASRetryOrchestrator:
    def __init__(
        self,
        evaluator: RAGASEvaluator,
        max_retries: int = 2,
    ):
        self.evaluator = evaluator
        self.max_retries = max_retries

    def run_with_retry(
        self,
        query: str,
        retrieve_fn, 
        generate_fn,
        reformulate_fn, 
    ) -> Tuple[str, List[RetrievedChunk], RAGASScores, int]:
        current_query = query
        chunks = retrieve_fn(current_query)
        answer = generate_fn(current_query, chunks)
        scores = self.evaluator.evaluate(query, answer, chunks)

        retry_count = 0
        while not scores.passed and retry_count < self.max_retries:
            retry_count += 1
            logger.info(f"[RAGAS Retry {retry_count}] Scores below threshold. Reformulating.")
            # Reformulate based on which metric failed
            current_query = reformulate_fn(query, scores)
            # REPLACE chunks (not expand) — SEAL-RAG principle
            chunks = retrieve_fn(current_query)
            answer = generate_fn(current_query, chunks)
            scores = self.evaluator.evaluate(query, answer, chunks)
            if scores.passed:
                break

        return answer, chunks, scores, retry_count

    @staticmethod
    def default_reformulate(query: str, scores: RAGASScores) -> str:
        if scores.context_relevance < 0.5:
            return f"{query} (jelaskan secara spesifik dan terperinci)"
        if scores.faithfulness < 0.7:
            return f"{query} (hanya berdasarkan data yang ada)"
        if scores.answer_relevance < 0.6:
            return f"Jawab pertanyaan ini secara langsung: {query}"
        return query