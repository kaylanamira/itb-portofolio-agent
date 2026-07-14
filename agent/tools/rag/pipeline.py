import logging
from typing import Literal, Optional

from pydantic import BaseModel, Field

from core.config import settings
from core.scope import UserScope
from core.sql_executor import PsycopgExecutor, QueryExecutor
from agent.tools.rag.retrieval.hybrid_retriever import HybridRetriever
from agent.tools.rag.retrieval.entity_filter import resolve_filters, RetrievalFilters
from agent.tools.rag.retrieval.hyde import MultiHydeGenerator, should_use_hyde
from agent.tools.rag.evaluation.chunk_grader import ChunkGrader
from agent.tools.rag.evaluation.query_transformer import QueryTransformer
from agent.tools.rag.evaluation.faithfulness_checker import FaithfulnessChecker
from agent.tools.rag.generation.answer_generator import AnswerGenerator, Citation
from agent.tools.rag.core.embedder import aembed_passage_texts

logger = logging.getLogger(__name__)


class RAGResult(BaseModel):
    answer: str = ""
    citations: list[Citation] = Field(default_factory=list)
    chunks_used: list[dict] = Field(default_factory=list)
    rag_query: str = ""
    retrieval_confidence: float = 0.0
    retrieval_action: Literal["ACCEPT", "FALLBACK"] = "FALLBACK"
    faithfulness_score: float = 0.0
    faithfulness_action: Literal["ACCEPT", "REVISED", "DISCLAIMED"] = "DISCLAIMED"
    hyde_used: bool = False
    filters_applied: RetrievalFilters = Field(default_factory=RetrievalFilters)
    attempts: dict = Field(default_factory=dict)


class RAGPipeline:
    def __init__(self, executor: QueryExecutor):
        self.retriever = HybridRetriever(executor)
        self.grader = ChunkGrader()
        self.transformer = QueryTransformer()
        self.hyde = MultiHydeGenerator()
        self.generator = AnswerGenerator()
        self.faithfulness = FaithfulnessChecker()

    async def run(
        self,
        query: str,
        user_scope: UserScope,
        source_types: Optional[list[str]] = None,
    ) -> RAGResult:
        filters = await resolve_filters(query)

        hyde_used = should_use_hyde(query)
        hyde_embeddings: Optional[list[list[float]]] = None
        if hyde_used:
            hypotheses = await self.hyde.generate(query)
            if hypotheses:
                hyde_embeddings = await aembed_passage_texts(hypotheses)
            else:
                hyde_used = False

        current_query = query
        chunks: list[dict] = []
        confidence = 0.0
        retrieval_action: Literal["ACCEPT", "FALLBACK"] = "FALLBACK"
        retrieval_attempts = 0

        for attempt in range(settings.RAG_MAX_ATTEMPTS):
            retrieval_attempts += 1
            # HyDE only augments the first (original-query) attempt; refined
            # retries stay a plain hybrid search to keep the loop bounded/simple.
            attempt_chunks = await self.retriever.retrieve(
                current_query, user_scope, source_types, filters,
                hyde_embeddings if attempt == 0 else None,
            )

            if not attempt_chunks:
                chunks = []
                break

            combined_text = "\n---\n".join(c.get("chunk_text", "") for c in attempt_chunks)
            evaluation = await self.grader.evaluate(query, combined_text)

            if evaluation.score >= settings.CRAG_CONFIDENCE_ACCEPT:
                chunks, confidence, retrieval_action = attempt_chunks, evaluation.score, "ACCEPT"
                break
            elif evaluation.score >= settings.CRAG_CONFIDENCE_REFINE and attempt < settings.RAG_MAX_ATTEMPTS - 1:
                current_query = await self.transformer.transform(query, evaluation.reasoning)
                continue
            else:
                chunks = attempt_chunks if evaluation.score >= 0.20 else []
                confidence = evaluation.score
                retrieval_action = "FALLBACK"
                break

        if not chunks:
            return RAGResult(
                answer="",
                citations=[],
                chunks_used=[],
                rag_query=current_query,
                retrieval_confidence=confidence,
                retrieval_action=retrieval_action,
                faithfulness_score=0.0,
                faithfulness_action="DISCLAIMED",
                hyde_used=hyde_used,
                filters_applied=filters,
                attempts={"retrieval_attempts": retrieval_attempts, "generation_attempts": 0},
            )

        generated = await self.generator.generate(query, chunks)
        faith_score = 0.0
        faith_action: Literal["ACCEPT", "REVISED", "DISCLAIMED"] = "ACCEPT"
        generation_attempts = 1

        for gen_attempt in range(settings.RAG_MAX_GENERATION_ATTEMPTS):
            faith = await self.faithfulness.check(generated.answer, chunks)
            faith_score = faith.score

            if faith_score >= settings.FAITH_ACCEPT:
                faith_action = "ACCEPT"
                break

            attempts_remain = gen_attempt < settings.RAG_MAX_GENERATION_ATTEMPTS - 1
            if not attempts_remain:
                generated.answer = f"{generated.answer}\n\n_{settings.FAITH_DISCLAIMER}_"
                faith_action = "DISCLAIMED"
                break

            if faith_score >= settings.FAITH_REVISE:
                # Over-claiming from thin context is the common failure mode here —
                # regenerate with the specific unsupported claims (cheaper than
                # re-retrieving; retrieval already had its own CRAG loop above).
                unsupported = [c.claim for c in faith.claims if not c.supported]
            else:
                unsupported = ["(low overall faithfulness — answer more conservatively, "
                               "or state that context is insufficient)"]

            generated = await self.generator.regenerate_with_critique(
                query, chunks, generated.answer, unsupported,
            )
            faith_action = "REVISED"
            generation_attempts += 1

        return RAGResult(
            answer=generated.answer,
            citations=generated.citations,
            chunks_used=chunks,
            rag_query=current_query,
            retrieval_confidence=confidence,
            retrieval_action=retrieval_action,
            faithfulness_score=faith_score,
            faithfulness_action=faith_action,
            hyde_used=hyde_used,
            filters_applied=filters,
            attempts={"retrieval_attempts": retrieval_attempts, "generation_attempts": generation_attempts},
        )


async def run_rag(
    query: str,
    user_scope: UserScope,
    source_types: Optional[list[str]] = None,
) -> RAGResult:
    pipeline = RAGPipeline(PsycopgExecutor())
    return await pipeline.run(query, user_scope, source_types)
