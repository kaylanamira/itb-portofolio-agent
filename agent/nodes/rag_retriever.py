from __future__ import annotations

import asyncio
from typing import Any

from agent.state import AgentState, QueryType
from agent.tools.keyword_extractor import extract_keywords
from agent.tools.query_transformer import generate_multi_queries
from agent.tools.rag_models import RAGChunk, RAGRetrievalRequest
from agent.tools.retriever import retriever
from core.config import settings

MULTI_QUERY_TYPES = {
    QueryType.ANALYTICAL_TEXT,
    QueryType.DIAGNOSTIC,
    QueryType.SUMMARIZATION,
    QueryType.ANALYTICAL_HYBRID,
}


async def rag_retriever(state: AgentState) -> dict:
    plan = state.get("plan", [])
    idx = state.get("current_step_index", 0)
    current_task = plan[idx] if idx < len(plan) else {}

    base_query = state.get("rag_refined_query") or current_task.get("task") or state.get("effective_query", "")
    source_types = current_task.get("rag_source_types") or state.get("rag_source_types")
    tipe_konten = current_task.get("rag_tipe_konten") or state.get("rag_tipe_konten")
    scope_override = current_task.get("rag_scope_override") or state.get("rag_scope_override")
    keywords = extract_keywords(base_query)

    queries = [base_query]
    if state.get("query_type") in MULTI_QUERY_TYPES and not state.get("rag_refined_query"):
        queries = await generate_multi_queries(base_query, current_task.get("task", base_query))

    requests = [
        RAGRetrievalRequest(
            query=query,
            user_id=state["user_scope"].user_id,
            source_types=source_types,
            tipe_konten=tipe_konten,
            scope_override=scope_override,
            keywords=keywords,
            top_k=settings.RAG_TOP_K_FINAL,
            top_k_after_rrf=settings.RAG_TOP_K_AFTER_RRF,
            query_type=state.get("query_type").value if state.get("query_type") else None,
        )
        for query in queries
    ]

    results = await asyncio.gather(*[
        retriever.retrieve(request, state["user_scope"])
        for request in requests
    ])
    chunks = _merge_multi_query_chunks([chunk for result in results for chunk in result.chunks])
    selected = chunks[: settings.RAG_TOP_K_FINAL]

    return {
        "rag_query": base_query,
        "rag_chunks": [chunk.model_dump(mode="json") for chunk in selected],
        "rag_source_types": source_types,
        "rag_tipe_konten": tipe_konten,
        "rag_scope_override": scope_override,
        "extracted_keywords": keywords,
    }


def _merge_multi_query_chunks(chunks: list[RAGChunk]) -> list[RAGChunk]:
    merged: dict[Any, RAGChunk] = {}
    for chunk in chunks:
        existing = merged.get(chunk.chunk_id)
        if existing is None:
            merged[chunk.chunk_id] = chunk
            continue
        merged[chunk.chunk_id] = existing.model_copy(update={
            "rrf_score": existing.rrf_score + chunk.rrf_score,
            "score": max(existing.score, chunk.score),
        })
    return sorted(merged.values(), key=lambda item: item.rrf_score, reverse=True)
