from __future__ import annotations

from agent.state import AgentState
from agent.tools.evaluator import crag_evaluator
from agent.tools.query_transformer import refine_query
from agent.tools.rag_models import RAGChunk
from core.config import settings


async def chunk_validator(state: AgentState) -> dict:
    chunks = [RAGChunk.model_validate(chunk) for chunk in state.get("rag_chunks") or []]
    query = state.get("rag_query") or state.get("effective_query", "")
    evaluation = await crag_evaluator.evaluate(query, chunks)

    updates = {
        "rag_confidence": evaluation.confidence,
        "rag_action": evaluation.action,
    }

    if evaluation.action == "accept":
        return updates

    attempt = state.get("rag_attempt_count", 0) + 1
    if evaluation.action == "refine" and attempt <= settings.RAG_MAX_ATTEMPTS:
        plan = state.get("plan", [])
        idx = state.get("current_step_index", 0)
        task = plan[idx].get("task", "") if idx < len(plan) else query
        refined = await refine_query(query, task, evaluation.refine_suggestion)
        return {
            **updates,
            "rag_attempt_count": attempt,
            "rag_refined_query": refined,
            "rag_chunks": None,
        }

    has_partial_results = bool(state.get("steps_completed"))
    return {
        **updates,
        "rag_attempt_count": attempt,
        "is_aborted": not has_partial_results,
        "abort_reason": None if has_partial_results else "Tidak ditemukan konteks teks yang cukup relevan untuk menjawab pertanyaan.",
        "current_step_index": len(state.get("plan", [])) if has_partial_results else state.get("current_step_index", 0),
    }


def route_after_chunk_validator(state: AgentState) -> str:
    action = state.get("rag_action")
    if action == "accept":
        return "step_reasoner"
    if action == "refine" and state.get("rag_chunks") is None and not state.get("is_aborted"):
        return "rag_retriever"
    return "synthesizer"
