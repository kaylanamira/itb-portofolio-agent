from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from agent.llm import get_llm
from agent.prompts.rag_evaluator import CRAG_EVALUATOR_SYSTEM_PROMPT, build_crag_evaluator_human_message
from agent.tools.rag_models import CRAGEvaluation, RAGChunk
from core.config import settings
from core.utils import extract_json_from_llm

logger = logging.getLogger(__name__)


class CRAGEvaluator:
    async def evaluate(self, query: str, chunks: list[RAGChunk]) -> CRAGEvaluation:
        if not chunks:
            return CRAGEvaluation(confidence=0.0, action="fallback", reasoning="No chunks retrieved.")

        preview = _chunks_preview(chunks)
        llm = get_llm("answer_validation")
        try:
            response = await llm.ainvoke([
                SystemMessage(content=CRAG_EVALUATOR_SYSTEM_PROMPT),
                HumanMessage(content=build_crag_evaluator_human_message(
                    query=query,
                    n=len(chunks),
                    chunks_preview=preview,
                )),
            ])
            data = extract_json_from_llm(response.content)
            confidence = float(data.get("confidence", 0.0))
            action = _normalize_action(confidence, data.get("action"))
            return CRAGEvaluation(
                confidence=confidence,
                action=action,
                refine_suggestion=data.get("refine_suggestion"),
                reasoning=data.get("reasoning", ""),
            )
        except Exception as exc:
            logger.warning("CRAG evaluator failed: %s", exc)
            return CRAGEvaluation(confidence=1.0, action="accept", reasoning="Evaluator unavailable.")


def _normalize_action(confidence: float, action: str | None) -> str:
    if action in {"accept", "refine", "fallback"}:
        return action
    if confidence >= settings.CRAG_CONFIDENCE_ACCEPT:
        return "accept"
    if confidence >= settings.CRAG_CONFIDENCE_REFINE:
        return "refine"
    return "fallback"


def _chunks_preview(chunks: list[RAGChunk]) -> str:
    lines = []
    for idx, chunk in enumerate(chunks[:10], start=1):
        lines.append(
            f"[{idx}] {chunk.source_type} {chunk.kelas_label} "
            f"score={chunk.rrf_score:.4f}: {chunk.chunk_text[:500]}"
        )
    return "\n".join(lines)


crag_evaluator = CRAGEvaluator()
